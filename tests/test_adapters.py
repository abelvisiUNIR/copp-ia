"""Tests unitarios de los adapters de steps (REST / SMTP / noop / notification).

Sin infraestructura: httpx y smtplib se mockean. Cubre casos felices y de error.
"""
import smtplib
from typing import Any

import httpx
import pytest

from teleflow.dsl.ast_nodes import IntegrationDef, Ref, StepDef
from teleflow.executor_service.adapters import (
    RetryableStepError,
    StepExecutionError,
    is_retryable_transport_error,
    eval_payload,
    is_retryable_status,
    render_template,
    resolve_env,
    run_automated,
    run_notification,
)


# --------------------------------------------------------------- helpers puros

def test_resolve_env(monkeypatch):
    monkeypatch.setenv("TOKEN", "secret")
    assert resolve_env("Bearer ${env.TOKEN}") == "Bearer secret"
    assert resolve_env(123) == 123                     # no-str pasa igual


def test_una_variable_de_entorno_faltante_falla_y_dice_cual(monkeypatch):
    """Antes se reemplazaba por cadena vacía, y era una falla silenciosa costosa.

    Con `base_url: "${env.LMS_URL}"` sin definir, el deploy pasaba, la validación pasaba, y el
    fallo aparecía cuando un expediente real llegaba al step: un `UnsupportedProtocol` sobre
    `/api/credentials` que no nombra la variable. Medido en un stack levantado: instancia FAILED
    después de gastar 4 intentos.
    """
    monkeypatch.delenv("NO_EXISTE", raising=False)

    with pytest.raises(StepExecutionError) as err:
        resolve_env("${env.NO_EXISTE}/api/x")

    assert "NO_EXISTE" in str(err.value), "el error tiene que nombrar la variable que falta"


def test_una_variable_vacia_cuenta_como_faltante(monkeypatch):
    """`LMS_URL=` en el .env produce el mismo fallo que no declararla."""
    monkeypatch.setenv("VACIA", "")

    with pytest.raises(StepExecutionError):
        resolve_env("${env.VACIA}/api/x")


def test_falta_de_config_no_es_transitoria(monkeypatch):
    """Ningún reintento va a crear la variable: tiene que fallar al toque."""
    monkeypatch.delenv("NO_EXISTE", raising=False)

    with pytest.raises(StepExecutionError) as err:
        resolve_env("${env.NO_EXISTE}")

    assert not isinstance(err.value, RetryableStepError)


def test_render_template():
    ctx = {"payload": {"x": "V"}}
    assert render_template("a={payload.x}", ctx) == "a=V"
    assert render_template("m={payload.falta}", ctx) == "m="   # ref inexistente -> ""


def test_eval_payload():
    step = StepDef(name="s", payload={"id": Ref(("payload", "cid")), "fijo": 7})
    assert eval_payload(step, {"payload": {"cid": "c9"}}) == {"id": "c9", "fijo": 7}


# --------------------------------------------------------------- run_automated

async def test_automated_noop_sin_integracion():
    step = StepDef(name="x", payload={"a": 1})
    out = await run_automated(step, None, {})
    assert out["mode"] == "noop"
    assert out["payload"] == {"a": 1}


async def test_automated_noop_integracion_mock():
    step = StepDef(name="x")
    integ = IntegrationDef(name="i", config={"type": "mock"})
    out = await run_automated(step, integ, {})
    assert out["mode"] == "noop"


async def test_automated_tipo_no_soportado_lanza():
    step = StepDef(name="x")
    integ = IntegrationDef(name="i", config={"type": "kafka"})
    with pytest.raises(StepExecutionError):
        await run_automated(step, integ, {})


# --------------------------------------------------------------- REST (mock httpx)

class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _install_fake_httpx(monkeypatch, resp, capture):
    class _Client:
        def __init__(self, **kwargs):
            capture["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, method, path, **kw):
            capture["method"] = method
            capture["path"] = path
            capture.update(kw)
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


async def test_rest_ok_resuelve_env_y_payload(monkeypatch):
    monkeypatch.setenv("LMS_URL", "https://lms.example")
    cap: dict[str, Any] = {}
    _install_fake_httpx(monkeypatch, _FakeResp(200, {"credential_id": "c1"}), cap)

    step = StepDef(name="crear", type="automated", method="POST", path="/api/cred",
                   payload={"nino_id": Ref(("payload", "nino_id"))})
    integ = IntegrationDef(name="lms",
                           config={"type": "rest", "base_url": "${env.LMS_URL}"})

    out = await run_automated(step, integ, {"payload": {"nino_id": "n1"}})

    assert out == {"ok": True, "status_code": 200, "body": {"credential_id": "c1"}}
    assert cap["init"]["base_url"] == "https://lms.example"   # ${env.LMS_URL} resuelto
    assert cap["method"] == "POST"
    assert cap["path"] == "/api/cred"
    assert cap["json"] == {"nino_id": "n1"}


async def test_rest_4xx_lanza(monkeypatch):
    _install_fake_httpx(monkeypatch, _FakeResp(500, text="boom"), {})
    step = StepDef(name="x", type="automated", method="POST", path="/y")
    integ = IntegrationDef(name="i", config={"type": "rest", "base_url": "http://h"})
    with pytest.raises(StepExecutionError):
        await run_automated(step, integ, {})


# ------------------------------------------- clasificación transitorio vs permanente
# Solo los transitorios se reintentan (ver ExecutionEngine._run_step).

def _rest_step_e_integracion():
    step = StepDef(name="x", type="automated", method="POST", path="/y")
    integ = IntegrationDef(name="i", config={"type": "rest", "base_url": "http://h"})
    return step, integ


@pytest.mark.parametrize("status", [500, 502, 503, 408, 429])
async def test_rest_status_transitorio_es_retryable(monkeypatch, status):
    _install_fake_httpx(monkeypatch, _FakeResp(status, text="boom"), {})
    step, integ = _rest_step_e_integracion()
    with pytest.raises(RetryableStepError):
        await run_automated(step, integ, {})


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_rest_status_permanente_no_es_retryable(monkeypatch, status):
    _install_fake_httpx(monkeypatch, _FakeResp(status, text="mal request"), {})
    step, integ = _rest_step_e_integracion()
    with pytest.raises(StepExecutionError) as exc_info:
        await run_automated(step, integ, {})
    assert not isinstance(exc_info.value, RetryableStepError)


async def test_rest_error_de_red_es_retryable(monkeypatch):
    """Timeout / conexión rechazada: el otro lado puede estar de vuelta en 2s."""
    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, method, path, **kw):
            raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    step, integ = _rest_step_e_integracion()
    with pytest.raises(RetryableStepError):
        await run_automated(step, integ, {})


def _install_smtp_que_falla(monkeypatch, exc):
    class _SMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def send_message(self, msg):
            raise exc

    monkeypatch.setattr(smtplib, "SMTP", _SMTP)


async def test_smtp_4xx_es_retryable(monkeypatch):
    """4xx SMTP = transitorio (greylisting, mailbox llena)."""
    _install_smtp_que_falla(
        monkeypatch, smtplib.SMTPResponseException(451, b"try again"))
    step = StepDef(name="n", type="notification", channel="email", to="a@x.com")
    integ = IntegrationDef(name="mail", config={"type": "smtp", "host": "h"})
    with pytest.raises(RetryableStepError):
        await run_notification(step, integ, {})


async def test_smtp_5xx_es_permanente(monkeypatch):
    """5xx SMTP = el mail no existe / rechazado: reintentar no lo arregla."""
    _install_smtp_que_falla(
        monkeypatch, smtplib.SMTPResponseException(550, b"no such user"))
    step = StepDef(name="n", type="notification", channel="email", to="a@x.com")
    integ = IntegrationDef(name="mail", config={"type": "smtp", "host": "h"})
    with pytest.raises(StepExecutionError) as exc_info:
        await run_notification(step, integ, {})
    assert not isinstance(exc_info.value, RetryableStepError)


# --------------------------------------------------------------- notification

async def test_notification_logged_sin_integracion():
    step = StepDef(name="n", type="notification", channel="email",
                   to="cli-1", template="Hola {payload.nombre}")
    out = await run_notification(step, None, {"payload": {"nombre": "Ana"}})
    assert out["mode"] == "logged"
    assert out["to"] == "cli-1"
    assert out["body"] == "Hola Ana"


async def test_notification_email_smtp(monkeypatch):
    sent: dict[str, Any] = {}

    class _SMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["body"] = msg.get_content().strip()

    monkeypatch.setattr(smtplib, "SMTP", _SMTP)
    step = StepDef(name="n", type="notification", channel="email",
                   to="ana@x.com", template="Bienvenida")
    integ = IntegrationDef(name="mail",
                           config={"type": "smtp", "host": "smtp.x", "port": 25})

    out = await run_notification(step, integ, {})

    assert out == {"ok": True, "channel": "email", "to": "ana@x.com"}
    assert sent["host"] == "smtp.x"
    assert sent["to"] == "ana@x.com"
    assert sent["body"] == "Bienvenida"


# --------------------------------------------------- clasificación de errores de transporte
#
# `httpx.HTTPError` es la clase base de todo: el `except` que la atrapaba y levantaba
# RetryableStepError gastaba los reintentos completos en errores que nunca van a andar.
# Medido en un stack levantado: un base_url vacío daba UnsupportedProtocol y el step reportaba
# "agotó 4 intentos", que se lee como integración intermitente y no como config mal puesta.


@pytest.mark.parametrize("exc", [
    httpx.UnsupportedProtocol("sin esquema"),
    httpx.LocalProtocolError("request mal armado de este lado"),
])
def test_un_request_mal_armado_no_gasta_reintentos(exc):
    assert not is_retryable_transport_error(exc)


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("conexión rechazada"),
    httpx.ReadTimeout("tardó demasiado"),
    httpx.RemoteProtocolError("el otro lado cortó raro"),
])
def test_los_fallos_de_red_si_son_transitorios(exc):
    assert is_retryable_transport_error(exc)


@pytest.mark.asyncio
async def test_una_base_url_sin_protocolo_falla_permanente(monkeypatch):
    """El caso exacto que dejó una instancia FAILED tras 4 intentos.

    Acá la base_url viene literal (no por ${env.X}) para probar la clasificación del transporte
    y no la resolución de variables, que ya tiene sus propios tests.
    """
    step = StepDef(name="crear_credenciales_lms", type="automated", path="/api/credentials")
    integration = IntegrationDef(name="lms", config={"type": "rest", "base_url": ""})

    with pytest.raises(StepExecutionError) as err:
        await run_automated(step, integration, {})

    assert not isinstance(err.value, RetryableStepError), (
        "una URL sin protocolo no se arregla reintentando"
    )
