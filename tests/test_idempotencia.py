"""Idempotencia de `/execute`: reintentar no crea un segundo expediente.

Un cliente que reintenta por timeout —el reintento más común y más razonable— disparaba el
proceso dos veces. En orquestación de negocio eso no es performance: son dos expedientes, dos
notificaciones al ciudadano y dos llamadas a la integración, y no se deshace.

Se prueba `trigger()` con una sesión falsa: lo que importa acá es la **decisión** (crear,
devolver la existente o rechazar), no el SQL. Que el `UNIQUE` exista y corte de verdad se
prueba contra Postgres en `tests/e2e/test_idempotencia_e2e.py`.
"""
import uuid
from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError

from teleflow.common.models import ProcessInstance
from teleflow.executor_service.engine import ExecutionEngine
from teleflow.executor_service.entities import DomainError


class _SesionFalsa:
    """Sesión mínima: guarda lo agregado y responde el `scalar` con lo que se le diga."""

    def __init__(self, existente: ProcessInstance | None = None,
                 choca_al_insertar: bool = False):
        self.existente = existente
        self.choca_al_insertar = choca_al_insertar
        self.agregados: list[Any] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, *args, **kwargs):
        return self.existente

    def add(self, obj):
        self.agregados.append(obj)

    async def flush(self):
        if self.choca_al_insertar:
            # Después del choque, el ganador ya está: la relectura lo encuentra.
            self.choca_al_insertar = False
            self.existente = _instancia(clave="k", flow="alta_socio")
            raise IntegrityError("INSERT", {}, Exception("uq_idempotency_key"))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def _instancia(clave: str, flow: str = "alta_socio",
               payload: dict[str, Any] | None = None) -> ProcessInstance:
    fila = ProcessInstance(
        flow_name=flow, flow_version="1.0.0", status="IN_PROGRESS",
        trigger_payload=payload if payload is not None else {"ci": "1.234.567-8"},
        context={}, idempotency_key=clave,
    )
    fila.id = uuid.uuid4()
    return fila


class _DominioVacio:
    """Ningún flow registrado: `trigger` sin clave termina en 404, su camino de siempre."""

    async def find_process(self, flow_name: str):
        return None


def _engine(sesion: _SesionFalsa) -> ExecutionEngine:
    """Engine con lo mínimo: `trigger` con clave repetida no llega a tocar nada más."""
    motor = ExecutionEngine.__new__(ExecutionEngine)
    motor._sessionmaker = cast(Any, lambda: sesion)
    motor._domain = cast(Any, _DominioVacio())
    return motor


PEDIDO = {"ci": "1.234.567-8"}


# ------------------------------------------------- el caso que importa

async def test_reintentar_con_la_misma_clave_no_crea_otra_instancia():
    ya_existe = _instancia(clave="k-1")
    sesion = _SesionFalsa(existente=ya_existe)

    salida = await _engine(sesion).trigger(
        "alta_socio", "latest", PEDIDO, idempotency_key="k-1")

    assert salida["instance_id"] == str(ya_existe.id)
    assert salida["idempotent_replay"] is True
    assert sesion.agregados == [], "no tendría que haber creado nada"


async def test_sin_clave_el_comportamiento_no_cambia():
    """La protección es opcional: sin clave, cada llamada dispara. No se rompe a nadie."""
    sesion = _SesionFalsa(existente=_instancia(clave="k-1"))

    with pytest.raises(DomainError) as exc:
        # Sin clave ni siquiera consulta: sigue de largo y falla al resolver el process,
        # que es el camino de siempre.
        await _engine(sesion).trigger("no_existe", "latest", PEDIDO)

    assert exc.value.status_code == 404


# ------------------------------------------------- la misma clave, otro pedido

async def test_la_misma_clave_con_otro_payload_es_409():
    """Devolver la instancia vieja sería lo amable y es lo peor: el cliente pidió A, recibe
    el resultado de B, y cree que A se disparó."""
    sesion = _SesionFalsa(existente=_instancia(clave="k-1", payload={"ci": "otro"}))

    with pytest.raises(DomainError) as exc:
        await _engine(sesion).trigger(
            "alta_socio", "latest", PEDIDO, idempotency_key="k-1")

    assert exc.value.status_code == 409
    assert "ya se usó para otro pedido" in str(exc.value)


async def test_la_misma_clave_con_otro_flow_es_409():
    sesion = _SesionFalsa(existente=_instancia(clave="k-1", flow="baja_socio"))

    with pytest.raises(DomainError) as exc:
        await _engine(sesion).trigger(
            "alta_socio", "latest", PEDIDO, idempotency_key="k-1")

    assert exc.value.status_code == 409


# ------------------------------------------------- la carrera

async def test_dos_disparos_simultaneos_devuelven_la_misma_instancia():
    """Los dos pasan el chequeo previo; el UNIQUE corta al segundo. Ese segundo tiene que
    recibir la instancia del que ganó, no un 500 ni una instancia nueva."""
    sesion = _SesionFalsa(existente=None, choca_al_insertar=True)
    motor = _engine(sesion)
    # Sustituir un método en la instancia: mypy lo marca, y acá es a propósito.
    setattr(motor, "_resolve_process", _resolver_ok)

    salida = await motor.trigger("alta_socio", "latest", PEDIDO, idempotency_key="k")

    assert salida["idempotent_replay"] is True
    assert sesion.commits == 0, "no puede haber commiteado una instancia duplicada"


async def _resolver_ok(flow_name: str, version: str):
    from teleflow.dsl.ast_nodes import ProcessDef

    return ProcessDef(name="alta_socio"), "alta_socio", "1.0.0"
