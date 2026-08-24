"""Métricas de negocio: estado actual del trabajo en curso.

Las métricas que ya existían (`teleflow_instances_total`, `teleflow_steps_total`) son
**counters de eventos**: responden "cuántas instancias terminaron" pero no "cuánto trabajo
hay ahora". El backlog de human_tasks que promete la doc de arquitectura es justamente lo
segundo, así que se publica como **gauge** desde un scanner periódico que agrega
`process_instances` — los datos ya están en la tabla, no hace falta schema nuevo.

Se miden solo los estados **vivos**: los terminales (COMPLETED / FAILED / COMPENSATED) ya
los cuenta `teleflow_instances_total` en el momento en que ocurren, y agregarlos acá
significaría escanear toda la historia de la tabla cada ciclo para reconstruir un número que
solo crece.

**Este colector tiene que correr en un solo proceso.** El gauge lleva el valor absoluto y el
dashboard suma entre pods, así que N procesos publicando lo mismo hacen leer N× todo número de
negocio. Por eso vive en `metrics_service`, que se despliega con **una sola réplica**, y no en el
executor, que corre con tres. La garantía es topológica y a propósito: se intentó coordinar por
advisory lock y no alcanzó (el detalle está en `metrics_service/main.py`).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger
from teleflow.common.models import ProcessInstance

log = get_logger(component="business-metrics")

# Estados en los que la instancia todavía representa trabajo pendiente.
ACTIVE_STATUSES = ("TRIGGERED", "IN_PROGRESS", "RETRYING", "WAITING_SIGNAL")

# Estado en el que la instancia duerme esperando la señal de un human_task (engine.py).
WAITING_SIGNAL = "WAITING_SIGNAL"

# Estados en los que la instancia **compite por un worker** del executor. Es
# `ACTIVE_STATUSES` menos `WAITING_SIGNAL`, y la diferencia no es cosmética: una instancia
# dormida en durable sleep no ocupa nada —`_run` hace `return` y suelta semáforo y lease— así
# que sumarla al trabajo pendiente hace leer como saturación lo que es un humano que todavía no
# contestó. Medido: con 220 instancias en WAITING_SIGNAL, el executor estaba ocioso.
WORKER_STATUSES = tuple(s for s in ACTIVE_STATUSES if s != WAITING_SIGNAL)


INSTANCES_CURRENT = Gauge(
    "teleflow_instances_current",
    "Instancias de proceso vivas ahora, por estado",
    ["flow_name", "status"],
)
# Trabajo que compite por un worker, en un solo número y sin labels: es la señal de capacidad
# del executor, y existe aparte de `teleflow_instances_current` por dos motivos medidos.
#
# (a) **Excluye WAITING_SIGNAL.** Sumar durable sleep haría escalar por humanos que no
#     contestan, y las réplicas nuevas no podrían hacer nada al respecto.
# (b) **No tiene labels.** Un autoscaler necesita un escalar; obligarlo a sumar series por
#     `flow_name` deja la decisión de capacidad escrita en la query de quien configure el
#     adapter, donde nadie la revisa y donde ya vimos que se cuela WAITING_SIGNAL.
#
# Lo que este número NO dice, y por eso el HPA del chart viene apagado: que sumar réplicas lo
# baje. El reparto de trabajo va por el balanceo HTTP del Service —la réplica que recibe el
# `POST /execute` es la que ejecuta la instancia— así que un pod nuevo atiende disparos nuevos
# pero no drena la cola que ya está encolada en otro.
EXECUTOR_BACKLOG = Gauge(
    "teleflow_executor_backlog",
    "Instancias que compiten por un worker del executor (excluye durable sleep)",
)
HUMAN_TASK_BACKLOG = Gauge(
    "teleflow_human_task_backlog",
    "Instancias esperando la señal de un human_task, por step",
    ["flow_name", "step_name"],
)
HUMAN_TASK_OLDEST_SECONDS = Gauge(
    "teleflow_human_task_oldest_seconds",
    "Antigüedad de la instancia más vieja esperando en un human_task, por step",
    ["flow_name", "step_name"],
)

# Frescura. Los tres gauges de arriba **conservan su último valor** si el refresh falla: el
# `except` del loop loguea y sigue, a propósito (un fallo de métricas no debe bajar el
# servicio). La consecuencia es que un backlog congelado en 10 se ve idéntico a un backlog
# estable de 10 — sin hueco en el dashboard que delate nada, y con `up == 1`, así que ninguna
# alerta sobre la salud del pod lo detecta.
#
# Estos dos existen para que ese estado sea **observable desde afuera**: no arreglan el fallo,
# lo hacen decible. El timestamp arranca en 0 a propósito — un servicio que nunca logró un
# refresh (DB caída al arrancar, o el colector que nadie arrancó) da una antigüedad enorme
# desde el primer scrape, que es exactamente lo que hay que reportar.
LAST_SUCCESS_TIMESTAMP = Gauge(
    "teleflow_business_metrics_last_success_timestamp_seconds",
    "Unix timestamp del último refresh exitoso de los gauges de negocio (0 = ninguno todavía)",
)
REFRESH_FAILURES = Counter(
    "teleflow_business_metrics_refresh_failures_total",
    "Refrescos de los gauges de negocio que terminaron en error",
)


@dataclass(frozen=True)
class InstanceGroup:
    """Una fila del agregado: instancias vivas de un flow en un estado (y step) dado."""

    flow_name: str
    status: str
    current_step: str | None
    count: int
    oldest_updated_at: datetime | None


def _seconds_since(moment: datetime | None, now: datetime) -> float:
    if moment is None:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (now - moment).total_seconds())


class BusinessMetricsCollector:
    """Refresca los gauges de negocio cada `business_metrics_interval` segundos.

    Sigue el patrón de `RuleEngine._timer_loop`: una task async arrancada desde el lifespan
    del servicio.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings):
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        # Labels publicados en el ciclo anterior. Un gauge conserva el último valor de cada
        # combinación de labels, así que un step que se vacía se quedaría marcando backlog
        # fantasma para siempre. Se los baja a 0 explícitamente en vez de borrarlos: borrar
        # la serie deja un hueco en el dashboard, que no es lo mismo que "no hay backlog".
        self._instance_labels: set[tuple[str, str]] = set()
        self._human_task_labels: set[tuple[str, str]] = set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        interval = max(5, self._settings.business_metrics_interval)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.refresh()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 — un fallo de métricas no baja el executor
                log.error("business_metrics_error", error=str(exc))

    async def refresh(self) -> None:
        # El contador se incrementa acá y no en el `except` del loop porque hay **dos**
        # llamadores: el loop y el refresh inicial del lifespan. Contar en un solo lado dejaba
        # el fallo de arranque —el más probable, porque la DB puede no estar lista— sin registrar.
        try:
            async with self._sessionmaker() as session:
                groups = await self._collect(session)
            now = datetime.now(timezone.utc)
            self.publish(groups, now)
            # Última línea del camino feliz: el timestamp solo avanza si los tres gauges de
            # arriba quedaron efectivamente actualizados.
            LAST_SUCCESS_TIMESTAMP.set(now.timestamp())
        except Exception:
            REFRESH_FAILURES.inc()
            raise

    async def _collect(self, session: AsyncSession) -> list[InstanceGroup]:
        """Un solo GROUP BY sobre el working set (los estados vivos usan el índice de status)."""
        query = (
            select(
                ProcessInstance.flow_name,
                ProcessInstance.status,
                ProcessInstance.current_step,
                func.count().label("total"),
                func.min(ProcessInstance.updated_at).label("oldest"),
            )
            .where(ProcessInstance.status.in_(ACTIVE_STATUSES))
            .group_by(
                ProcessInstance.flow_name,
                ProcessInstance.status,
                ProcessInstance.current_step,
            )
        )
        rows = (await session.execute(query)).all()
        return [
            InstanceGroup(
                flow_name=row.flow_name,
                status=row.status,
                current_step=row.current_step,
                count=row.total,
                oldest_updated_at=row.oldest,
            )
            for row in rows
        ]

    def publish(self, groups: list[InstanceGroup], now: datetime) -> None:
        """Vuelca el agregado a los gauges. Puro respecto de la DB: recibe las filas ya leídas."""
        por_estado: dict[tuple[str, str], int] = {}
        backlog: dict[tuple[str, str], int] = {}
        mas_viejo: dict[tuple[str, str], datetime] = {}

        for group in groups:
            estado_key = (group.flow_name, group.status)
            por_estado[estado_key] = por_estado.get(estado_key, 0) + group.count
            if group.status != WAITING_SIGNAL:
                continue
            # Una instancia en WAITING_SIGNAL siempre tiene current_step (engine.py lo
            # persiste al dormirse), pero la columna es nullable: no inventamos un nombre.
            step_key = (group.flow_name, group.current_step or "desconocido")
            backlog[step_key] = backlog.get(step_key, 0) + group.count
            if group.oldest_updated_at is not None:
                previo = mas_viejo.get(step_key)
                if previo is None or group.oldest_updated_at < previo:
                    mas_viejo[step_key] = group.oldest_updated_at

        # Se calcula sumando el mismo agregado, no con una query aparte: dos consultas podrían
        # leer momentos distintos y dejar el backlog contradiciendo a `instances_current`.
        EXECUTOR_BACKLOG.set(
            sum(total for (_, estado), total in por_estado.items()
                if estado in WORKER_STATUSES)
        )

        for labels in self._instance_labels - set(por_estado):
            INSTANCES_CURRENT.labels(*labels).set(0)
        for labels, total in por_estado.items():
            INSTANCES_CURRENT.labels(*labels).set(total)

        for labels in self._human_task_labels - set(backlog):
            HUMAN_TASK_BACKLOG.labels(*labels).set(0)
            HUMAN_TASK_OLDEST_SECONDS.labels(*labels).set(0)
        for labels, total in backlog.items():
            HUMAN_TASK_BACKLOG.labels(*labels).set(total)
            HUMAN_TASK_OLDEST_SECONDS.labels(*labels).set(
                _seconds_since(mas_viejo.get(labels), now)
            )

        self._instance_labels |= set(por_estado)
        self._human_task_labels |= set(backlog)
