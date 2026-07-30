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


# --- Un solo publicador -----------------------------------------------------------------
#
# El gauge lleva el valor absoluto y el dashboard suma entre pods, así que dos procesos
# publicando hacen leer el doble. La garantía es que el colector viva en un componente de
# una sola réplica (`metrics_service`), no en el executor que corre con tres.
#
# El intento anterior fue sortear un turno por ciclo con un advisory lock de Postgres, y no
# funcionó: un lock que se toma y se suelta dentro del ciclo solo excluye a réplicas cuyos
# ciclos se solapan, y con un ciclo de milisegundos cada 30 s no se solapan nunca. El test
# que lo cubría forzaba el solapamiento, así que verificaba un escenario inexistente.
# Este test es el que habría fallado: refresca dos veces SIN solapamiento.


def test_el_colector_no_coordina_nada_por_su_cuenta():
    """Contrato explícito: la exclusión es del despliegue, no del colector.

    Si alguien le agrega coordinación interna (un lock, un líder) este test lo va a hacer
    notar, y quien lo haga tiene que leer por qué se saco: dos ciclos que no se solapan no se
    excluyen entre sí, aunque el lock esté bien puesto.
    """
    assert not hasattr(BusinessMetricsCollector, "_tomar_turno")
    assert not hasattr(BusinessMetricsCollector, "apagar")


def test_dos_colectores_secuenciales_publican_los_dos(collector):
    """El caso que el test viejo no veía, y que documenta por qué hace falta 1 réplica.

    Dos colectores que refrescan uno después del otro —lo que pasa de verdad con réplicas
    cuyos ciclos están desfasados— publican los dos. En un solo proceso el gauge se sobrescribe
    y queda en 4; entre procesos distintos, cada uno expone 4 y Prometheus suma 8.

    O sea: no hay nada en el colector que impida el doble conteo. Por eso corre en un
    componente de una sola réplica.
    """
    a = BusinessMetricsCollector(None, Settings())  # type: ignore[arg-type]
    b = BusinessMetricsCollector(None, Settings())  # type: ignore[arg-type]

    a.publish([waiting("aprobacion", 4)], NOW)
    b.publish([waiting("aprobacion", 4)], NOW)

    assert backlog("venta", "aprobacion") == 4
    assert a._human_task_labels == b._human_task_labels == {("venta", "aprobacion")}
