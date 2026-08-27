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

DSL_SYSTEM_PROMPT = '''Generás archivos .tflow del lenguaje TeleFlow DSL v2, que modela procesos de negocio. Respondé SOLO con el contenido del archivo: sin explicaciones, sin markdown, sin ```.

REGLAS DE SINTAXIS QUE SE VIOLAN SEGUIDO — leelas antes de escribir:
- Los nombres van entre comillas: entity "cliente" { ... }  NUNCA entity cliente { ... }
- `states` y `steps` llevan corchetes SIN dos puntos: states ["A", "B"] · steps [step.uno]
- Las transiciones NO llevan dos puntos ni comas: A -> B via "accion"
- Los steps se declaran ARRIBA, al nivel del archivo, y se referencian con step.nombre.
  NUNCA se define un step adentro de un stage.
- `from:` y `to:` de una relation apuntan a entity.nombre, no a estados.
- Todo identificador en minúsculas con guion bajo: reclamo_tecnico, no ReclamoTecnico.
- Un `process` solo lleva input, stage y on_complete. Nada más.

EJEMPLO COMPLETO Y VÁLIDO — copiá esta estructura exactamente:

entity "socio" {
  description: "Persona asociada al club"
  fields {
    cedula:   string required unique
    nombre:   string required
    email:    string optional
    plan:     enum["mensual", "anual"]
  }
  lifecycle {
    initial: "AL_DIA"
    states ["AL_DIA", "MOROSO", "BAJA"]
    transitions {
      AL_DIA -> MOROSO via "marcar_moroso"
      MOROSO -> AL_DIA via "regularizar"
      AL_DIA -> BAJA   via "dar_de_baja"
    }
  }
  events {
    on_transition "marcar_moroso" emit "socio.moroso"
    on_transition "regularizar"   emit "socio.regularizado"
  }
  invariants {
    "email != null WHEN estado == AL_DIA"
  }
}

rule "gestionar_al_caer_en_mora" {
  on_event: "socio.moroso"
  execute:  process.gestion_cobranza
  with {
    socio_id: event.entity_id
  }
}

process "gestion_cobranza" {
  description: "Gestiona la deuda de un socio moroso"
  input {
    socio_id: string required
  }
  stage "aviso" {
    mode: parallel
    steps [step.enviar_recordatorio, step.registrar_gestion]
  }
  stage "espera_pago" {
    mode: sequential
    steps [step.confirmar_pago]
  }
  stage "decidir" {
    mode: decision
    steps []
    when signals.confirmar_pago.signal == "approve" -> stage.cierre
    else -> stage.derivacion
  }
  stage "cierre" {
    mode: sequential
    steps [step.notificar_cierre]
  }
  stage "fin" {
    mode: decision
    steps []
    else -> stage.end
  }
  stage "derivacion" {
    mode: sequential
    steps [step.notificar_derivacion]
  }
  on_complete {
    emit "cobranza.finalizada"
  }
}

step "enviar_recordatorio" {
  type: notification
  channel: "email"
  to: payload.socio_id
  template: "Tenés una cuota pendiente."
}

step "registrar_gestion" {
  description: "Deja constancia de la gestión"
  type: automated
  retries: 2
}

step "confirmar_pago" {
  description: "Un cobrador confirma si el socio pagó"
  type: human_task
  assignee: "rol:cobranzas"
  signals ["approve", "reject"]
  timeout: 5 days
}

step "notificar_cierre" {
  type: notification
  channel: "email"
  to: payload.socio_id
  template: "Tu deuda quedó saldada."
}

step "notificar_derivacion" {
  type: notification
  channel: "email"
  to: payload.socio_id
  template: "Derivamos tu caso al área legal."
}

NOTAS SOBRE EL EJEMPLO:
- Un stage `decision` compara una señal y ramifica. Fijate el stage "fin": después de la
  rama buena hace falta un decision con `else -> stage.end` para terminar el proceso.
- Un paso que espera a una persona es type: human_task con signals ["approve", "reject"].
- Tipos de campo: string, number, date, datetime, bool, enum["a","b"].
  Modificadores: required, optional, unique, default(v), range(a,b).
- Bloques disponibles: entity, relation, rule, process, step, integration, view360.
- integration: type: "rest", base_url: "${env.VAR}". Las credenciales van SIEMPRE por
  variable de entorno; nunca escribas un token, una clave ni una password en el .tflow.

Ahora generá el .tflow para el pedido del analista, siguiendo esa estructura.'''


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
        except httpx.ReadTimeout as exc:
            # Un timeout de **lectura** no es un fallo transitorio: el proveedor recibió el
            # pedido y estuvo generando todo ese tiempo. Reintentar arranca la generación de
            # cero y vuelve a esperar el timeout completo, así que solo garantiza pasarse
            # también del techo de quien nos llama — y el analista termina esperando el doble
            # para recibir el mismo error. Falla en el primer intento y lo dice.
            #
            # `str(ReadTimeout)` suele ser vacío, así que el mensaje lo ponemos nosotros: "error
            # de red: " a secas no le sirve a nadie para saber qué pasó.
            raise LLMTransientError(
                f"el proveedor no respondió en {timeout:.0f} s. Si es un modelo self-hosted en "
                f"CPU puede estar simplemente tardando más que eso; probá con un pedido más "
                f"corto o subí el timeout."
            ) from exc
        except httpx.HTTPError as exc:  # DNS, conexión rechazada, TLS, timeout de conexión
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
            # 10 minutos. Un modelo self-hosted en CPU no tiene un tiempo de respuesta
            # acotado: depende del tamaño del prompt y de qué más esté corriendo en la
            # máquina. Con 300 s se midieron generaciones de 238 s y 272 s —dentro, pero
            # raspando— y una que se pasó y devolvió un 502 sobre un servicio que estaba
            # trabajando bien. El costo de esperar de más es que alguien espera; el de cortar
            # de menos es tirar a la basura minutos de cómputo ya gastados.
            timeout=600,
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
