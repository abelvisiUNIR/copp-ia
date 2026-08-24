"""metrics-service: publica los gauges de negocio. **Corre en una sola réplica.**

Existe por un bug medido en un cluster real: el scanner vivía en el lifespan del
`executor-service`, que corre con 3 réplicas, y los gauges llevan el **valor absoluto** leído
de la misma tabla. Prometheus scrapea cada pod por separado y el dashboard suma entre pods, así
que todo número de negocio se leía 3×. No fallaba: informaba un backlog de 30 donde había 10.

El primer intento fue sortear un turno por ciclo con un advisory lock de Postgres. **No
funcionó**, y la razón vale recordarla: un lock que se toma y se suelta dentro del ciclo solo
excluye a réplicas cuyos ciclos se **solapan en el tiempo**, y con un ciclo de milisegundos cada
30 s no se solapan nunca. Las tres réplicas obtenían el lock, cada una en su propio horario.
Medido en el cluster: `pg_locks` con `locktype='advisory'` daba 0 en todo momento, y los tres
pods reportaban el mismo valor.

Así que la garantía se mueve a la capa que puede sostenerla: **la topología del despliegue**. Un
componente con una sola réplica no necesita coordinarse con nadie. No hay lock, no hay líder, no
hay failover que escribir — y no hay una segunda forma de equivocarse.

**La contracara, y hay que decirla:** la garantía ahora es que este componente NO se escale. Está
fijado en `replicas: 1` en el chart con el motivo escrito al lado, y en `docker-compose.yml` es
un servicio único. Escalarlo a 2 reintroduce el bug exacto.

Ver el ADR de la wiki "quién publica los gauges de negocio cuando el executor tiene varias
réplicas".
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from teleflow.common.config import get_settings
from teleflow.common.db import db_ping, dispose_db, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.observability import setup_observability
from teleflow.executor_service.business_metrics import BusinessMetricsCollector

log = setup_logging("metrics-service")

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    sessionmaker = init_db(settings)
    business_metrics = BusinessMetricsCollector(sessionmaker, settings)

    # Primer refresh en el arranque: sin esto el backlog recién aparece en /metrics tras el
    # primer intervalo, y un reinicio mostraría cero trabajo pendiente mientras tanto. Si la DB
    # no está lista todavía, el loop lo reintenta solo.
    try:
        await business_metrics.refresh()
    except Exception as exc:  # noqa: BLE001
        log.warning("business_metrics_initial_refresh_failed", error=str(exc))
    await business_metrics.start()

    state.update(business_metrics=business_metrics)
    log.info("metrics_service_started", interval=settings.business_metrics_interval)
    yield
    await business_metrics.stop()
    await dispose_db()


app = FastAPI(title="TeleFlow metrics-service", version="1.0.0", lifespan=lifespan)
setup_observability(app, "metrics-service", ready_check=db_ping)
