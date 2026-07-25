"""Tests del composer: que no mienta sobre qué proveedor generó el borrador.

Antes, `LLM_PROVIDER=anthropic` sin credencial devolvía el `StubProvider` con un `warning`:
`POST /compose` respondía 201, el analista recibía un esqueleto con `TODO:` creyendo que lo
había generado el modelo, y el log registraba el proveedor *pedido*. Estos tests fijan que
el stub solo aparece cuando se lo pide explícitamente.
"""
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.common.config import Settings
from teleflow.composer_service.main import _validate_source
from teleflow.composer_service.providers import (
    AnthropicProvider,
    LLMConfigurationError,
    OllamaProvider,
    OpenAIProvider,
    StubProvider,
    get_provider,
)

ROOT = Path(__file__).resolve().parent.parent


def _settings(provider, api_key=""):
    """Settings explícitas: los kwargs ganan sobre el `.env` que pueda existir en el repo."""
    return Settings(llm_provider=provider, llm_api_key=api_key)


# ------------------------------------------- el stub solo si se lo pide

@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_proveedor_real_sin_credencial_levanta(provider):
    with pytest.raises(LLMConfigurationError) as exc:
        get_provider(_settings(provider))

    mensaje = str(exc.value)
    assert "LLM_API_KEY" in mensaje
    # El error tiene que decir cómo salir, no solo qué falta.
    assert "stub" in mensaje


@pytest.mark.parametrize("provider", ["anthropic", "openai", "ollama"])
def test_ningun_proveedor_real_devuelve_el_stub(provider):
    """La regresión que importa: pedir un LLM real y recibir el esqueleto de mentira."""
    try:
        instancia = get_provider(_settings(provider, api_key="k"))
    except LLMConfigurationError:
        return  # falló explícitamente, que es el otro final aceptable
    assert not isinstance(instancia, StubProvider)
    assert instancia.name == provider


def test_stub_solo_cuando_se_lo_pide():
    instancia = get_provider(_settings("stub"))
    assert isinstance(instancia, StubProvider)
    assert instancia.name == "stub"


# ------------------------------------------- construcción de cada proveedor

def test_anthropic_con_credencial():
    assert isinstance(get_provider(_settings("anthropic", api_key="k")), AnthropicProvider)


def test_openai_con_credencial():
    assert isinstance(get_provider(_settings("openai", api_key="k")), OpenAIProvider)


def test_ollama_no_necesita_credencial():
    """Self-hosted: la credencial no aplica, así que su ausencia no puede ser un error."""
    assert isinstance(get_provider(_settings("ollama")), OllamaProvider)


@pytest.mark.parametrize("valor", ["  Anthropic ", "STUB", "OpenAI"])
def test_el_valor_se_normaliza(valor):
    """Un `LLM_PROVIDER` con mayúsculas o espacios no puede caer en 'desconocido'."""
    instancia = get_provider(_settings(valor, api_key="k"))
    assert instancia.name == valor.strip().lower()


@pytest.mark.parametrize("typo", ["antropic", "gpt", "claude", ""])
def test_proveedor_desconocido_levanta(typo):
    """Un typo antes devolvía el stub sin siquiera loguear un warning."""
    with pytest.raises(LLMConfigurationError) as exc:
        get_provider(_settings(typo, api_key="k"))
    assert "no es un proveedor conocido" in str(exc.value)


# ------------------------------------------- validación del borrador contra el parser

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Reemplaza a `httpx.AsyncClient`: devuelve un payload fijo o levanta."""

    def __init__(self, resultado):
        self._resultado = resultado

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        if isinstance(self._resultado, Exception):
            raise self._resultado
        return _FakeResponse(self._resultado)


def _parser_responde(monkeypatch, resultado):
    """`resultado` es el payload que devuelve el parser, o la excepción que levanta."""
    import httpx

    # `main` hace `import httpx` y usa `httpx.AsyncClient`, así que alcanza con el módulo.
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient(resultado))


async def test_borrador_que_compila_queda_marcado_ok(monkeypatch):
    _parser_responde(monkeypatch, {"valid": True, "issues": []})
    validation = await _validate_source("process \"x\" {}", "x")

    assert validation["parses"] is True
    assert validation["issues"] == []
    assert validation["checked_at"]


async def test_borrador_que_no_compila_se_marca_pero_no_levanta(monkeypatch):
    """No se rechaza: la generación ya se pagó y suele estar a dos líneas de compilar."""
    issues = [{"level": "error", "message": "falta '}'", "block": "syntax"}]
    _parser_responde(monkeypatch, {"valid": False, "issues": issues})
    validation = await _validate_source("process \"x\" {", "x")

    assert validation["parses"] is False
    assert validation["issues"] == issues


async def test_parser_caido_no_se_confunde_con_compila(monkeypatch):
    """`parses: None` es "no se pudo verificar", que no es lo mismo que "compila"."""
    import httpx

    _parser_responde(monkeypatch, httpx.ConnectError("parser caído"))
    validation = await _validate_source("process \"x\" {}", "x")

    assert validation["parses"] is None  # ni True ni False
    assert "error" in validation


async def test_un_bug_nuestro_no_se_disfraza_de_parser_caido(monkeypatch):
    """Solo transporte y respuesta ilegible se absorben; el resto tiene que propagarse."""
    _parser_responde(monkeypatch, RuntimeError("bug nuestro"))

    with pytest.raises(RuntimeError):
        await _validate_source("process \"x\" {}", "x")


class _FakeSession:
    """Lo mínimo que usa `compose`: acumular y confirmar."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


async def test_compose_guarda_el_borrador_marcado(monkeypatch):
    """Que `_validate_source` funcione no sirve si `compose` no la llama.

    Verifica el camino completo: el borrador que se persiste lleva el proveedor que lo
    generó y el resultado del parser, y ambos viajan en la respuesta.
    """
    from teleflow.common.config import get_settings
    from teleflow.composer_service.main import ComposeRequest, compose

    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    _parser_responde(monkeypatch, {"valid": False, "issues": [{"level": "error",
                                                              "message": "falta '}'",
                                                              "block": "syntax"}]})
    session = _FakeSession()
    try:
        salida = await compose(
            ComposeRequest(name="alta_socio", description="alta de socio"),
            session=cast(AsyncSession, session),
        )
    finally:
        get_settings.cache_clear()

    draft = session.added[0]
    assert draft.provider == "stub"
    assert draft.validation["parses"] is False
    assert salida["provider"] == "stub"
    assert salida["validation"]["issues"][0]["message"] == "falta '}'"


# ------------------------------------------- el cableado, no solo la función

def test_el_servicio_no_arranca_sin_credencial(monkeypatch):
    """Que `get_provider` levante no sirve si nadie lo llama al arrancar.

    Verifica el camino completo: `lifespan` construye el proveedor, así que el contenedor
    falla en el `up` y no sirviendo 201 mentirosos.
    """
    from fastapi.testclient import TestClient

    from teleflow.common.config import get_settings
    from teleflow.composer_service.main import app

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(LLMConfigurationError):
            with TestClient(app):
                pass  # pragma: no cover — el startup no debería llegar acá
    finally:
        get_settings.cache_clear()


# ------------------------------------------- guard del .env.example

def test_env_example_arranca_sin_credenciales():
    """Un clon nuevo del repo tiene que poder levantar el stack sin conseguir una API key.

    Con `LLM_PROVIDER` real y `LLM_API_KEY` vacía, `composer-service` ya no arranca — así que
    esa combinación en el ejemplo dejaría el stack roto de fábrica.
    """
    lineas = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    valores = dict(
        linea.split("=", 1) for linea in lineas
        if "=" in linea and not linea.strip().startswith("#")
    )
    provider = valores.get("LLM_PROVIDER", "").strip()
    api_key = valores.get("LLM_API_KEY", "").strip()

    if not api_key:
        assert provider in ("stub", ""), (
            f".env.example trae LLM_PROVIDER={provider!r} sin LLM_API_KEY: "
            f"composer-service no arrancaría en un clon nuevo."
        )
