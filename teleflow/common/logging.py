"""Logging estructurado JSON con structlog.

Convención: siempre que exista, incluir instance_id, flow_name y step_name
en los eventos de log (se pasan como kwargs en cada llamada).
"""
import logging
import sys

import structlog


def setup_logging(service_name: str) -> structlog.stdlib.BoundLogger:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger(service=service_name)


def get_logger(**initial_values: object) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(**initial_values)
