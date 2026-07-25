"""Criterio compartido de transitorio vs permanente, y backoff con full jitter.

Vive en `common\\` y no en un servicio porque lo usan varios: los adapters del executor
(steps REST/SMS/AMQP) y el composer (llamadas al proveedor LLM). Tener el criterio dos veces
es tenerlo mal una vez: la segunda copia se olvida cuando la primera cambia.

Ver el ADR de clasificación de errores de integración (2026-07-14).
"""
import random

# 408 Request Timeout y 429 Too Many Requests son transitorios pese a ser 4xx.
RETRYABLE_STATUS = frozenset({408, 429})


def is_retryable_status(status_code: int) -> bool:
    """5xx = el otro lado está roto ahora; 4xx = el request está mal (salvo 408/429)."""
    return status_code >= 500 or status_code in RETRYABLE_STATUS


def full_jitter_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Backoff exponencial con full jitter: evita que N clientes reintenten al unísono.

    `attempt` es 0-based. El jitter va sobre **todo** el intervalo (no la mitad): con
    reintentos sincronizados, el pico coordinado es peor que la espera promedio más larga.
    """
    ceiling = min(base_delay * float(2 ** attempt), max_delay)
    return random.uniform(0, ceiling)
