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

    # Gateway
    rate_limit_rpm: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
