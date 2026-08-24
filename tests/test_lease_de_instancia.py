"""Propiedad de una instancia en vuelo: solo el dueño la ejecuta.

Contexto del bug que esto arregla: `_recover()` corría en **cada** réplica del executor y
recuperaba **todas** las instancias en vuelo, sin que nadie reclamara nada. Medido en un cluster
de 3 réplicas: el mismo step ejecutado 3 veces (63 requests donde iban 21) y tres transiciones
`IN_PROGRESS → FAILED` del mismo expediente. La condición de disparo era cada deploy.

**Por qué el escenario de estos tests es secuencial, y esto costó aprenderlo.** El intento
anterior de arreglar un problema multi-réplica (los gauges de negocio) se verificó con un test
que **forzaba** el solapamiento temporal de dos ciclos, y por eso pasaba mientras el bug seguía
vivo: en producción los ciclos nunca se solapaban. Acá el escenario real es **arranques
desfasados** —los pods no arrancan al mismo instante—, así que las réplicas reclaman **una
después de la otra**. Es la forma en que el bug ocurría, y con el bug original las tres ganaban.

**Qué prueban y qué no.** Corren sobre SQLite en memoria: alcanza porque lo que se verifica es
la lógica del `WHERE` y la decisión por **rowcount**, que es idéntica, y porque los reclamos son
secuencialmente deliberados. Lo que SQLite **no** prueba es el comportamiento real con varias
réplicas contra Postgres; eso se verifica en el cluster con el mismo experimento que encontró el
bug (instancia en vuelo + `rollout restart` con 3 réplicas), y está anotado en el ADR.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from teleflow.common.config import Settings
from teleflow.common.models import Base, InstanceTransition, ProcessInstance
from teleflow.executor_service.engine import ExecutionEngine


@pytest.fixture
async def sessionmaker_mem():
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with motor.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


def _replica(sessionmaker, nombre: str, lease_seconds: int = 60) -> ExecutionEngine:
    """Un engine que se hace pasar por una réplica con identidad propia."""
    motor = ExecutionEngine(
        sessionmaker, None, None, None,  # type: ignore[arg-type]
        Settings(instance_lease_seconds=lease_seconds),
    )
    motor._identidad = nombre
    return motor


@pytest.fixture
async def en_vuelo(sessionmaker_mem):
    """Una instancia IN_PROGRESS sin dueño: lo que deja un proceso que murió."""
    iid = uuid.uuid4()
    async with sessionmaker_mem() as session:
        session.add(ProcessInstance(
            id=iid, flow_name="test_lease", flow_version="1.0.0",
            status="IN_PROGRESS", trigger_payload={}, context={},
        ))
        await session.commit()
    return iid


async def test_una_sola_replica_se_queda_con_la_instancia(sessionmaker_mem, en_vuelo):
    """El caso reproducido en el cluster: tres réplicas arrancando y recuperando lo mismo."""
    a = _replica(sessionmaker_mem, "pod-a")
    b = _replica(sessionmaker_mem, "pod-b")
    c = _replica(sessionmaker_mem, "pod-c")

    ganadores = [
        nombre for nombre, motor in (("a", a), ("b", b), ("c", c))
        if await motor._tomar_lease(en_vuelo)
    ]

    assert ganadores == ["a"], f"esperaba un solo dueño, ganaron: {ganadores}"


async def test_el_dueno_puede_reclamar_de_nuevo_lo_suyo(sessionmaker_mem, en_vuelo):
    """Reentrar sobre la propia instancia no es un conflicto: renueva y sigue."""
    a = _replica(sessionmaker_mem, "pod-a")

    assert await a._tomar_lease(en_vuelo)
    assert await a._tomar_lease(en_vuelo)


async def test_mientras_el_lease_esta_vigente_nadie_mas_la_toma(sessionmaker_mem, en_vuelo):
    a = _replica(sessionmaker_mem, "pod-a", lease_seconds=300)
    b = _replica(sessionmaker_mem, "pod-b", lease_seconds=300)

    assert await a._tomar_lease(en_vuelo)
    assert not await b._tomar_lease(en_vuelo)


async def test_cuando_el_lease_vence_otra_replica_la_toma(sessionmaker_mem, en_vuelo):
    """La razón de ser del vencimiento, y la mitad que un test apurado se saltea.

    Sin esto el arreglo sería un candado: un pod que muere dejaría su expediente trabado para
    siempre, y `_recover()` —que existe justamente para retomar trabajo huérfano— no serviría
    de nada.
    """
    muerta = _replica(sessionmaker_mem, "pod-que-muere", lease_seconds=0)
    viva = _replica(sessionmaker_mem, "pod-vivo")

    assert await muerta._tomar_lease(en_vuelo)   # lease que vence al instante
    assert await viva._tomar_lease(en_vuelo), (
        "con el lease vencido, otra réplica tiene que poder tomarla"
    )


async def test_el_que_perdio_la_instancia_se_entera_al_renovar(sessionmaker_mem, en_vuelo):
    """Una réplica que tardó tanto que perdió el lease no debe seguir trabajando a ciegas."""
    lenta = _replica(sessionmaker_mem, "pod-lento", lease_seconds=0)
    otra = _replica(sessionmaker_mem, "pod-otro", lease_seconds=300)

    await lenta._tomar_lease(en_vuelo)
    await otra._tomar_lease(en_vuelo)

    assert not await lenta._renovar_lease(en_vuelo), (
        "renovar tiene que fallar cuando la instancia ya es de otro"
    )


async def test_soltar_el_lease_la_deja_disponible(sessionmaker_mem, en_vuelo):
    a = _replica(sessionmaker_mem, "pod-a", lease_seconds=300)
    b = _replica(sessionmaker_mem, "pod-b", lease_seconds=300)

    await a._tomar_lease(en_vuelo)
    await a._soltar_lease(en_vuelo)

    assert await b._tomar_lease(en_vuelo)
    async with sessionmaker_mem() as session:
        fila = await session.get(ProcessInstance, en_vuelo)
        assert fila is not None and fila.driven_by == "pod-b"


async def test_recover_no_toma_lo_que_tiene_dueno_vivo(sessionmaker_mem, en_vuelo):
    """`_recover()` pasó de "recupero todo lo en vuelo" a "tomo lo huérfano".

    Se ejecuta el `_recover` real y se afirma que **no** lanzó ningún drive: si lo hiciera,
    volvería el bug. El drive se intercepta para no necesitar dominio ni broker.
    """
    dueno = _replica(sessionmaker_mem, "pod-dueno", lease_seconds=300)
    await dueno._tomar_lease(en_vuelo)

    recuperador = _replica(sessionmaker_mem, "pod-recuperador")
    conducidas: list[uuid.UUID] = []

    async def _drive_falso(instance_id):
        conducidas.append(instance_id)

    recuperador._drive = _drive_falso  # type: ignore[method-assign]
    await recuperador._recover()
    # `_recover` lanza los drives con `_spawn`, que crea tasks. Sin cederle el control al loop
    # la lista queda vacía SIEMPRE y este test pasaría por el motivo equivocado.
    await asyncio.sleep(0)

    assert en_vuelo not in conducidas, (
        "recuperó una instancia que otra réplica está ejecutando ahora mismo"
    )


async def test_recover_si_toma_lo_huerfano(sessionmaker_mem, en_vuelo):
    """La contracara: sin esto, el arreglo rompería la recuperación tras una caída."""
    recuperador = _replica(sessionmaker_mem, "pod-recuperador")
    conducidas: list[uuid.UUID] = []

    async def _drive_falso(instance_id):
        conducidas.append(instance_id)

    recuperador._drive = _drive_falso  # type: ignore[method-assign]
    await recuperador._recover()
    await asyncio.sleep(0)

    assert en_vuelo in conducidas, "una instancia sin dueño tiene que recuperarse"


async def test_una_transicion_desde_un_estado_que_ya_cambio_se_descarta(
    sessionmaker_mem, en_vuelo
):
    """La segunda red: `_set_status` guardado.

    Es lo que evita que dos procesos escriban la misma transición, que es cómo
    `instance_transitions` terminó con tres `IN_PROGRESS → FAILED` del mismo expediente.
    """
    motor = _replica(sessionmaker_mem, "pod-a")

    assert await motor._set_status(en_vuelo, "IN_PROGRESS", "COMPLETED")
    # El segundo cree que sigue en IN_PROGRESS, pero ya no: no tiene nada que registrar.
    assert not await motor._set_status(en_vuelo, "IN_PROGRESS", "FAILED")

    async with sessionmaker_mem() as session:
        fila = await session.get(ProcessInstance, en_vuelo)
        assert fila is not None and fila.status == "COMPLETED"
        transiciones = (await session.execute(
            select(InstanceTransition).where(InstanceTransition.instance_id == en_vuelo)
        )).scalars().all()
        assert len(transiciones) == 1, (
            f"la transición descartada no debe dejar rastro; hay {len(transiciones)}"
        )


async def test_una_instancia_ya_terminal_no_vuelve_a_fallar(sessionmaker_mem, en_vuelo):
    """`_mark_failed` es el método que escribió las tres transiciones a FAILED."""
    motor = _replica(sessionmaker_mem, "pod-a")

    await motor._mark_failed(en_vuelo, "paso_x", "primer fallo")
    await motor._mark_failed(en_vuelo, "paso_x", "el segundo llega tarde")

    async with sessionmaker_mem() as session:
        transiciones = (await session.execute(
            select(InstanceTransition).where(
                InstanceTransition.instance_id == en_vuelo,
                InstanceTransition.to_status == "FAILED",
            )
        )).scalars().all()

    assert len(transiciones) == 1, (
        f"un expediente no falla dos veces; hay {len(transiciones)} transiciones a FAILED"
    )
