"""Auditoría del gateway: que quede constancia de quién hizo qué.

Antes, la identidad de la key se resolvía, se usaba para autorizar y se tiraba: lo único que
quedaba era una línea de log. Estos tests fijan qué se registra, qué no, y —lo más
importante— que la cobertura sea **estructural**: una ruta nueva con scope de escritura no
puede quedar sin auditar por olvido.

No hay Postgres en los tests unitarios: `sink_auditoria` (conftest) captura en memoria las
filas que el gateway escribiría.
"""
from typing import cast

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from teleflow.common.config import get_settings
from teleflow.gateway import auth
from teleflow.gateway.main import app, get_bootstrap_scopes

KEY = "dev-key-change-me"
H = {"X-TeleFlow-API-Key": KEY}


@pytest.fixture
def client(monkeypatch, sink_auditoria):
    abiertos = []

    def _make(scopes: str = "*", propagar_errores: bool = True) -> TestClient:
        monkeypatch.setenv("TELEFLOW_API_KEY", KEY)
        monkeypatch.setenv("TELEFLOW_API_KEY_SCOPES", scopes)
        get_settings.cache_clear()
        get_bootstrap_scopes.cache_clear()
        c = TestClient(app, raise_server_exceptions=propagar_errores)
        c.__enter__()
        abiertos.append(c)
        return c

    yield _make

    for c in abiertos:
        c.__exit__(None, None, None)
    get_settings.cache_clear()
    get_bootstrap_scopes.cache_clear()


# ------------------------------------------------- qué se registra

def test_una_escritura_queda_registrada(client, sink_auditoria):
    """El caso que motiva todo: quién desplegó qué y cuándo tiene que ser consultable."""
    c = client("*")

    # Sin upstream levantado termina en 502, pero la acción **se intentó** y eso es lo que
    # se audita: el registro lleva el resultado, no solo la intención.
    c.post("/flows/alta_socio", headers=H,
           json={"source": "entity \"a\" { }", "version": "1.0.0"})

    assert len(sink_auditoria) == 1
    fila = sink_auditoria[0]
    assert fila.scope == auth.FLOWS_DEPLOY
    assert fila.method == "POST"
    assert fila.subject == "alta_socio"
    assert fila.actor_name == auth.BOOTSTRAP_KEY_NAME
    assert fila.status_code >= 400  # 502: el upstream no está levantado


def test_el_deploy_registra_version_y_checksum_pero_no_el_source(client, sink_auditoria):
    """El checksum responde "¿esta versión es la que se publicó?" sin guardar el código.

    El cuerpo no se guarda nunca: es la tabla que más se conserva y más gente puede leer.
    """
    c = client("*")
    fuente = "entity \"socio\" { fields { nombre: string required } }"

    c.post("/flows/alta_socio", headers=H, json={"source": fuente, "version": "2.1.0"})

    detalles = sink_auditoria[0].details or {}
    assert detalles.get("version") == "2.1.0"
    # Sin upstream no hay checksum, pero el source no puede estar por ningún lado.
    assert fuente not in str(sink_auditoria[0].__dict__)


def test_una_lectura_exitosa_no_se_registra(client, sink_auditoria):
    """La mayoría del tráfico. Auditarlas multiplicaría la tabla sin agregar traza útil."""
    c = client("*")

    c.get("/flows", headers=H)

    assert sink_auditoria == []


def test_un_intento_denegado_queda_registrado_con_el_scope_que_se_intento(
        client, sink_auditoria):
    """Un 403 es la señal más barata de una credencial filtrada probando permisos."""
    c = client("entities:read")

    r = c.post("/flows/x", headers=H, json={"source": "", "version": "1.0.0"})

    assert r.status_code == 403
    assert len(sink_auditoria) == 1
    fila = sink_auditoria[0]
    assert fila.status_code == 403
    # El scope se anota **antes** de chequearlo: si no, un 403 no diría qué se intentó hacer.
    assert fila.scope == auth.FLOWS_DEPLOY


def test_una_key_invalida_queda_registrada(client, sink_auditoria):
    """El 401 lo corta el middleware de auth antes de cualquier ruta: no hay scope que anotar,
    pero el intento tiene que quedar."""
    c = client("*")

    r = c.get("/flows", headers={"X-TeleFlow-API-Key": "no-existe"})

    assert r.status_code == 401
    assert len(sink_auditoria) == 1
    assert sink_auditoria[0].status_code == 401
    assert sink_auditoria[0].scope == ""
    assert sink_auditoria[0].actor_key_id is None


def test_una_ruta_que_revienta_deja_constancia(client, monkeypatch, sink_auditoria):
    """El intento más interesante de registrar: un deploy que crashea a mitad de camino.

    El 500 lo arma un middleware de Starlette que está **por fuera** del de auditoría, así
    que sin atrapar la excepción el registro no se escribía.
    """
    from teleflow.gateway import main

    async def _explota(*args, **kwargs):
        raise RuntimeError("bug en la ruta")

    monkeypatch.setattr(main, "_post_upstream", _explota)
    c = client("*", propagar_errores=False)

    r = c.post("/flows/x", headers=H, json={"source": "a", "version": "1.0.0"})

    assert r.status_code == 500
    assert len(sink_auditoria) == 1
    assert sink_auditoria[0].status_code == 500
    assert sink_auditoria[0].scope == auth.FLOWS_DEPLOY


def test_un_intento_cortado_por_rate_limit_deja_constancia(client, monkeypatch,
                                                           sink_auditoria):
    """Un 429 es "no te dejé": martillar la API es una señal, no ruido."""
    from teleflow.gateway import main

    agotado = main.TokenBucket(1)
    agotado.tokens = 0.0
    agotado.rate = 0.0
    c = client("*")
    # Sin Redis, el limitador cae al bucket del proceso: es el camino que este test necesita
    # forzar, y lo que importa acá es que el 429 quede auditado, no cómo se decidió.
    monkeypatch.setitem(main.state, "redis", None)
    monkeypatch.setitem(main._buckets, KEY, agotado)

    r = c.post("/flows/x", headers=H, json={"source": "a", "version": "1.0.0"})

    assert r.status_code == 429
    assert len(sink_auditoria) == 1
    assert sink_auditoria[0].status_code == 429


def test_el_subject_conserva_el_registro_y_no_solo_el_tipo(client, sink_auditoria):
    """`/entities/socio/12345`: "alguien modificó un socio" sin decir cuál no sirve."""
    c = client("*")

    c.post("/entities/socio/12345", headers=H, json={})

    assert sink_auditoria[0].subject == "socio/12345"


def test_las_rutas_publicas_no_se_auditan(client, sink_auditoria):
    c = client("*")

    c.get("/health")

    assert sink_auditoria == []


# ------------------------------------------------- consulta

def test_leer_la_auditoria_exige_su_propio_scope(client, sink_auditoria):
    """`audit:read` no se hereda de `keys:admin` ni de nada: se otorga."""
    c = client("keys:admin,flows:deploy,entities:write")

    r = c.get("/audit", headers=H)

    assert r.status_code == 403
    assert "audit:read" in r.json()["detail"]


def test_leer_la_auditoria_queda_auditado(client, sink_auditoria):
    """La única lectura donde importa quién miró: alguien revisando si sus movimientos
    quedaron registrados es exactamente lo que este registro tiene que mostrar."""
    c = client("*")

    c.get("/audit", headers=H)

    assert len(sink_auditoria) == 1
    assert sink_auditoria[0].scope == auth.AUDIT_READ


# ------------------------------------------------- cobertura estructural

def test_todo_scope_esta_clasificado():
    """El guard que importa: un scope nuevo **obliga** a decidir si se audita.

    Sin esto, agregar `flows:delete` al catálogo y olvidarse de sumarlo a
    `SCOPES_DE_ESCRITURA` dejaría esa acción sin auditar, y el olvido no haría ruido — una
    falla silenciosa justo en la capa de garantías.
    """
    clasificados = auth.SCOPES_DE_ESCRITURA | auth.SCOPES_DE_LECTURA

    sin_clasificar = auth.ALL_SCOPES - clasificados
    assert not sin_clasificar, (
        f"scope(s) sin clasificar como lectura o escritura: {sorted(sin_clasificar)}. "
        f"Decidí si su acción se audita y sumalo al conjunto que corresponda."
    )
    inventados = clasificados - auth.ALL_SCOPES
    assert not inventados, f"scope(s) clasificados que no existen: {sorted(inventados)}"
    assert not (auth.SCOPES_DE_ESCRITURA & auth.SCOPES_DE_LECTURA)


def test_toda_ruta_con_scope_de_escritura_pasa_por_el_marcador():
    """La cobertura no depende de una lista de rutas: depende de `require`, que la anota.

    Verifica el mecanismo: pedir un scope de escritura deja el rastro que lee el middleware.
    """
    class _Estado:
        pass

    class _RequestFalso:
        def __init__(self):
            self.state = _Estado()

    for scope in sorted(auth.SCOPES_DE_ESCRITURA):
        req = cast(Request, _RequestFalso())
        with pytest.raises(Exception):
            # Sin identidad no tiene el scope → 403, pero primero tiene que haberlo anotado.
            auth.require(scope)(req)
        assert auth.scope_exigido(req) == scope
