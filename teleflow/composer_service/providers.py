"""Abstracción LLM (ADR-003): el proveedor es una variable de entorno.

LLM_PROVIDER = anthropic | openai | ollama | stub
El cambio de proveedor es configuración, no código.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger

log = get_logger(component="llm-provider")

DSL_SYSTEM_PROMPT = '''Sos un experto en TeleFlow DSL v2, un lenguaje declarativo \
para modelar procesos de negocio. Generás archivos .tflow sintácticamente válidos.

Bloques disponibles: entity, relation, rule, view360, process, step, integration.

Reglas del lenguaje:
- Los nombres de bloques van entre comillas: entity "nino" { ... }
- entity: description, fields { nombre: string required }, lifecycle { initial: "X" \
states ["X","Y"] transitions { X -> Y via "accion" } }, events { on_transition \
"accion" emit "evento.nombre" }, invariants { "expr" }
- Tipos de campo: string, number, date, datetime, bool, enum["a","b"]. \
Modificadores: required, optional, unique, default(v), range(a,b)
- relation: from: entity.x  to: entity.y  cardinality: "many_to_many" + lifecycle, \
fields, events
- rule: on_event: "evento" | on_timer { after: 30 days since: "evento" condition: \
expr } + condition, execute: process.nombre, with { clave: expr }
- process: stage "nombre" { mode: sequential steps [step.a, step.b] }, \
on_complete { emit "evento" }
- step: type: automated | human_task | decision | notification. human_task lleva \
signals ["approve","reject"]. notification lleva channel: "email" y template.
- integration: type: "rest", base_url: "${env.VAR}" — credenciales SIEMPRE por env.

Respondé SOLO con el contenido del archivo .tflow, sin explicaciones ni markdown.'''


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str: ...


class AnthropicProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model or "claude-fable-5"
        self._base_url = settings.llm_base_url or "https://api.anthropic.com"

    async def generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self._model,
                    "max_tokens": 4096,
                    "system": DSL_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        response.raise_for_status()
        data = response.json()
        return str(data["content"][0]["text"])


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model or "gpt-4o"
        self._base_url = settings.llm_base_url or "https://api.openai.com"

    async def generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self._base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": DSL_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])


class OllamaProvider(LLMProvider):
    """Modelo self-hosted (p.ej. requisito regulatorio de datos en territorio)."""

    def __init__(self, settings: Settings):
        self._model = settings.llm_model or "llama3.1"
        self._base_url = settings.llm_base_url or "http://ollama:11434"

    async def generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": DSL_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        response.raise_for_status()
        data = response.json()
        return str(data["message"]["content"])


class StubProvider(LLMProvider):
    """Sin LLM configurado: genera un esqueleto comentado para editar a mano.

    Permite probar el ciclo compose → review → deploy sin credenciales.
    """

    async def generate(self, prompt: str) -> str:
        commented = "\n".join(f"// {line}" for line in prompt.strip().splitlines())
        return f'''// Borrador generado en modo stub (sin LLM configurado).
// Pedido del analista:
{commented}

process "proceso_borrador" {{
  description: "TODO: completar según el pedido de arriba"

  stage "principal" {{
    mode: sequential
    steps [step.paso_inicial]
  }}

  on_complete {{
    emit "proceso_borrador.completado"
  }}
}}

step "paso_inicial" {{
  description: "TODO: reemplazar por el paso real"
  type: automated
}}
'''


def get_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "anthropic" and settings.llm_api_key:
        return AnthropicProvider(settings)
    if provider == "openai" and settings.llm_api_key:
        return OpenAIProvider(settings)
    if provider == "ollama":
        return OllamaProvider(settings)
    if provider in ("anthropic", "openai"):
        log.warning("llm_api_key_missing_using_stub", provider=provider)
    return StubProvider()
