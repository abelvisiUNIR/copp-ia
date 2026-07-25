"""Tests del composer: que no mienta sobre qué proveedor generó el borrador.

Antes, `LLM_PROVIDER=anthropic` sin credencial devolvía el `StubProvider` con un `warning`:
`POST /compose` respondía 201, el analista recibía un esqueleto con `TODO:` creyendo que lo
había generado el modelo, y el log registraba el proveedor *pedido*. Estos tests fijan que
el stub solo aparece cuando se lo pide explícitamente.
"""
from pathlib import Path

import pytest

from teleflow.common.config import Settings
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
