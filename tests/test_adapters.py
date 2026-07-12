"""Tests unitarios de los adapters de steps (REST / SMTP / noop / notification).

Sin infraestructura: httpx y smtplib se mockean. Cubre casos felices y de error.
"""
import pytest

from teleflow.dsl.ast_nodes import IntegrationDef, Ref, StepDef
from teleflow.executor_service import adapters
from teleflow.executor_service.adapters import (
    StepExecutionError,
    eval_payload,
    render_template,
    resolve_env,
    run_automated,
    run_notification,
)


# --------------------------------------------------------------- helpers puros

def test_resolve_env(monkeypatch):
    monkeypatch.setenv("TOKEN", "secret")
    assert resolve_env("Bearer ${env.TOKEN}") == "Bearer secret"
    assert resolve_env("${env.NO_EXISTE}") == ""      # faltante -> ""
    assert resolve_env(123) == 123                     # no-str pasa igual


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

    monkeypatch.setattr(adapters.httpx, "AsyncClient", _Client)


async def test_rest_ok_resuelve_env_y_payload(monkeypatch):
    monkeypatch.setenv("LMS_URL", "https://lms.example")
    cap: dict = {}
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


# --------------------------------------------------------------- notification

async def test_notification_logged_sin_integracion():
    step = StepDef(name="n", type="notification", channel="email",
                   to="cli-1", template="Hola {payload.nombre}")
    out = await run_notification(step, None, {"payload": {"nombre": "Ana"}})
    assert out["mode"] == "logged"
    assert out["to"] == "cli-1"
    assert out["body"] == "Hola Ana"


async def test_notification_email_smtp(monkeypatch):
    sent: dict = {}

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

    monkeypatch.setattr(adapters.smtplib, "SMTP", _SMTP)
    step = StepDef(name="n", type="notification", channel="email",
                   to="ana@x.com", template="Bienvenida")
    integ = IntegrationDef(name="mail",
                           config={"type": "smtp", "host": "smtp.x", "port": 25})

    out = await run_notification(step, integ, {})

    assert out == {"ok": True, "channel": "email", "to": "ana@x.com"}
    assert sent["host"] == "smtp.x"
    assert sent["to"] == "ana@x.com"
    assert sent["body"] == "Bienvenida"
