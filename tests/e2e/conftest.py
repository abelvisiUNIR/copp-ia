"""Fixtures para tests e2e contra el stack levantado (gateway :8000).

Estos tests requieren `docker compose up -d`. Si el gateway no responde, se
**saltan** (skip) — así el `pytest` unitario sigue verde sin stack.
Se marcan con `@pytest.mark.e2e` (ver `pytestmark` en cada módulo).
"""
from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

GATEWAY = os.environ.get("TELEFLOW_GATEWAY_URL", "http://localhost:8000")
API_KEY = os.environ.get("TELEFLOW_API_KEY", "dev-key-change-me")
ROOT = Path(__file__).resolve().parents[2]

_HEADERS = {"X-TeleFlow-API-Key": API_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def gateway_up() -> None:
    """Salta toda la suite e2e si el gateway no está disponible."""
    try:
        httpx.get(f"{GATEWAY}/health", timeout=3.0).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"Stack e2e no disponible en {GATEWAY} ({exc}). "
            f"Levantar con `docker compose up -d`."
        )


@pytest.fixture(scope="session")
def deployed(gateway_up: None) -> None:
    """Asegura ceibal + venta desplegados. Si hubo deploy nuevo, espera el
    cache de dominio del executor (30 s)."""
    existing = {
        f["name"]
        for f in httpx.get(f"{GATEWAY}/flows", headers=_HEADERS, timeout=10).json()
    }
    nuevos = False
    for name, path in (
        ("ceibal", ROOT / "examples" / "ceibal.tflow"),
        ("venta_internet_hogar", ROOT / "examples" / "venta_internet_hogar.tflow"),
    ):
        if name in existing:
            continue
        src = path.read_text(encoding="utf-8")
        r = httpx.post(
            f"{GATEWAY}/flows/{name}",
            headers=_HEADERS,
            json={"source": src, "version": "1.0.0", "description": "e2e"},
            timeout=30,
        )
        assert r.status_code == 201, r.text
        nuevos = True
    if nuevos:
        time.sleep(32)  # domain_cache_ttl del executor


@pytest.fixture
async def client(deployed: None) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=GATEWAY, headers=_HEADERS, timeout=30.0
    ) as c:
        yield c


@pytest.fixture
def poll_status(
    client: httpx.AsyncClient,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def _poll(instance_id: str, expect: str,
                    tries: int = 40, delay: float = 0.5) -> dict[str, Any]:
        last = "?"
        for _ in range(tries):
            r = await client.get(f"/instances/{instance_id}")
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            last = data["status"]
            if last == expect:
                return data
            await asyncio.sleep(delay)
        raise AssertionError(
            f"instancia {instance_id} no llegó a {expect} (último: {last})")
    return _poll


@pytest.fixture
def count_instances(
    client: httpx.AsyncClient,
) -> Callable[[str], Awaitable[int]]:
    async def _count(flow_name: str) -> int:
        r = await client.get("/instances", params={"flow_name": flow_name, "limit": 500})
        r.raise_for_status()
        return len(r.json())
    return _count


@pytest.fixture
def poll_count(
    count_instances: Callable[[str], Awaitable[int]],
) -> Callable[..., Awaitable[int]]:
    async def _poll(flow_name: str, at_least: int,
                    tries: int = 30, delay: float = 0.5) -> int:
        current = 0
        for _ in range(tries):
            current = await count_instances(flow_name)
            if current >= at_least:
                return current
            await asyncio.sleep(delay)
        raise AssertionError(
            f"'{flow_name}': esperaba >= {at_least} instancias, hay {current}")
    return _poll
