"""E2E: el backlog de human_tasks llega hasta Prometheus.

Cubre la parte que el test unitario no puede: que la agregación corra de verdad contra
Postgres, que el executor la exponga en `/metrics` y que Prometheus la scrapee. El executor
no publica su puerto al host (la entrada única es el gateway), así que se consulta por la
API de Prometheus — que además es el consumidor real de la métrica.

Es lento a propósito: hay que esperar el ciclo del colector (`BUSINESS_METRICS_INTERVAL`,
30 s) más el `scrape_interval` de Prometheus (15 s).
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e

PROMETHEUS = os.environ.get("TELEFLOW_PROMETHEUS_URL", "http://localhost:9090")


@pytest.fixture(scope="session")
def prometheus_up(gateway_up: None) -> None:
    try:
        httpx.get(f"{PROMETHEUS}/-/ready", timeout=3.0).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Prometheus no disponible en {PROMETHEUS} ({exc}).")


async def _query_scalar(query: str, tries: int = 30, delay: float = 3.0) -> float:
    """Primer valor de la query, esperando a que el colector y el scrape hagan su ciclo."""
    ultimo = 0.0
    async with httpx.AsyncClient(base_url=PROMETHEUS, timeout=10.0) as prom:
        for _ in range(tries):
            r = await prom.get("/api/v1/query", params={"query": query})
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if result:
                ultimo = float(result[0]["value"][1])
                if ultimo > 0:
                    return ultimo
            await asyncio.sleep(delay)
    return ultimo


async def test_una_instancia_dormida_aparece_en_el_backlog_de_human_tasks(
    prometheus_up: None,
    client: httpx.AsyncClient,
    poll_status: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    r = await client.post("/execute", json={
        "flow_name": "venta_internet_hogar",
        "payload": {"cliente_id": "cli-metrics", "producto": "fibra-300"},
    })
    assert r.status_code == 202, r.text
    instance_id = r.json()["instance_id"]
    await poll_status(instance_id, "WAITING_SIGNAL")

    backlog = await _query_scalar(
        'teleflow_human_task_backlog{step_name="aprobacion_gerencia"}')
    espera = await _query_scalar(
        'teleflow_human_task_oldest_seconds{step_name="aprobacion_gerencia"}')

    assert backlog >= 1, "la instancia dormida no aparece en el backlog"
    assert espera > 0, "la antigüedad del backlog debería avanzar con el tiempo"

    # Resuelta la tarea, deja de contar como pendiente.
    await client.post(f"/instances/{instance_id}/signal", json={
        "step_name": "aprobacion_gerencia", "signal": "approve", "actor_id": "e2e",
    })
    await poll_status(instance_id, "COMPLETED")


async def test_las_instancias_vivas_se_publican_por_estado(
    prometheus_up: None,
    client: httpx.AsyncClient,
    poll_status: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    r = await client.post("/execute", json={
        "flow_name": "venta_internet_hogar",
        "payload": {"cliente_id": "cli-metrics-2", "producto": "fibra-600"},
    })
    instance_id = r.json()["instance_id"]
    await poll_status(instance_id, "WAITING_SIGNAL")

    vivas = await _query_scalar(
        'teleflow_instances_current{flow_name="venta_internet_hogar",'
        'status="WAITING_SIGNAL"}')

    assert vivas >= 1

    await client.post(f"/instances/{instance_id}/signal", json={
        "step_name": "aprobacion_gerencia", "signal": "approve", "actor_id": "e2e",
    })
    await poll_status(instance_id, "COMPLETED")


# --- El turno de publicación, contra Postgres real ---------------------------------------

_GUION_DOS_REPLICAS = """
import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from teleflow.common.config import Settings
from teleflow.executor_service.business_metrics import (
    BusinessMetricsCollector, InstanceGroup)

ajustes = Settings()


async def main():
    # Dos engines separados = dos conexiones distintas, como dos réplicas del executor.
    motores = [create_async_engine(ajustes.database_url) for _ in range(2)]
    replicas = [BusinessMetricsCollector(async_sessionmaker(m), ajustes) for m in motores]

    turnos = []

    def espiar(indice):
        async def _collect(_session):
            # Solo llega acá quien ganó el turno. La espera fuerza el solapamiento: sin ella
            # la primera podría soltar el lock antes de que la segunda lo pida.
            turnos.append(indice)
            await asyncio.sleep(0.5)
            return [InstanceGroup("venta", "WAITING_SIGNAL", "aprobacion", 7, None)]
        return _collect

    for i, r in enumerate(replicas):
        r._collect = espiar(i)

    await asyncio.gather(*(r.refresh() for r in replicas))

    print("TURNOS=%d" % len(turnos))
    for m in motores:
        await m.dispose()


asyncio.run(main())
"""


def test_solo_una_replica_toma_el_turno_del_ciclo(gateway_up: None) -> None:
    """El lock de Postgres tiene que excluir de verdad, no solo en un doble.

    Se corre **dentro** del executor porque Postgres no se publica al host (la entrada única
    es el gateway). Dos colectores con conexiones distintas refrescan a la vez y solo uno tiene
    que llegar a leer la DB.

    **Lo que se mira es cuántos tomaron el turno, no el valor del gauge** — y esa distinción
    costó un test vacuo: la primera versión afirmaba que el gauge quedaba en 7 y no en 14, pero
    los dos colectores comparten el objeto Gauge del proceso, así que dos `set(7)` dan 7 igual
    y el test pasaba **con el bug puesto** (verificado por mutación). La multiplicación real
    ocurre entre procesos distintos, cada uno con su registry, sumados por Prometheus: no se
    puede reproducir dentro de un proceso. Lo que sí se puede verificar acá es el invariante
    que sostiene el lock, que es exactamente lo que estaba roto.
    """
    import subprocess
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    if not subprocess.run(["docker", "compose", "ps", "-q", "executor-service"],
                          cwd=raiz, capture_output=True).stdout.strip():
        pytest.skip("docker compose no disponible: el turno se prueba contra Postgres real")

    r = subprocess.run(
        ["docker", "compose", "exec", "-T", "executor-service", "python", "-c",
         _GUION_DOS_REPLICAS],
        cwd=raiz, capture_output=True, timeout=180)
    salida = r.stdout.decode(errors="replace")
    assert r.returncode == 0, r.stderr.decode(errors="replace")
    assert "TURNOS=1" in salida, f"esperaba un solo publicador por ciclo, salió: {salida}"
