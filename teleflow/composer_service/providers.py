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


class LLMConfigurationError(RuntimeError):
    """El proveedor pedido no se puede construir con la configuración actual.

    Se levanta al arrancar el servicio (no al componer): un `.env` mal configurado es un
    error de despliegue y tiene que aparecer en el despliegue.
    """


class LLMProvider(ABC):
    #: Nombre del proveedor que realmente corrió. Es lo que va al log y a la respuesta —
    #: `settings.llm_provider` dice lo que se *pidió*, que no siempre es lo mismo.
    name: str

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...


class AnthropicProvider(LLMProvider):
    name = "anthropic"

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
    name = "openai"

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

    name = "ollama"

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

    Permite probar el ciclo compose → review → deploy sin credenciales. Se usa **solo** con
    `LLM_PROVIDER=stub`: nunca es el resultado de que otro proveedor no se haya podido
    construir (ver `get_provider`).
    """

    name = "stub"

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


#: Proveedores que no pueden funcionar sin credencial. `ollama` es self-hosted y `stub` no
#: llama a nadie, así que ninguno de los dos está acá.
_NEEDS_API_KEY = ("anthropic", "openai")

_VALID_PROVIDERS = ("anthropic", "openai", "ollama", "stub")


def get_provider(settings: Settings) -> LLMProvider:
    """Construye el proveedor pedido, o levanta `LLMConfigurationError`.

    **Nunca cae al `stub` en silencio.** Antes, un `LLM_PROVIDER` real sin credencial
    devolvía el stub con un `warning`: el analista recibía un esqueleto con `TODO:` creyendo
    que lo había generado el modelo, y el log registraba el proveedor *pedido*, así que la
    única traza del incidente decía lo contrario de lo que pasó. Un proveedor mal configurado
    es un error de despliegue: se levanta acá y el servicio no arranca.
    """
    provider = settings.llm_provider.lower().strip()

    if provider not in _VALID_PROVIDERS:
        raise LLMConfigurationError(
            f"LLM_PROVIDER={settings.llm_provider!r} no es un proveedor conocido. "
            f"Válidos: {', '.join(_VALID_PROVIDERS)}."
        )
    if provider in _NEEDS_API_KEY and not settings.llm_api_key:
        raise LLMConfigurationError(
            f"LLM_PROVIDER={provider} requiere LLM_API_KEY y está vacía. "
            f"Configurá la credencial, o poné LLM_PROVIDER=stub para trabajar sin LLM "
            f"(genera esqueletos para editar a mano, no borradores reales)."
        )

    if provider == "anthropic":
        return AnthropicProvider(settings)
    if provider == "openai":
        return OpenAIProvider(settings)
    if provider == "ollama":
        return OllamaProvider(settings)
    return StubProvider()
