"""Criterio compartido de transitorio vs permanente, y backoff con full jitter.

Vive en `common\\` y no en un servicio porque lo usan varios: los adapters del executor
(steps REST/SMS/AMQP) y el composer (llamadas al proveedor LLM). Tener el criterio dos veces
es tenerlo mal una vez: la segunda copia se olvida cuando la primera cambia.

Ver el ADR de clasificación de errores de integración (2026-07-14).
"""
import random

# 408 Request Timeout y 429 Too Many Requests son transitorios pese a ser 4xx.
RETRYABLE_STATUS = frozenset({408, 429})

# Errores de transporte de httpx que **nunca** van a salir bien reintentando, porque el request
# está mal armado de este lado. `httpx.HTTPError` es la clase base de todo, así que atraparla y
# tratarla como transitoria —lo que se hacía— gastaba reintentos en errores de configuración.
# Medido: un `base_url` vacío daba `UnsupportedProtocol` y consumía 4 intentos con backoff, y el
# operador leía "agotó 4 intentos", que suena a integración intermitente y no a config mal puesta.
PERMANENT_TRANSPORT_ERRORS = frozenset({
    "UnsupportedProtocol",   # falta el esquema http:// — base_url vacía o mal escrita
    "InvalidURL",            # la URL no es parseable
    "LocalProtocolError",    # este lado violó el protocolo: bug o config, no red
})


def is_retryable_status(status_code: int) -> bool:
    """5xx = el otro lado está roto ahora; 4xx = el request está mal (salvo 408/429)."""
    return status_code >= 500 or status_code in RETRYABLE_STATUS


def is_retryable_transport_error(exc: BaseException) -> bool:
    """Un error de transporte es transitorio salvo que el request esté mal armado acá.

    Se mira el **nombre** de la clase y no se importa httpx: este módulo vive en `common\\` y lo
    usan el executor y el composer; atarlo a la jerarquía de un cliente HTTP concreto sería
    meterle una dependencia al criterio compartido.
    """
    return type(exc).__name__ not in PERMANENT_TRANSPORT_ERRORS


def full_jitter_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Backoff exponencial con full jitter: evita que N clientes reintenten al unísono.

    `attempt` es 0-based. El jitter va sobre **todo** el intervalo (no la mitad): con
    reintentos sincronizados, el pico coordinado es peor que la espera promedio más larga.
    """
    ceiling = min(base_delay * float(2 ** attempt), max_delay)
    return random.uniform(0, ceiling)
