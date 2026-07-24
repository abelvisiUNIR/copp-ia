"""E2E: durable sleep + human_task (venta_internet_hogar) — ADR-002.

La instancia debe dormir en WAITING_SIGNAL en `aprobacion_gerencia` y
reactivarse al recibir la señal `approve`, hasta COMPLETED.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e


async def test_durable_sleep_signal_approve(
    client: httpx.AsyncClient,
    poll_status: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    # 1. Disparar el proceso
    r = await client.post("/execute", json={
        "flow_name": "venta_internet_hogar",
        "payload": {"cliente_id": "cli-e2e", "producto": "fibra-300"},
    })
    assert r.status_code == 202, r.text
    instance_id = r.json()["instance_id"]

    # 2. Debe dormir en el human_task
    waiting = await poll_status(instance_id, "WAITING_SIGNAL")
    assert waiting["current_step"] == "aprobacion_gerencia"

    # 3. La señal approve lo reactiva
    r = await client.post(f"/instances/{instance_id}/signal", json={
        "step_name": "aprobacion_gerencia", "signal": "approve", "actor_id": "e2e",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SIGNALED"

    # 4. Completa por la rama de aprobación
    done = await poll_status(instance_id, "COMPLETED")
    assert done["status"] == "COMPLETED"
    assert "aprobacion_gerencia" in done["context"]["signals"]


async def test_signal_sobre_instancia_completada_rechazada(
    client: httpx.AsyncClient,
    poll_status: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    """Reenviar señal a una instancia ya COMPLETED debe rechazarse (no re-procesa)."""
    r = await client.post("/execute", json={
        "flow_name": "venta_internet_hogar",
        "payload": {"cliente_id": "cli-e2e-2", "producto": "fibra-600"},
    })
    instance_id = r.json()["instance_id"]
    await poll_status(instance_id, "WAITING_SIGNAL")

    sig = {"step_name": "aprobacion_gerencia", "signal": "approve", "actor_id": "e2e"}
    assert (await client.post(f"/instances/{instance_id}/signal", json=sig)).status_code == 200
    await poll_status(instance_id, "COMPLETED")

    # segunda señal: la instancia ya no espera
    r2 = await client.post(f"/instances/{instance_id}/signal", json=sig)
    assert r2.status_code >= 400
