"""E2E de la idempotencia, contra Postgres real y pasando por el gateway.

Dos cosas que solo se ven acá: que el `UNIQUE` de la base sea la garantía de verdad, y que el
header `Idempotency-Key` **llegue** al executor — el proxy del gateway arma los headers desde
cero, así que sin la propagación explícita la clave se perdería en el camino y el cliente
creería estar protegido. Requiere `docker compose up -d` (si no, se saltan).
"""
import uuid
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e

GATEWAY = "http://localhost:8000"
H = {"X-TeleFlow-API-Key": "dev-key-change-me", "Content-Type": "application/json"}

PEDIDO = {"flow_name": "venta_internet_hogar",
          "payload": {"cliente_id": "cli-idem", "producto": "fibra-300"}}


def _disparar(clave: str | None = None, pedido: dict[str, Any] | None = None) -> httpx.Response:
    headers = dict(H)
    if clave:
        headers["Idempotency-Key"] = clave
    return httpx.post(f"{GATEWAY}/execute", headers=headers, timeout=30,
                      json=pedido if pedido is not None else PEDIDO)


def test_el_header_llega_al_executor_y_deduplica(deployed):
    """El caso completo: mismo pedido, misma clave, una sola instancia."""
    clave = f"e2e-{uuid.uuid4()}"

    primera = _disparar(clave)
    segunda = _disparar(clave)

    assert primera.status_code == 202, primera.text
    assert segunda.status_code == 202, segunda.text
    assert segunda.json()["instance_id"] == primera.json()["instance_id"]
    assert segunda.json().get("idempotent_replay") is True
    assert not primera.json().get("idempotent_replay"), "la primera no es un replay"


def test_sin_clave_cada_llamada_dispara(deployed):
    """La protección es opcional: sin clave, el comportamiento de siempre."""
    primera = _disparar()
    segunda = _disparar()

    assert primera.json()["instance_id"] != segunda.json()["instance_id"]


def test_la_misma_clave_con_otro_pedido_es_409(deployed):
    clave = f"e2e-{uuid.uuid4()}"
    _disparar(clave).raise_for_status()

    otro = dict(PEDIDO, payload={"cliente_id": "otro-cliente", "producto": "fibra-600"})
    r = _disparar(clave, pedido=otro)

    assert r.status_code == 409
    assert "ya se usó para otro pedido" in r.text


def test_la_dedup_sobrevive_al_tiempo(deployed):
    """La clave vive con la instancia, sin TTL: un reintento tardío sigue protegido."""
    clave = f"e2e-{uuid.uuid4()}"
    primera = _disparar(clave)

    # Se consulta la instancia (pasa tiempo real, la instancia avanza de estado) y se
    # reintenta: el replay tiene que seguir devolviendo la misma.
    instancia = primera.json()["instance_id"]
    httpx.get(f"{GATEWAY}/instances/{instancia}", headers=H, timeout=20).raise_for_status()

    assert _disparar(clave).json()["instance_id"] == instancia
