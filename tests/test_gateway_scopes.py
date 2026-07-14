"""Autorización por scopes en el gateway.

Lo que se prueba: una key restringida **no puede** salirse de sus permisos. El caso que motiva
todo esto: una integración que lee la vista 360 no debe poder desplegar código.

No hay servicios upstream levantados, así que una ruta autorizada termina en 502 (no se pudo
proxear). Eso alcanza: lo que importa es 403 (bloqueado) vs no-403 (pasó la autorización).
"""
import pytest
from fastapi.testclient import TestClient

from teleflow.common.config import get_settings
from teleflow.gateway import auth
from teleflow.gateway.auth import UnknownScopeError, parse_scopes
from teleflow.gateway.main import app, get_key_scopes

KEY = "dev-key-change-me"
H = {"X-TeleFlow-API-Key": KEY}


@pytest.fixture
def client(monkeypatch):
    """TestClient con los scopes de la key global configurables por test.

    Se entra al context manager para que corra el `lifespan` (crea el cliente httpx que usa
    `_proxy`); sin eso, una ruta autorizada rompe en vez de intentar proxear.
    """
    abiertos = []

    def _make(scopes: str) -> TestClient:
        monkeypatch.setenv("TELEFLOW_API_KEY", KEY)
        monkeypatch.setenv("TELEFLOW_API_KEY_SCOPES", scopes)
        get_settings.cache_clear()
        get_key_scopes.cache_clear()
        c = TestClient(app)
        c.__enter__()
        abiertos.append(c)
        return c

    yield _make

    for c in abiertos:
        c.__exit__(None, None, None)
    get_settings.cache_clear()
    get_key_scopes.cache_clear()


# ------------------------------------------------------------------ el caso que importa

def test_key_de_solo_lectura_no_puede_desplegar(client):
    """Una integración que lee la 360 NO debe poder registrar código nuevo."""
    c = client("entities:read,instances:read")

    r = c.post("/flows/x", headers=H,
               json={"source": "entity \"a\" { }", "version": "1.0.0"})

    assert r.status_code == 403
    assert "flows:deploy" in r.json()["detail"]


def test_key_de_solo_lectura_si_puede_leer_la_360(client):
    c = client("entities:read,instances:read")

    r = c.get("/entities/nino/n1/360", headers=H)

    assert r.status_code != 403     # pasó la autorización (502: no hay executor levantado)


# ------------------------------------------------------- lectura vs escritura por método

def test_scope_de_lectura_no_habilita_escribir_entidades(client):
    c = client("entities:read")

    assert c.get("/entities/nino/n1", headers=H).status_code != 403
    assert c.post("/entities/nino", headers=H,
                  json={"entity_id": "n1", "fields": {}}).status_code == 403


def test_scope_de_escritura_habilita_post_y_patch(client):
    c = client("entities:write")

    assert c.post("/entities/nino", headers=H, json={}).status_code != 403
    assert c.patch("/entities/nino/n1", headers=H, json={}).status_code != 403
    assert c.get("/entities/nino/n1", headers=H).status_code == 403   # write != read


# --------------------------------------------------------- acciones sobre instancias

def test_disparar_no_habilita_firmar_ni_reintentar(client):
    """Los tres son POST sobre instancias, pero son permisos distintos."""
    c = client("instances:trigger")

    assert c.post("/execute", headers=H, json={"flow_name": "f"}).status_code != 403
    assert c.post("/instances/i1/signal", headers=H, json={}).status_code == 403
    assert c.post("/instances/i1/retry", headers=H).status_code == 403


# ------------------------------------------------------------- compatibilidad y default

def test_sin_config_la_key_global_conserva_todos_los_permisos(client):
    """El default es `*`: el upgrade no rompe ninguna instalación existente."""
    c = client("*")

    for path in ("/flows", "/instances", "/entities/nino/n1", "/drafts"):
        assert c.get(path, headers=H).status_code != 403
    assert c.post("/execute", headers=H, json={"flow_name": "f"}).status_code != 403
    assert c.post("/flows/x", headers=H,
                  json={"source": "", "version": "1"}).status_code != 403


# ------------------------------------------------------------- upstream caído = 502

def test_deploy_con_el_parser_caido_da_502_no_500(client):
    """Antes: `deploy_flow` no atrapaba el ConnectError y el gateway reventaba con un 500."""
    c = client("*")   # los servicios core no están levantados en el test

    r = c.post("/flows/x", headers=H, json={"source": "entity \"a\" { }",
                                            "version": "1.0.0"})

    assert r.status_code == 502
    assert "Servicio no disponible" in r.json()["detail"]


def test_key_invalida_sigue_dando_401_no_403(client):
    """La autenticación va antes que la autorización: sin key válida no se llega al scope."""
    c = client("*")

    r = c.get("/flows", headers={"X-TeleFlow-API-Key": "no-es-la-key"})

    assert r.status_code == 401


def test_rutas_publicas_no_piden_scope(client):
    c = client("")   # key sin ningún permiso

    assert c.get("/health").status_code == 200


# ----------------------------------------------------------------- parseo de la config

def test_parse_scopes():
    assert parse_scopes("*") == auth.ALL_SCOPES
    assert parse_scopes("flows:read, entities:read") == {"flows:read", "entities:read"}
    assert parse_scopes("") == frozenset()          # key sin permisos
    assert parse_scopes("flows:read,*") == auth.ALL_SCOPES


def test_scope_con_typo_falla_en_vez_de_dar_menos_permisos():
    """Un typo silenciado dejaría al operador preguntándose por qué su key no anda."""
    with pytest.raises(UnknownScopeError, match="flows:deply"):
        parse_scopes("flows:read,flows:deply")
