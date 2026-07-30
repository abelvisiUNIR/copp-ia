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

**Con varias réplicas del executor, solo una publica por ciclo.** El gauge lleva el valor
absoluto y el dashboard suma entre pods, así que N réplicas publicando lo mismo hacían leer N×
todo número de negocio. El turno se sortea con un advisory lock de Postgres, y las réplicas que
no lo obtienen **bajan sus gauges a 0** en vez de dejar de refrescar — un gauge conserva su
último valor, así que quedarse quieto mantendría el `sum` inflado con un dato viejo que parece
actual. Ver el ADR de la wiki "quién publica los gauges de negocio cuando el executor tiene
varias réplicas".
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from prometheus_client import Gauge
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger
from teleflow.common.models import ProcessInstance

log = get_logger(component="business-metrics")

# Estados en los que la instancia todavía representa trabajo pendiente.
ACTIVE_STATUSES = ("TRIGGERED", "IN_PROGRESS", "RETRYING", "WAITING_SIGNAL")

# Estado en el que la instancia duerme esperando la señal de un human_task (engine.py).
WAITING_SIGNAL = "WAITING_SIGNAL"

# Clave del advisory lock que decide qué réplica publica el ciclo. Es un número fijo y arbitrario;
# lo único que importa es que no lo use otra cosa contra la misma base. Los advisory locks viven
# en un espacio global del cluster de Postgres, no por tabla, así que conviene dejarlo acá
# nombrado y no repetirlo suelto.
LOCK_METRICAS_NEGOCIO = 8474137001

INSTANCES_CURRENT = Gauge(
    "teleflow_instances_current",
    "Instancias de proceso vivas ahora, por estado",
    ["flow_name", "status"],
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
        """Publica el ciclo si le toca el turno; si no, apaga sus propios gauges.

        El lock y la query van en la **misma** sesión a propósito: un advisory lock de Postgres
        es de la sesión que lo tomó, así que pedirlo en una conexión y consultar en otra no
        garantizaría nada.
        """
        async with self._sessionmaker() as session:
            if not await self._tomar_turno(session):
                self.apagar()
                return
            try:
                groups = await self._collect(session)
            finally:
                await self._soltar_turno(session)
        self.publish(groups, datetime.now(timezone.utc))

    async def _tomar_turno(self, session: AsyncSession) -> bool:
        """`True` si esta réplica es la que publica este ciclo.

        `pg_try_advisory_lock` no espera: la réplica que no lo consigue sigue de largo y vuelve a
        intentar el ciclo que viene. No hay líder permanente, así que tampoco hay que detectar
        caídas: si la que tenía el turno murió, otra lo toma en el próximo intervalo.
        """
        tomado = await session.scalar(
            text("SELECT pg_try_advisory_lock(:clave)"), {"clave": LOCK_METRICAS_NEGOCIO}
        )
        return bool(tomado)

    async def _soltar_turno(self, session: AsyncSession) -> None:
        await session.execute(
            text("SELECT pg_advisory_unlock(:clave)"), {"clave": LOCK_METRICAS_NEGOCIO}
        )

    def apagar(self) -> None:
        """Baja a 0 todo lo que esta réplica haya publicado alguna vez.

        Se llama cuando el turno le tocó a otra. No alcanza con no refrescar: el gauge conserva
        el último valor de cada combinación de labels, así que esta réplica seguiría exportando
        el número del ciclo anterior y el `sum(...)` del dashboard seguiría inflado — con el
        agravante de que un dato viejo se lee como actual.

        Los labels se **recuerdan**, no se olvidan: si esta réplica vuelve a ganar el turno,
        tiene que poder bajar a 0 los que dejen de aparecer.
        """
        for labels in self._instance_labels:
            INSTANCES_CURRENT.labels(*labels).set(0)
        for labels in self._human_task_labels:
            HUMAN_TASK_BACKLOG.labels(*labels).set(0)
            HUMAN_TASK_OLDEST_SECONDS.labels(*labels).set(0)

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
