"""E2E de las API keys por integración (Chunk 2), contra el stack levantado.

Prueba el ciclo real: la key de bootstrap crea una key acotada, y esa key nueva puede hacer
**solo** lo suyo. Requiere `docker compose up -d` (si no, se saltan).
"""
import uuid

import httpx
import pytest

pytestmark = pytest.mark.e2e

GATEWAY = "http://localhost:8000"
BOOTSTRAP = {"X-TeleFlow-API-Key": "dev-key-change-me"}


@pytest.fixture
def key_de_solo_lectura(gateway_up: None):
    """Crea (con la key de bootstrap) una key restringida a lectura."""
    nombre = f"e2e-lectura-{uuid.uuid4().hex[:8]}"
    r = httpx.post(f"{GATEWAY}/keys", headers=BOOTSTRAP, timeout=20,
                   json={"name": nombre, "scopes": ["instances:read", "entities:read"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key"].startswith("tf_")
    return body["key"]


def test_la_key_creada_puede_leer_pero_no_desplegar(key_de_solo_lectura):
    """El caso que motiva todo: leer la 360 NO habilita desplegar código."""
    h = {"X-TeleFlow-API-Key": key_de_solo_lectura}

    assert httpx.get(f"{GATEWAY}/instances", headers=h, timeout=20).status_code == 200

    r = httpx.post(f"{GATEWAY}/flows/e2e_probe", headers=h, timeout=20,
                   json={"source": 'entity "p" { }', "version": "1.0.0"})
    assert r.status_code == 403
    assert "flows:deploy" in r.json()["detail"]

    r = httpx.post(f"{GATEWAY}/execute", headers=h, timeout=20,
                   json={"flow_name": "x", "version": "latest", "payload": {}})
    assert r.status_code == 403


def test_la_key_creada_no_puede_crear_otras_keys(key_de_solo_lectura):
    """Repartir permisos requiere keys:admin: una key común no puede escalar sola."""
    h = {"X-TeleFlow-API-Key": key_de_solo_lectura}

    r = httpx.post(f"{GATEWAY}/keys", headers=h, timeout=20,
                   json={"name": "escalada", "scopes": ["*"]})

    assert r.status_code == 403
    assert "keys:admin" in r.json()["detail"]


def test_el_secreto_no_se_puede_volver_a_ver(key_de_solo_lectura):
    """La DB guarda solo el hash: el listado nunca devuelve la key en claro."""
    r = httpx.get(f"{GATEWAY}/keys", headers=BOOTSTRAP, timeout=20)
    assert r.status_code == 200

    cuerpo = r.text
    assert key_de_solo_lectura not in cuerpo
    assert "key_hash" not in cuerpo

    listadas = r.json()
    assert any(k["scopes"] == ["entities:read", "instances:read"] for k in listadas)


def test_una_key_inexistente_da_401():
    assert httpx.get(f"{GATEWAY}/instances", timeout=20,
                     headers={"X-TeleFlow-API-Key": "tf_no-existe"}).status_code == 401
