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

    # Executor
    worker_concurrency: int = 10
    timer_scan_interval: int = 60
    domain_cache_ttl: int = 30
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
