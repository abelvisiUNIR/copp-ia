"""Gauges de negocio: qué backlog reportan y qué pasa cuando el backlog se vacía.

Sin DB: `publish()` recibe el agregado ya leído, así que el reparto a gauges se prueba
directo. La query contra Postgres se cubre en el e2e (`tests/e2e/test_business_metrics_e2e.py`).
"""
from datetime import datetime, timedelta, timezone

import pytest

from teleflow.common.config import Settings
from teleflow.executor_service.business_metrics import (
    HUMAN_TASK_BACKLOG,
    HUMAN_TASK_OLDEST_SECONDS,
    INSTANCES_CURRENT,
    BusinessMetricsCollector,
    InstanceGroup,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def collector() -> BusinessMetricsCollector:
    INSTANCES_CURRENT.clear()
    HUMAN_TASK_BACKLOG.clear()
    HUMAN_TASK_OLDEST_SECONDS.clear()
    return BusinessMetricsCollector(None, Settings())  # type: ignore[arg-type]


def backlog(flow: str, step: str) -> float:
    return float(HUMAN_TASK_BACKLOG.labels(flow, step)._value.get())


def esperando_hace(flow: str, step: str) -> float:
    return float(HUMAN_TASK_OLDEST_SECONDS.labels(flow, step)._value.get())


def vivas(flow: str, status: str) -> float:
    return float(INSTANCES_CURRENT.labels(flow, status)._value.get())


def waiting(step: str, count: int, minutos: int = 0) -> InstanceGroup:
    return InstanceGroup(
        flow_name="venta", status="WAITING_SIGNAL", current_step=step, count=count,
        oldest_updated_at=NOW - timedelta(minutes=minutos),
    )


def test_el_backlog_se_reporta_por_step_no_agregado(collector):
    """Un backlog total no dice a quién reclamarle: el label es el step que espera."""
    collector.publish([waiting("aprobacion", 3), waiting("instalacion", 1)], NOW)

    assert backlog("venta", "aprobacion") == 3
    assert backlog("venta", "instalacion") == 1


def test_la_antiguedad_es_la_del_mas_viejo_del_step(collector):
    """El insumo de SLA es el peor caso, no el promedio."""
    collector.publish([waiting("aprobacion", 5, minutos=90)], NOW)

    assert esperando_hace("venta", "aprobacion") == 90 * 60


def test_un_step_que_se_vacia_baja_a_cero_y_no_queda_pegado(collector):
    """Un gauge conserva el último valor: sin esto el dashboard mostraría backlog fantasma."""
    collector.publish([waiting("aprobacion", 4, minutos=30)], NOW)

    collector.publish([waiting("instalacion", 1)], NOW)

    assert backlog("venta", "aprobacion") == 0
    assert esperando_hace("venta", "aprobacion") == 0
    assert backlog("venta", "instalacion") == 1


def test_instancias_vivas_por_estado_suman_los_steps_del_estado(collector):
    """`teleflow_instances_current` es por estado: el step es detalle del backlog."""
    collector.publish(
        [waiting("aprobacion", 2), waiting("instalacion", 3),
         InstanceGroup("venta", "IN_PROGRESS", "alta_ott", 4, NOW)],
        NOW,
    )

    assert vivas("venta", "WAITING_SIGNAL") == 5
    assert vivas("venta", "IN_PROGRESS") == 4


def test_un_estado_que_se_vacia_tambien_baja_a_cero(collector):
    collector.publish([InstanceGroup("venta", "RETRYING", None, 2, NOW)], NOW)

    collector.publish([], NOW)

    assert vivas("venta", "RETRYING") == 0


def test_current_step_nulo_no_inventa_nombre_de_step(collector):
    """La columna es nullable: preferimos un label explícito antes que atribuirlo mal."""
    collector.publish([
        InstanceGroup("venta", "WAITING_SIGNAL", None, 1, NOW)], NOW)

    assert backlog("venta", "desconocido") == 1


def test_una_instancia_recien_dormida_reporta_espera_no_negativa(collector):
    """Si el reloj de la DB va adelantado, la espera es 0 — nunca un negativo."""
    futuro = InstanceGroup(
        "venta", "WAITING_SIGNAL", "aprobacion", 1, NOW + timedelta(seconds=5))

    collector.publish([futuro], NOW)

    assert esperando_hace("venta", "aprobacion") == 0


# --- Turno de publicación con varias réplicas ------------------------------------------
#
# El gauge lleva el valor absoluto y el dashboard suma entre pods, así que N réplicas
# publicando lo mismo hacen leer N× el negocio. Solo una publica por ciclo; las demás
# tienen que bajar sus gauges a 0, no simplemente dejar de refrescar.


class _SesionFalsa:
    """Sesión mínima que finge el resultado de `pg_try_advisory_lock`."""

    def __init__(self, gana_el_turno: bool):
        self.gana_el_turno = gana_el_turno
        self.solto = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def scalar(self, _stmt, _params=None):
        return self.gana_el_turno

    async def execute(self, _stmt, _params=None):
        self.solto = True
        return None


class _ColectorConTurno(BusinessMetricsCollector):
    """Colector con la query real reemplazada: acá se prueba el reparto, no el SQL."""

    def __init__(self, gana_el_turno: bool, groups):
        self.sesion = _SesionFalsa(gana_el_turno)
        super().__init__(lambda: self.sesion, Settings())  # type: ignore[arg-type]
        self._groups = groups

    async def _collect(self, _session):
        return self._groups


@pytest.mark.asyncio
async def test_la_replica_con_el_turno_publica_el_agregado(collector):
    replica = _ColectorConTurno(True, [waiting("aprobacion", 4)])

    await replica.refresh()

    assert backlog("venta", "aprobacion") == 4
    assert replica.sesion.solto, "el lock tiene que soltarse en el mismo ciclo"


@pytest.mark.asyncio
async def test_la_replica_sin_turno_no_publica_nada(collector):
    replica = _ColectorConTurno(False, [waiting("aprobacion", 4)])

    await replica.refresh()

    assert backlog("venta", "aprobacion") == 0


@pytest.mark.asyncio
async def test_la_replica_que_pierde_el_turno_baja_lo_que_habia_publicado(collector):
    """El caso que hacía leer 3× el negocio.

    Sin `apagar()`, la réplica que deja de ganar el turno **conserva** su último valor: el
    gauge no se vacía solo. El `sum(...)` del dashboard seguiría contando ese número viejo,
    que además se lee como si fuera actual.
    """
    replica = _ColectorConTurno(True, [waiting("aprobacion", 4)])
    await replica.refresh()
    assert backlog("venta", "aprobacion") == 4

    replica.sesion.gana_el_turno = False
    await replica.refresh()

    assert backlog("venta", "aprobacion") == 0
    assert esperando_hace("venta", "aprobacion") == 0


@pytest.mark.asyncio
async def test_recuperar_el_turno_vuelve_a_publicar(collector):
    """Apagar no puede ser definitivo: los labels se recuerdan, no se olvidan."""
    replica = _ColectorConTurno(True, [waiting("aprobacion", 4)])
    await replica.refresh()
    replica.sesion.gana_el_turno = False
    await replica.refresh()

    replica.sesion.gana_el_turno = True
    await replica.refresh()

    assert backlog("venta", "aprobacion") == 4
