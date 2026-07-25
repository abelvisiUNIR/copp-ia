"""Abstracción LLM (ADR-003): el proveedor es una variable de entorno.

LLM_PROVIDER = anthropic | openai | ollama | stub
El cambio de proveedor es configuración, no código.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger
from teleflow.common.retry import full_jitter_delay, is_retryable_status

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


class LLMRequestRejected(RuntimeError):
    """El proveedor rechazó el pedido: reintentar el mismo prompt no lo va a arreglar.

    Un 4xx de contenido, o el modelo declinando la generación. Es responsabilidad del
    pedido, no de la instalación → el analista puede reformular.
    """


class LLMTransientError(RuntimeError):
    """Falló de forma transitoria y se agotaron los reintentos (5xx, 429, timeout, red)."""


class LLMProvider(ABC):
    #: Nombre del proveedor que realmente corrió. Es lo que va al log y a la respuesta —
    #: `settings.llm_provider` dice lo que se *pidió*, que no siempre es lo mismo.
    name: str

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...


def _retry_after(response: httpx.Response) -> float | None:
    """Un 429 suele venir con `retry-after`: si el proveedor dice cuánto esperar, se le cree."""
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # también admite fecha HTTP; no vale complicarse por eso


async def _post_json(url: str, *, headers: dict[str, str], payload: dict[str, Any],
                     timeout: float, settings: Settings) -> dict[str, Any]:
    """POST al proveedor, reintentando **solo** lo transitorio.

    Usa el mismo criterio que los adapters del executor (`common.retry`): 5xx, 408 y 429 son
    transitorios; el resto de los 4xx no. Antes, `raise_for_status()` + `except Exception`
    convertía todo en 502 sin reintentar nada: un 429 (que se resuelve esperando) se trataba
    igual que un 400 (que no).
    """
    attempts = max(1, settings.llm_retry_attempts)
    ultimo = "sin detalle"

    for attempt in range(attempts):
        espera: float | None = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:  # timeout, DNS, conexión rechazada, TLS
            ultimo = f"error de red: {exc}"
        else:
            if response.status_code < 400:
                data: Any = response.json()
                if not isinstance(data, dict):
                    raise LLMRequestRejected(
                        f"el proveedor devolvió {type(data).__name__} y no un objeto JSON")
                return data

            detalle = f"{response.status_code}: {response.text[:500]}"
            if response.status_code in (401, 403):
                raise LLMConfigurationError(
                    f"el proveedor rechazó la credencial ({detalle}). Revisá LLM_API_KEY.")
            if response.status_code == 404:
                raise LLMConfigurationError(
                    f"el proveedor no conoce el modelo o la ruta ({detalle}). "
                    f"Revisá LLM_MODEL y LLM_BASE_URL.")
            if not is_retryable_status(response.status_code):
                raise LLMRequestRejected(detalle)
            ultimo = detalle
            espera = _retry_after(response)

        if attempt + 1 < attempts:
            if espera is None:
                espera = full_jitter_delay(attempt, settings.llm_retry_base_delay,
                                           settings.llm_retry_max_delay)
            espera = min(espera, settings.llm_retry_max_delay)
            log.warning("llm_retry", attempt=attempt + 1, of=attempts,
                        delay=round(espera, 2), error=ultimo)
            await asyncio.sleep(espera)

    raise LLMTransientError(f"agotados {attempts} intentos contra el proveedor — {ultimo}")


def _texto_o_error(texto: str, *, truncado: bool, motivo: str) -> str:
    """Un borrador cortado a la mitad no es un borrador: lo dice en vez de guardarlo."""
    if truncado:
        raise LLMConfigurationError(
            "la respuesta del modelo se cortó por límite de tokens: subí LLM_MAX_TOKENS "
            f"(actual insuficiente para este flow). motivo={motivo}")
    if not texto.strip():
        raise LLMRequestRejected(
            f"el modelo no devolvió texto (motivo={motivo}). Probá reformular el pedido.")
    return texto


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model or "claude-fable-5"
        self._base_url = settings.llm_base_url or "https://api.anthropic.com"

    async def generate(self, prompt: str) -> str:
        data = await _post_json(
            f"{self._base_url}/v1/messages",
            headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
            payload={
                "model": self._model,
                "max_tokens": self._settings.llm_max_tokens,
                "system": DSL_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
            settings=self._settings,
        )
        motivo = str(data.get("stop_reason") or "")
        # Un rechazo por políticas llega como **200** con `stop_reason: refusal` y sin texto.
        # Leer `content[0]["text"]` a ciegas reventaba con un IndexError que se reportaba como
        # "error del proveedor": el analista no tenía forma de saber que podía reformular.
        if motivo == "refusal":
            raise LLMRequestRejected(
                "el modelo declinó generar esto (stop_reason=refusal). Reformulá el pedido.")
        bloques = [b for b in data.get("content") or [] if b.get("type") == "text"]
        return _texto_o_error("".join(str(b.get("text") or "") for b in bloques),
                              truncado=motivo == "max_tokens",
                              motivo=motivo or "desconocido")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model or "gpt-4o"
        self._base_url = settings.llm_base_url or "https://api.openai.com"

    async def generate(self, prompt: str) -> str:
        data = await _post_json(
            f"{self._base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            payload={
                "model": self._model,
                "max_tokens": self._settings.llm_max_tokens,
                "messages": [
                    {"role": "system", "content": DSL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=120,
            settings=self._settings,
        )
        opciones = data.get("choices") or []
        if not opciones:
            raise LLMRequestRejected("el proveedor devolvió una respuesta sin `choices`")
        motivo = str(opciones[0].get("finish_reason") or "")
        texto = str((opciones[0].get("message") or {}).get("content") or "")
        return _texto_o_error(texto, truncado=motivo == "length",
                              motivo=motivo or "desconocido")


class OllamaProvider(LLMProvider):
    """Modelo self-hosted (p.ej. requisito regulatorio de datos en territorio)."""

    name = "ollama"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model = settings.llm_model or "llama3.1"
        self._base_url = settings.llm_base_url or "http://ollama:11434"

    async def generate(self, prompt: str) -> str:
        data = await _post_json(
            f"{self._base_url}/api/chat",
            headers={},
            payload={
                "model": self._model,
                "stream": False,
                "options": {"num_predict": self._settings.llm_max_tokens},
                "messages": [
                    {"role": "system", "content": DSL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=300,
            settings=self._settings,
        )
        motivo = str(data.get("done_reason") or "")
        texto = str((data.get("message") or {}).get("content") or "")
        return _texto_o_error(texto, truncado=motivo == "length",
                              motivo=motivo or "desconocido")


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
