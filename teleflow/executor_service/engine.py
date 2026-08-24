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
import uuid
from typing import Any

import networkx as nx
import redis.asyncio as aioredis
from prometheus_client import Counter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger
from teleflow.common.models import InstanceTransition, ProcessInstance, SignalRecord
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


def build_stage_dag(proc: ProcessDef) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    names = [s.name for s in proc.stages]
    graph.add_nodes_from(names)
    for i, stage in enumerate(proc.stages):
        if stage.mode == "decision":
            for branch in stage.branches:
                graph.add_edge(stage.name, branch.target.target)
        elif i + 1 < len(names):
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
        self._tasks: set[asyncio.Task] = set()
        self._listener_task: asyncio.Task | None = None
        self._stopping = False

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

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error("background_task_failed", error=repr(exc))

    async def _recover(self) -> None:
        """Al arrancar: retoma instancias en vuelo y dormidas con señal pendiente."""
        async with self._sessionmaker() as session:
            in_flight = (await session.execute(
                select(ProcessInstance.id).where(
                    ProcessInstance.status.in_(("TRIGGERED", "IN_PROGRESS", "RETRYING"))
                )
            )).scalars().all()
            waiting = (await session.execute(
                select(SignalRecord.instance_id).where(
                    SignalRecord.processed.is_(False))
            )).scalars().all()
        for instance_id in in_flight:
            log.info("recover_in_flight", instance_id=str(instance_id))
            self._spawn(self._drive(instance_id))
        for instance_id in set(waiting):
            log.info("recover_waiting_signal", instance_id=str(instance_id))
            self._spawn(self._apply_signals_and_resume(instance_id))

    # ------------------------------------------------------------- trigger

    async def trigger(self, flow_name: str, version: str, payload: dict[str, Any],
                      correlation_id: str | None = None) -> dict[str, Any]:
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
                status="TRIGGERED",
                trigger_payload=payload,
                context=context,
            )
            session.add(instance)
            await session.flush()
            session.add(InstanceTransition(
                instance_id=instance.id, from_status="-", to_status="TRIGGERED"))
            instance_id = instance.id
            await session.commit()

        log.info("instance_triggered", instance_id=str(instance_id),
                 flow_name=proc.name, correlation_id=correlation_id)
        self._spawn(self._drive(instance_id))
        return {"instance_id": str(instance_id), "status": "TRIGGERED"}

    async def _resolve_process(self, flow_name: str, version: str):
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
        visited_decisions = 0

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
                cursor["stage"] += 1
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
                    cursor["stage"] += 1
                elif target == "end":  # branch terminal: -> stage.end
                    cursor["stage"] = len(proc.stages)
                else:
                    cursor["stage"] = stage_index[target]
            else:
                cursor["stage"] += 1
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

    async def _run_step(self, step: StepDef, integrations: dict, ctx: dict[str, Any],
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
            except Exception as exc:
                last_error = exc
                STEPS_TOTAL.labels(flow_name, step.name, "error").inc()
                log.warning("step_attempt_failed", flow_name=flow_name,
                            step_name=step.name, attempt=attempt + 1, error=str(exc))
                if attempt < retries:
                    await asyncio.sleep(min(2 ** attempt, 30))

        raise StepFailed(step.name,
                         f"step agotó {retries + 1} intentos: {last_error}")

    async def _apply_step_actions(self, step: StepDef, ctx: dict[str, Any]) -> None:
        await self._apply_actions(step.name, step.on_complete, ctx)

    async def _apply_actions(self, origin: str, actions: list, ctx: dict[str, Any]) -> None:
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
            await pubsub.aclose()

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
                          to_status: str, clear_error: bool = False) -> None:
        values: dict[str, Any] = {"status": to_status}
        if clear_error:
            values["error"] = None
        async with self._sessionmaker() as session:
            await session.execute(
                update(ProcessInstance).where(
                    ProcessInstance.id == instance_id).values(**values))
            session.add(InstanceTransition(
                instance_id=instance_id, from_status=from_status,
                to_status=to_status))
            await session.commit()

    async def _mark_failed(self, instance_id: uuid.UUID, step_name: str | None,
                           message: str) -> None:
        async with self._sessionmaker() as session:
            instance = await session.get(ProcessInstance, instance_id)
            if instance is None:
                return
            flow_name = instance.flow_name
            instance.status = "FAILED"
            instance.error = {"step": step_name, "message": message}
            session.add(InstanceTransition(
                instance_id=instance_id, from_status="IN_PROGRESS",
                to_status="FAILED", step_name=step_name,
                step_output={"error": message}))
            await session.commit()
        INSTANCES_TOTAL.labels(flow_name, "FAILED").inc()
        log.error("instance_failed", instance_id=str(instance_id),
                  flow_name=flow_name, step_name=step_name, error=message)
