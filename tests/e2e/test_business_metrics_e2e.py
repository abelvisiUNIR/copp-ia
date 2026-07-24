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
