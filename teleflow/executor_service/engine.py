"""Motor de ejecución: DAG async + durable sleep (ADR-002).

- Construye el DAG de stages con networkx y valida que sea acíclico
  (los saltos de stages decision pueden formar loops controlados: warning).
- Recorre los steps de forma async, persistiendo el cursor tras cada step.
- En un step human_task la instancia pasa a WAITING_SIGNAL: el contexto
  completo queda en Postgres y el worker se libera (sin polling).
- La señal llega por Redis pub/sub (latencia de ms) y es idempotente
  por signal_key único. Al reiniciar, el executor recupera instancias
  dormidas y en vuelo desde Postgres.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import networkx as nx
import redis.asyncio as aioredis
from prometheus_client import Counter
from sqlalchemy import CursorResult
from sqlalchemy import or_ as sa_or
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger
from teleflow.common.models import InstanceTransition, ProcessInstance, SignalRecord
from teleflow.common.retry import full_jitter_delay
from teleflow.dsl.ast_nodes import ProcessDef, Ref, StageDef, StepDef
from teleflow.dsl.evaluator import evaluate
from teleflow.executor_service import adapters
from teleflow.executor_service.domain import DomainLoader
from teleflow.executor_service.entities import DomainError, EntityService
from teleflow.executor_service.events import EventBus

log = get_logger(component="engine")

INSTANCES_TOTAL = Counter(
    "teleflow_instances_total", "Instancias por estado final", ["flow_name", "status"]
)
STEPS_TOTAL = Counter(
    "teleflow_steps_total", "Steps ejecutados", ["flow_name", "step_name", "result"]
)

SIGNAL_CHANNEL_PREFIX = "teleflow:signal:"


class StepFailed(Exception):
    def __init__(self, step_name: str, message: str):
        super().__init__(message)
        self.step_name = step_name


def ramas_por_decision(proc: ProcessDef) -> dict[str, set[str]]:
    """Para cada stage `decision`, los stages a los que puede saltar.

    Es la base de la regla que impide que **las ramas de una misma decisión se derramen una
    en otra**: un stage que no es decision cae en el de al lado, y las ramas están escritas
    una debajo de la otra, así que sin esto la rama buena corría y después seguía de largo
    hacia la mala. Ver el ADR de la caída secuencial.
    """
    return {
        s.name: {b.target.target for b in s.branches if b.target.target != "end"}
        for s in proc.stages if s.mode == "decision"
    }


def siguiente_stage(proc: ProcessDef, ramas: dict[str, set[str]],
                    actual: int, rama: str | None) -> int:
    """A qué stage se cae al terminar `actual`. Devolver `len(stages)` = el proceso termina.

    `rama` es la decisión de la que venimos, o None si llegamos por caída. La regla: **una
    rama no se derrama sobre otra rama de su misma decisión**. Las ramas se escriben una
    debajo de la otra y los stages que no son decision caen en el de al lado, así que sin esto
    elegir la rama buena la ejecutaba y después seguía de largo hacia la mala.

    Es acotada a propósito: solo corta el paso hacia una **hermana**. Un stage común sigue
    cayendo en el siguiente, que es lo que hace legible un proceso lineal, y una rama de varios
    stages sigue encadenada hasta toparse con su hermana.
    """
    siguiente = actual + 1
    if rama is not None and siguiente < len(proc.stages) \
            and proc.stages[siguiente].name in ramas.get(rama, set()):
        return len(proc.stages)
    return siguiente


def decision_de_cada_stage(proc: ProcessDef) -> dict[int, str]:
    """Para cada stage, de qué decisión es rama (directa o por caída desde una rama).

    Recorre hacia adelante desde cada destino: se entra a la rama y se sigue cayendo hasta
    toparse con otra rama de esa misma decisión —ahí termina— o con una decisión, que vuelve
    a elegir. Es la versión estática de lo que el intérprete resuelve con el cursor.
    """
    dueño: dict[int, str] = {}
    indice = {s.name: i for i, s in enumerate(proc.stages)}
    for decision, destinos in ramas_por_decision(proc).items():
        for destino in destinos:
            if destino not in indice:
                continue
            i = indice[destino]
            while i < len(proc.stages):
                dueño.setdefault(i, decision)
                if proc.stages[i].mode == "decision":
                    break
                if i + 1 < len(proc.stages) and proc.stages[i + 1].name in destinos:
                    break  # la rama termina antes de pisar a su hermana
                i += 1
    return dueño


def build_stage_dag(proc: ProcessDef) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    names = [s.name for s in proc.stages]
    graph.add_nodes_from(names)
    ramas = ramas_por_decision(proc)
    dueño = decision_de_cada_stage(proc)
    for i, stage in enumerate(proc.stages):
        if stage.mode == "decision":
            for branch in stage.branches:
                graph.add_edge(stage.name, branch.target.target)
        elif i + 1 < len(names):
            # La caída secuencial **no** cruza hacia otra rama de la misma decisión: ahí el
            # proceso termina. El grafo tiene que decir lo mismo que el intérprete, o la
            # detección de ciclos opina sobre un proceso que no existe.
            decision = dueño.get(i)
            if decision is not None and names[i + 1] in ramas.get(decision, set()):
                continue
            graph.add_edge(stage.name, names[i + 1])
    return graph


class ExecutionEngine:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession],
                 domain_loader: DomainLoader, event_bus: EventBus,
                 entity_service: EntityService, settings: Settings):
        self._sessionmaker = sessionmaker
        self._domain = domain_loader
        self._bus = event_bus
        self._entities = entity_service
        self._settings = settings
        self._redis: aioredis.Redis | None = None
        self._semaphore = asyncio.Semaphore(settings.worker_concurrency)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._listener_task: asyncio.Task[Any] | None = None
        self._stopping = False
        # Identidad de este proceso, para escribirla como dueño de las instancias que ejecuta.
        # Hostname + pid: en Kubernetes el hostname es el nombre del pod, así que un expediente
        # trabado dice quién lo tenía. No se valida contra ninguna tabla — el dueño vale por el
        # vencimiento del lease, no por existir.
        self._identidad = f"{socket.gethostname()}:{os.getpid()}"
        self._renovaciones: dict[uuid.UUID, asyncio.Task[Any]] = {}

    # ----------------------------------------------------------- lifecycle

    async def start(self) -> None:
        self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        self._listener_task = asyncio.create_task(self._signal_listener())
        await self._recover()

    async def stop(self) -> None:
        self._stopping = True
        if self._listener_task:
            self._listener_task.cancel()
        for task in list(self._tasks):
            task.cancel()
        if self._redis is not None:
            await self._redis.aclose()

    def _spawn(self, coro) -> None:  # type: ignore[no-untyped-def]
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error("background_task_failed", error=repr(exc))

    # -------------------------------------------------- propiedad de la instancia
    #
    # Una instancia en vuelo tiene dueño (`driven_by`) y un vencimiento
    # (`lease_expires_at`). Solo el dueño la ejecuta. Sin esto, cada réplica recuperaba al
    # arrancar TODAS las instancias en vuelo y las ejecutaba en paralelo: medido en un cluster
    # de 3 réplicas, el mismo step corrido 3 veces y 3 transiciones a FAILED del mismo
    # expediente. La condición de disparo era cada deploy.
    #
    # Ver el ADR de la wiki "quién es dueño de una instancia en vuelo cuando el executor tiene
    # varias réplicas".

    @staticmethod
    async def _filas_afectadas(session: AsyncSession, sentencia: Any) -> int:
        """Ejecuta un UPDATE y devuelve cuántas filas tocó.

        Existe para no repetir el `cast`: `session.execute()` está tipado como `Result`, que no
        declara `rowcount`, aunque en tiempo de ejecución un UPDATE devuelve un `CursorResult`
        que sí lo tiene. El rowcount es lo que decide quién gana el reclamo, así que conviene
        que la conversión esté en un solo lugar y explicada.
        """
        resultado = cast(CursorResult[Any], await session.execute(sentencia))
        return int(resultado.rowcount)

    def _ahora(self) -> datetime:
        return datetime.now(timezone.utc)

    def _vencimiento(self) -> datetime:
        return self._ahora() + timedelta(seconds=self._settings.instance_lease_seconds)

    async def _tomar_lease(self, instance_id: uuid.UUID) -> bool:
        """Reclama la instancia. `True` solo si esta réplica se la quedó.

        Es un `UPDATE ... WHERE` y lo que decide es el **rowcount**: si otra réplica la tiene
        con lease vigente, el `WHERE` no matchea y el update afecta 0 filas. La garantía la
        sostiene la base, no el orden en que arrancan los pods — mismo criterio que el `UNIQUE`
        de registry, auditoría, idempotencia y los timers de rules.

        Reclamar de nuevo algo que ya es de esta réplica también cuenta como éxito: renueva y
        sigue (un `_drive` reentrante sobre la misma instancia no es un conflicto).
        """
        async with self._sessionmaker() as session:
            filas = await self._filas_afectadas(
                session,
                update(ProcessInstance)
                .where(
                    ProcessInstance.id == instance_id,
                    sa_or(
                        ProcessInstance.driven_by.is_(None),
                        ProcessInstance.driven_by == self._identidad,
                        ProcessInstance.lease_expires_at.is_(None),
                        ProcessInstance.lease_expires_at < self._ahora(),
                    ),
                )
                .values(driven_by=self._identidad, lease_expires_at=self._vencimiento()),
            )
            await session.commit()
        return bool(filas)

    async def _renovar_lease(self, instance_id: uuid.UUID) -> bool:
        """Extiende el lease. `False` si esta réplica ya no es la dueña.

        El `WHERE driven_by = yo` es lo que hace que una réplica que perdió la instancia
        —porque tardó tanto que el lease venció y otra la tomó— se entere en vez de seguir
        trabajando sobre algo que ya no le pertenece.
        """
        async with self._sessionmaker() as session:
            filas = await self._filas_afectadas(
                session,
                update(ProcessInstance)
                .where(
                    ProcessInstance.id == instance_id,
                    ProcessInstance.driven_by == self._identidad,
                )
                .values(lease_expires_at=self._vencimiento()),
            )
            await session.commit()
        return bool(filas)

    async def _soltar_lease(self, instance_id: uuid.UUID) -> None:
        """Libera la instancia al terminar el drive, sin esperar el vencimiento.

        No es imprescindible —el lease vencería solo— pero sin esto una instancia que quedó
        dormida en `WAITING_SIGNAL` seguiría marcada como "en manos de" una réplica durante un
        lease entero, y eso se lee mal cuando alguien mira la tabla para entender qué pasa.
        """
        async with self._sessionmaker() as session:
            await session.execute(
                update(ProcessInstance)
                .where(
                    ProcessInstance.id == instance_id,
                    ProcessInstance.driven_by == self._identidad,
                )
                .values(driven_by=None, lease_expires_at=None)
            )
            await session.commit()

    async def _renovar_hasta_que_termine(self, instance_id: uuid.UUID) -> None:
        """Renueva el lease mientras el drive trabaja.

        Renueva a un tercio del vencimiento: dos renovaciones perdidas seguidas todavía no
        pierden la instancia. Si el proceso muere, este loop muere con él, el lease vence y
        otra réplica puede tomar el trabajo — que es exactamente lo que `_recover()` existe
        para hacer.
        """
        intervalo = max(1.0, self._settings.instance_lease_seconds / 3)
        while not self._stopping:
            await asyncio.sleep(intervalo)
            try:
                if not await self._renovar_lease(instance_id):
                    log.warning("lease_perdido", instance_id=str(instance_id))
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — reintenta en el próximo ciclo
                log.error("lease_renovacion_fallida",
                          instance_id=str(instance_id), error=str(exc))

    async def _recover(self) -> None:
        """Al arrancar: retoma lo que quedó **huérfano**, no todo lo que esté en vuelo.

        La diferencia es el bug que arregló este método: antes recuperaba toda instancia en
        vuelo, así que N réplicas arrancando a la vez ejecutaban N veces el mismo expediente.
        Ahora el filtro es "sin dueño o con el lease vencido", y encima cada instancia se
        reclama con `_tomar_lease` antes de ejecutarla: si dos réplicas leen la misma fila a la
        vez, solo una gana el `UPDATE`.
        """
        ahora = self._ahora()
        async with self._sessionmaker() as session:
            in_flight = (await session.execute(
                select(ProcessInstance.id).where(
                    ProcessInstance.status.in_(("TRIGGERED", "IN_PROGRESS", "RETRYING")),
                    sa_or(
                        ProcessInstance.driven_by.is_(None),
                        ProcessInstance.lease_expires_at.is_(None),
                        ProcessInstance.lease_expires_at < ahora,
                    ),
                )
            )).scalars().all()
            waiting = (await session.execute(
                select(SignalRecord.instance_id).where(
                    SignalRecord.processed.is_(False))
            )).scalars().all()
        for instance_id in in_flight:
            log.info("recover_in_flight", instance_id=str(instance_id))
            self._spawn(self._drive(instance_id))
        # El path de señales no necesita lease: `_apply_signals_and_resume` abre la instancia
        # con FOR UPDATE y corta si el estado ya no es WAITING_SIGNAL, así que de N réplicas
        # solo una aplica. Ya era seguro para multi-réplica y se deja como estaba.
        for instance_id in set(waiting):
            log.info("recover_waiting_signal", instance_id=str(instance_id))
            self._spawn(self._apply_signals_and_resume(instance_id))

    # ------------------------------------------------------------- trigger

    async def trigger(self, flow_name: str, version: str, payload: dict[str, Any],
                      correlation_id: str | None = None,
                      idempotency_key: str | None = None) -> dict[str, Any]:
        if idempotency_key:
            repetido = await self._instancia_de(idempotency_key, flow_name, payload)
            if repetido is not None:
                return repetido

        resolved = await self._resolve_process(flow_name, version)
        if resolved is None:
            raise DomainError(
                f"process '{flow_name}' no encontrado en el dominio registrado", 404)
        proc, source_flow, source_version = resolved

        graph = build_stage_dag(proc)
        if not nx.is_directed_acyclic_graph(graph):
            log.warning("stage_graph_has_cycles", flow_name=flow_name)

        context = {
            "payload": payload,
            "steps": {},
            "signals": {},
            "_cursor": {"stage": 0, "step": 0},
        }
        async with self._sessionmaker() as session:
            instance = ProcessInstance(
                flow_name=proc.name,
                flow_version=source_version,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                status="TRIGGERED",
                trigger_payload=payload,
                context=context,
            )
            session.add(instance)
            try:
                await session.flush()
            except IntegrityError:
                # Dos disparos con la misma clave llegaron a la vez: los dos pasaron el
                # chequeo de arriba y el UNIQUE cortó a este. El que ganó ya creó la
                # instancia, así que se devuelve esa — que es lo que el cliente pidió.
                await session.rollback()
                repetido = await self._instancia_de(idempotency_key, flow_name, payload)
                if repetido is not None:
                    return repetido
                raise
            session.add(InstanceTransition(
                instance_id=instance.id, from_status="-", to_status="TRIGGERED"))
            instance_id = instance.id
            await session.commit()

        log.info("instance_triggered", instance_id=str(instance_id),
                 flow_name=proc.name, correlation_id=correlation_id,
                 idempotency_key=idempotency_key)
        self._spawn(self._drive(instance_id))
        return {"instance_id": str(instance_id), "status": "TRIGGERED"}

    async def _instancia_de(self, idempotency_key: str | None, flow_name: str,
                            payload: dict[str, Any]) -> dict[str, Any] | None:
        """La instancia que ya creó esta clave, si existe. `None` = es la primera vez.

        Si la clave existe pero el pedido es otro, levanta 409 en vez de devolver la vieja:
        el cliente pidió A y recibiría el resultado de B creyendo que A se disparó — un
        proceso de negocio que nunca ocurrió y que nadie sabría que falta.
        """
        if not idempotency_key:
            return None
        async with self._sessionmaker() as session:
            fila = await session.scalar(
                select(ProcessInstance).where(
                    ProcessInstance.idempotency_key == idempotency_key)
            )
        if fila is None:
            return None
        if fila.flow_name != flow_name or fila.trigger_payload != payload:
            raise DomainError(
                f"la Idempotency-Key '{idempotency_key}' ya se usó para otro pedido "
                f"(instancia {fila.id}, flow '{fila.flow_name}')", 409)
        log.info("instance_idempotent_replay", instance_id=str(fila.id),
                 flow_name=flow_name, idempotency_key=idempotency_key)
        return {"instance_id": str(fila.id), "status": fila.status,
                "idempotent_replay": True}

    async def _resolve_process(
        self, flow_name: str, version: str
    ) -> tuple[ProcessDef, str, str] | None:
        if version in ("", "latest"):
            return await self._domain.find_process(flow_name)
        # versión explícita: buscar el flow registrado y el proceso dentro
        from teleflow.common.models import FlowDefinition

        async with self._sessionmaker() as session:
            row = await session.scalar(select(FlowDefinition).where(
                FlowDefinition.name == flow_name,
                FlowDefinition.version == version))
        if row is None:
            return await self._domain.find_process(flow_name)
        from teleflow.dsl.parser import get_parser

        flow = get_parser().parse(row.source)
        proc = flow.processes.get(flow_name)
        if proc is None and len(flow.processes) == 1:
            proc = next(iter(flow.processes.values()))
        if proc is None:
            return None
        return proc, row.name, row.version

    # --------------------------------------------------------------- drive

    async def _drive(self, instance_id: uuid.UUID) -> None:
        # Reclamar ANTES del semáforo: si otra réplica la tiene, no hay que ocupar un worker
        # para descubrirlo.
        if not await self._tomar_lease(instance_id):
            log.info("instancia_con_otro_dueno", instance_id=str(instance_id))
            return
        renovacion = asyncio.create_task(self._renovar_hasta_que_termine(instance_id))
        self._renovaciones[instance_id] = renovacion
        try:
            async with self._semaphore:
                try:
                    await self._run(instance_id)
                except asyncio.CancelledError:
                    raise
                except StepFailed as exc:
                    await self._mark_failed(instance_id, exc.step_name, str(exc))
                except Exception as exc:
                    log.exception("instance_crashed", instance_id=str(instance_id))
                    await self._mark_failed(instance_id, None, f"error interno: {exc}")
        finally:
            renovacion.cancel()
            self._renovaciones.pop(instance_id, None)
            # Soltar el lease aunque el drive haya fallado: si no, la instancia queda marcada
            # como "en manos de" esta réplica un lease entero y nadie más la puede retomar.
            try:
                await self._soltar_lease(instance_id)
            except Exception as exc:  # noqa: BLE001 — vencería solo; no vale tumbar el drive
                log.error("lease_liberacion_fallida",
                          instance_id=str(instance_id), error=str(exc))

    async def _run(self, instance_id: uuid.UUID) -> None:
        snapshot = await self._load(instance_id)
        if snapshot is None or snapshot["status"] in ("COMPLETED", "COMPENSATED"):
            return
        flow_name = snapshot["flow_name"]
        resolved = await self._resolve_process(flow_name, snapshot["flow_version"])
        if resolved is None:
            raise StepFailed("-", f"process '{flow_name}' ya no existe en el dominio")
        proc, _, _ = resolved
        domain = await self._domain.load()
        steps_map = domain.merged.steps
        integrations = domain.merged.integrations

        ctx: dict[str, Any] = snapshot["context"]
        cursor = ctx.setdefault("_cursor", {"stage": 0, "step": 0})

        if snapshot["status"] != "IN_PROGRESS":
            await self._set_status(instance_id, snapshot["status"], "IN_PROGRESS")

        stage_index = {s.name: i for i, s in enumerate(proc.stages)}
        ramas = ramas_por_decision(proc)
        visited_decisions = 0

        def avanzar() -> None:
            """Cae al stage siguiente. `_cursor["rama"]` recuerda de qué decisión venimos, que
            es lo que `siguiente_stage()` necesita para no derramar una rama sobre otra."""
            cursor["stage"] = siguiente_stage(
                proc, ramas, cursor["stage"], cursor.get("rama"))

        while cursor["stage"] < len(proc.stages):
            stage: StageDef = proc.stages[cursor["stage"]]

            if stage.mode == "parallel":
                pending = [steps_map[r.target] for r in stage.steps[cursor["step"]:]]
                results = await asyncio.gather(
                    *[self._run_step(s, integrations, ctx, flow_name) for s in pending],
                    return_exceptions=True,
                )
                for step_def, result in zip(pending, results):
                    if isinstance(result, BaseException):
                        raise StepFailed(step_def.name, str(result))
                    ctx["steps"][step_def.name] = result
                    await self._record_step(instance_id, step_def.name, result)
                cursor["step"] = 0
                avanzar()
                await self._save_progress(instance_id, ctx, None)
                continue

            # sequential / decision: steps en orden
            while cursor["step"] < len(stage.steps):
                step_ref: Ref = stage.steps[cursor["step"]]
                step_def = steps_map[step_ref.target]

                if step_def.type == "human_task" \
                        and step_def.name not in ctx["signals"]:
                    # ---- durable sleep: contexto a Postgres, worker liberado
                    await self._save_progress(instance_id, ctx, step_def.name,
                                              status="WAITING_SIGNAL")
                    log.info("instance_sleeping", instance_id=str(instance_id),
                             flow_name=flow_name, step_name=step_def.name)
                    return

                output = await self._run_step(step_def, integrations, ctx, flow_name)
                ctx["steps"][step_def.name] = output
                cursor["step"] += 1
                await self._save_progress(instance_id, ctx, step_def.name)
                await self._record_step(instance_id, step_def.name, output)
                await self._apply_step_actions(step_def, ctx)

            # stage terminado: decidir siguiente
            if stage.mode == "decision":
                visited_decisions += 1
                if visited_decisions > 100:
                    raise StepFailed(stage.name, "loop infinito en stages decision")
                target = self._next_branch(stage, ctx)
                if target is None:
                    # Ninguna rama aplicó: cae como cualquier stage, y deja de estar dentro
                    # de la rama anterior.
                    cursor.pop("rama", None)
                    avanzar()
                elif target == "end":  # branch terminal: -> stage.end
                    cursor["stage"] = len(proc.stages)
                else:
                    cursor["stage"] = stage_index[target]
                    cursor["rama"] = stage.name
            else:
                avanzar()
            cursor["step"] = 0
            await self._save_progress(instance_id, ctx, None)

        # ------------------------------------------------------- completado
        await self._apply_actions(proc.name, proc.on_complete, ctx)
        await self._set_status(instance_id, "IN_PROGRESS", "COMPLETED")
        INSTANCES_TOTAL.labels(flow_name, "COMPLETED").inc()
        log.info("instance_completed", instance_id=str(instance_id),
                 flow_name=flow_name)

    def _next_branch(self, stage: StageDef, ctx: dict[str, Any]) -> str | None:
        eval_ctx = {**ctx, **ctx.get("payload", {})}
        else_target: str | None = None
        for branch in stage.branches:
            if branch.condition is None:
                else_target = branch.target.target
                continue
            if evaluate(branch.condition, eval_ctx):
                return branch.target.target
        return else_target

    # ---------------------------------------------------------------- steps

    async def _run_step(self, step: StepDef, integrations: dict[str, Any], ctx: dict[str, Any],
                        flow_name: str) -> dict[str, Any]:
        integration = (integrations.get(step.integration.target)
                       if step.integration else None)
        eval_ctx = {**ctx, **ctx.get("payload", {})}
        retries = max(0, step.retries)
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                if step.type == "automated":
                    output = await adapters.run_automated(step, integration, eval_ctx)
                elif step.type == "notification":
                    output = await adapters.run_notification(step, integration, eval_ctx)
                elif step.type == "decision":
                    output = {"result": bool(evaluate(step.condition, eval_ctx))
                              if step.condition is not None else True}
                elif step.type == "human_task":
                    output = {"signal": ctx["signals"][step.name]}
                else:
                    raise StepFailed(step.name, f"tipo desconocido: {step.type}")
                STEPS_TOTAL.labels(flow_name, step.name, "ok").inc()
                return output
            except asyncio.CancelledError:
                raise
            except adapters.RetryableStepError as exc:
                last_error = exc
                STEPS_TOTAL.labels(flow_name, step.name, "error").inc()
                log.warning("step_attempt_failed", flow_name=flow_name,
                            step_name=step.name, attempt=attempt + 1,
                            attempts=retries + 1, error=str(exc))
                if attempt < retries:
                    await asyncio.sleep(self._retry_delay(attempt))
            except Exception as exc:
                # permanente (400, credencial mala, config, bug): reintentar es
                # tirar la ventana de reintentos a la basura. Falla ya.
                STEPS_TOTAL.labels(flow_name, step.name, "error").inc()
                log.warning("step_failed_permanent", flow_name=flow_name,
                            step_name=step.name, attempt=attempt + 1, error=str(exc))
                raise StepFailed(step.name, f"error permanente: {exc}") from exc

        raise StepFailed(step.name,
                         f"step agotó {retries + 1} intentos: {last_error}")

    def _retry_delay(self, attempt: int) -> float:
        """Backoff exponencial con full jitter: evita que N steps reintenten al unísono."""
        return full_jitter_delay(attempt, self._settings.step_retry_base_delay,
                                 self._settings.step_retry_max_delay)

    async def _apply_step_actions(self, step: StepDef, ctx: dict[str, Any]) -> None:
        await self._apply_actions(step.name, step.on_complete, ctx)

    async def _apply_actions(self, origin: str, actions: list[Any], ctx: dict[str, Any]) -> None:
        payload = ctx.get("payload", {})
        for action in actions:
            if action.kind == "emit":
                await self._bus.publish(action.event, {
                    "event": action.event, "subject": origin,
                    "subject_kind": "process", "payload": payload,
                    "steps": {k: v for k, v in ctx.get("steps", {}).items()},
                })
            elif action.kind == "transition" and action.target is not None:
                # transition entity.nino via "inscribir" — el id se toma por
                # convención del payload: <entity>_id
                entity_type = action.target.target
                entity_id = payload.get(f"{entity_type}_id")
                if entity_id is None:
                    log.warning("transition_action_skipped", origin=origin,
                                entity_type=entity_type,
                                reason=f"payload sin '{entity_type}_id'")
                    continue
                try:
                    if action.target.kind == "relation":
                        await self._entities.transition_relation(
                            entity_type, str(entity_id), action.via or "")
                    else:
                        await self._entities.transition_entity(
                            entity_type, str(entity_id), action.via or "")
                except DomainError as exc:
                    log.warning("transition_action_failed", origin=origin,
                                entity_type=entity_type, error=str(exc))

    # -------------------------------------------------------------- señales

    async def signal(self, instance_id: uuid.UUID, step_name: str, signal: str,
                     actor_id: str | None, signal_data: dict[str, Any],
                     signal_id: str | None = None) -> dict[str, Any]:
        snapshot = await self._load(instance_id)
        if snapshot is None:
            raise DomainError("instancia no encontrada", 404)
        if snapshot["status"] != "WAITING_SIGNAL":
            raise DomainError(
                f"la instancia está en {snapshot['status']}, no espera señal", 409)

        domain = await self._domain.load()
        step_def = domain.merged.steps.get(step_name)
        if step_def is not None and step_def.signals and signal not in step_def.signals:
            raise DomainError(
                f"señal '{signal}' no válida para {step_name}: {step_def.signals}", 422)

        key = signal_id or f"{instance_id}:{step_name}:{signal}"
        async with self._sessionmaker() as session:
            record = SignalRecord(
                instance_id=instance_id, step_name=step_name, signal=signal,
                actor_id=actor_id, signal_data=signal_data, signal_key=key,
            )
            session.add(record)
            duplicate = False
            try:
                await session.commit()  # audit log + idempotencia
            except IntegrityError:
                # ya registrada: no se duplica el efecto, pero se re-publica
                # la reactivación (idempotente) por si el mensaje se perdió
                duplicate = True
                log.info("signal_duplicate", instance_id=str(instance_id),
                         signal_key=key)

        assert self._redis is not None
        await self._redis.publish(
            f"{SIGNAL_CHANNEL_PREFIX}{instance_id}",
            json.dumps({"step_name": step_name, "signal": signal,
                        "actor_id": actor_id}),
        )
        log.info("signal_published", instance_id=str(instance_id),
                 step_name=step_name, signal=signal, actor_id=actor_id)
        return {"instance_id": str(instance_id), "status": "SIGNALED",
                "duplicate": duplicate}

    async def _signal_listener(self) -> None:
        """Suscripción a señales con reconexión: el listener nunca muere."""
        while not self._stopping:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("signal_listener_crashed_restarting", error=repr(exc))
                await asyncio.sleep(3)

    async def _listen_once(self) -> None:
        import redis.exceptions as redis_exc

        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{SIGNAL_CHANNEL_PREFIX}*")
        log.info("signal_listener_started")
        try:
            while not self._stopping:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=5.0)
                except (TimeoutError, redis_exc.TimeoutError):
                    continue  # timeout periódico: la suscripción sigue viva
                if message is None or message.get("type") != "pmessage":
                    continue
                try:
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")
                    instance_id = uuid.UUID(
                        str(channel).removeprefix(SIGNAL_CHANNEL_PREFIX))
                    self._spawn(self._apply_signals_and_resume(instance_id))
                except Exception as exc:
                    log.error("signal_listener_message_error", error=repr(exc))
        finally:
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def _apply_signals_and_resume(self, instance_id: uuid.UUID) -> None:
        async with self._sessionmaker() as session:
            instance = await session.get(ProcessInstance, instance_id,
                                         with_for_update=True)
            if instance is None or instance.status != "WAITING_SIGNAL":
                return
            signals = (await session.execute(
                select(SignalRecord).where(
                    SignalRecord.instance_id == instance_id,
                    SignalRecord.processed.is_(False),
                ).order_by(SignalRecord.created_at)
            )).scalars().all()
            if not signals:
                return
            ctx = dict(instance.context)
            sig_ctx = dict(ctx.get("signals", {}))
            for record in signals:
                sig_ctx[record.step_name] = {
                    "signal": record.signal,
                    "actor_id": record.actor_id,
                    "data": record.signal_data,
                }
                record.processed = True
            ctx["signals"] = sig_ctx
            # avanzar el cursor más allá del human_task que dormía
            instance.context = ctx
            instance.status = "IN_PROGRESS"
            session.add(InstanceTransition(
                instance_id=instance_id, from_status="WAITING_SIGNAL",
                to_status="IN_PROGRESS", step_name=instance.current_step,
                actor_id=signals[-1].actor_id))
            await session.commit()
        log.info("instance_resumed", instance_id=str(instance_id))
        self._spawn(self._drive(instance_id))

    # ---------------------------------------------------------------- retry

    async def retry(self, instance_id: uuid.UUID) -> dict[str, Any]:
        snapshot = await self._load(instance_id)
        if snapshot is None:
            raise DomainError("instancia no encontrada", 404)
        if snapshot["status"] != "FAILED":
            raise DomainError(
                f"solo instancias FAILED pueden reintentarse "
                f"(actual: {snapshot['status']})", 409)
        await self._set_status(instance_id, "FAILED", "RETRYING")
        await self._set_status(instance_id, "RETRYING", "IN_PROGRESS",
                               clear_error=True)
        self._spawn(self._drive(instance_id))
        return {"instance_id": str(instance_id), "status": "RETRYING"}

    # ------------------------------------------------------------ persistencia

    async def _load(self, instance_id: uuid.UUID) -> dict[str, Any] | None:
        async with self._sessionmaker() as session:
            instance = await session.get(ProcessInstance, instance_id)
            if instance is None:
                return None
            return {
                "id": instance.id,
                "flow_name": instance.flow_name,
                "flow_version": instance.flow_version,
                "status": instance.status,
                "context": dict(instance.context),
                "current_step": instance.current_step,
            }

    async def _save_progress(self, instance_id: uuid.UUID, ctx: dict[str, Any],
                             current_step: str | None,
                             status: str | None = None) -> None:
        values: dict[str, Any] = {"context": ctx, "current_step": current_step}
        if status is not None:
            values["status"] = status
        async with self._sessionmaker() as session:
            await session.execute(
                update(ProcessInstance).where(
                    ProcessInstance.id == instance_id).values(**values))
            if status is not None:
                session.add(InstanceTransition(
                    instance_id=instance_id, from_status="IN_PROGRESS",
                    to_status=status, step_name=current_step))
            await session.commit()

    async def _record_step(self, instance_id: uuid.UUID, step_name: str,
                           output: dict[str, Any]) -> None:
        async with self._sessionmaker() as session:
            session.add(InstanceTransition(
                instance_id=instance_id, from_status="IN_PROGRESS",
                to_status="IN_PROGRESS", step_name=step_name, step_output=output))
            await session.commit()

    async def _set_status(self, instance_id: uuid.UUID, from_status: str,
                          to_status: str, clear_error: bool = False) -> bool:
        """Cambia el estado **solo si sigue siendo el que se creía**, y devuelve si lo logró.

        Antes era un `UPDATE` incondicional, y por eso no podía detectar que otro proceso se le
        había adelantado: dos réplicas ejecutando el mismo expediente escribían las dos su
        transición, y `instance_transitions` terminaba con tres `IN_PROGRESS → FAILED` del mismo
        step. El lease es lo que evita que lleguen dos; esta guarda es la segunda red, y hace
        que la carrera —si alguna vez vuelve— sea visible en vez de silenciosa.
        """
        values: dict[str, Any] = {"status": to_status}
        if clear_error:
            values["error"] = None
        async with self._sessionmaker() as session:
            filas = await self._filas_afectadas(
                session,
                update(ProcessInstance).where(
                    ProcessInstance.id == instance_id,
                    ProcessInstance.status == from_status,
                ).values(**values))
            if not filas:
                await session.rollback()
                log.warning("transicion_descartada", instance_id=str(instance_id),
                            esperaba=from_status, hacia=to_status)
                return False
            session.add(InstanceTransition(
                instance_id=instance_id, from_status=from_status,
                to_status=to_status))
            await session.commit()
        return True

    async def _mark_failed(self, instance_id: uuid.UUID, step_name: str | None,
                           message: str) -> None:
        async with self._sessionmaker() as session:
            # `with_for_update` + chequeo de estado: este es el método que escribió las tres
            # transiciones `IN_PROGRESS → FAILED` del mismo expediente cuando tres réplicas lo
            # ejecutaban en paralelo. Una instancia ya fallada no vuelve a fallar, y el que
            # llega segundo no tiene nada que registrar.
            instance = await session.get(ProcessInstance, instance_id, with_for_update=True)
            if instance is None:
                return
            if instance.status in ("FAILED", "COMPLETED", "COMPENSATED"):
                log.warning("fallo_descartado_instancia_ya_terminal",
                            instance_id=str(instance_id), estado=instance.status)
                return
            flow_name = instance.flow_name
            estado_previo = instance.status
            instance.status = "FAILED"
            instance.error = {"step": step_name, "message": message}
            session.add(InstanceTransition(
                instance_id=instance_id, from_status=estado_previo,
                to_status="FAILED", step_name=step_name,
                step_output={"error": message}))
            await session.commit()
        INSTANCES_TOTAL.labels(flow_name, "FAILED").inc()
        log.error("instance_failed", instance_id=str(instance_id),
                  flow_name=flow_name, step_name=step_name, error=message)
