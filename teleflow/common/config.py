"""Configuración compartida de todos los servicios TeleFlow."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "teleflow"

    # Infraestructura de datos
    database_url: str = "postgresql+asyncpg://teleflow:teleflow@localhost:5432/teleflow"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://teleflow:teleflow@localhost:5672/"

    # Auth
    teleflow_api_key: str = "dev-key-change-me"
    # Permisos de la key global. `*` = todos (default: no rompe instalaciones existentes).
    # Restringir es una decisión explícita del operador, p.ej. para una integración que solo
    # lee: `TELEFLOW_API_KEY_SCOPES=entities:read,instances:read`.
    # Scopes válidos: ver teleflow/gateway/auth.py
    teleflow_api_key_scopes: str = "*"
    # Las demás keys viven en la tabla `api_keys` (una por integración, hasheadas).
    # El TTL del cache es también la ventana máxima que sobrevive una key revocada.
    api_key_cache_ttl: int = 30

    # URLs internas entre servicios
    parser_url: str = "http://parser-service:8001"
    registry_url: str = "http://registry-service:8003"
    executor_url: str = "http://executor-service:8002"
    composer_url: str = "http://composer-service:8004"
    gateway_url: str = "http://api-gateway:8000"

    # Capa IA (ADR-003)
    llm_provider: str = "stub"  # anthropic | openai | ollama | stub
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    # Techo de tokens de la respuesta. Un `.tflow` completo entra holgado en 4096; subirlo
    # tiene sentido para flows grandes. Si la respuesta se corta, el composer lo dice en vez
    # de guardar un borrador truncado.
    llm_max_tokens: int = 4096
    # Reintentos ante fallos **transitorios** del proveedor (5xx, 408, 429, red). Lo
    # permanente (4xx, credencial mala) falla en el primer intento.
    llm_retry_attempts: int = 3
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 20.0

    # Executor
    worker_concurrency: int = 10
    timer_scan_interval: int = 60
    domain_cache_ttl: int = 30
    # Cada cuánto se recalculan los gauges de negocio (instancias vivas, backlog de
    # human_tasks). Es una agregación sobre el working set de `process_instances`, no sobre
    # toda la historia. Prometheus scrapea cada 15 s: bajar de eso no agrega resolución.
    business_metrics_interval: int = 30
    # Segundos que vale el derecho a ejecutar una instancia. El dueño lo renueva mientras
    # trabaja; si el proceso muere, otra réplica puede tomarla recién cuando vence. Bajarlo
    # acelera la recuperación tras una caída y sube el riesgo de que una renovación demorada
    # (GC, DB lenta) deje que otro se la lleve; subirlo, al revés.
    instance_lease_seconds: int = 60
    events_exchange: str = "teleflow.domain.events"

    # Bus de eventos: reintentos antes de mandar el evento a la DLQ (<queue>.dlq).
    # La cola lleva sufijo de versión: cambiar sus argumentos (x-dead-letter-exchange)
    # sobre una cola ya declarada da PRECONDITION_FAILED en RabbitMQ.
    rules_queue: str = "teleflow.rules.v1"
    event_max_attempts: int = 3
    event_retry_base_delay: float = 1.0

    # Reintentos de steps: cuántos los decide el DSL (`retries:` del step); acá van
    # los tiempos. Backoff exponencial con full jitter, topeado a max_delay.
    # Solo se reintentan errores transitorios (5xx/408/429/timeout/red).
    step_retry_base_delay: float = 1.0
    step_retry_max_delay: float = 30.0

    # Gateway
    rate_limit_rpm: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
