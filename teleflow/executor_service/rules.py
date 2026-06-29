"""Rule engine event-driven (sección 6 del documento).

- on_event / on_state / on_relation: consumidor RabbitMQ (binding '#')
  evalúa condition y dispara el proceso vía el engine.
- on_timer: scanner periódico que busca eventos `since` más viejos que
  `after` cuya condición sigue siendo verdadera; rule_timer_log evita
  re-disparos sobre el mismo sujeto.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.config import Settings
from teleflow.common.logging import get_logger
from teleflow.common.models import EntityEvent, EntityState, RelationState, RuleTimerLog
from teleflow.dsl.ast_nodes import RuleDef
from teleflow.dsl.evaluator import evaluate
from teleflow.executor_service.domain import DomainLoader
from teleflow.executor_service.engine import ExecutionEngine
from teleflow.executor_service.events import EventBus

log = get_logger(component="rule-engine")


class RuleEngine:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession],
                 domain_loader: DomainLoader, event_bus: EventBus,
                 engine: ExecutionEngine, settings: Settings):
        self._sessionmaker = sessionmaker
        self._domain = domain_loader
        self._bus = event_bus
        self._engine = engine
        self._settings = settings
        self._consumer_task: asyncio.Task | None = None
        self._timer_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._consumer_task = asyncio.create_task(self._consume_forever())
        self._timer_task = asyncio.create_task(self._timer_loop())

    async def stop(self) -> None:
        for task in (self._consumer_task, self._timer_task):
            if task:
                task.cancel()

    # ------------------------------------------------------------ consumidor

    async def _consume_forever(self) -> None:
        while True:
            try:
                await self._bus.consume("teleflow.rules", self._on_event)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("rule_consumer_error", error=str(exc))
                await asyncio.sleep(5)

    async def _on_event(self, routing_key: str, message: dict[str, Any]) -> None:
        domain = await self._domain.load()
        event_name = str(message.get("event", routing_key))
        subject = str(message.get("subject", ""))
        subject_kind = str(message.get("subject_kind", ""))
        state = message.get("state")

        for rule in domain.merged.rules.values():
            matched = False
            if rule.on_event is not None and rule.on_event == event_name:
                matched = True
            elif rule.on_state is not None and state is not None \
                    and rule.on_state == f"{subject}.{state}":
                matched = True
            elif rule.on_relation is not None and subject_kind == "relation" \
                    and subject == rule.on_relation \
                    and event_name == f"relation.{subject}.created":
                matched = True
            if not matched:
                continue
            try:
                await self._fire(rule, message)
            except Exception as exc:
                log.error("rule_fire_failed", rule=rule.name, error=str(exc))

    async def _fire(self, rule: RuleDef, message: dict[str, Any]) -> None:
        ctx = await self._build_context(message)
        if rule.condition is not None and not evaluate(rule.condition, ctx):
            log.info("rule_condition_false", rule=rule.name)
            return
        if rule.execute is None:
            return

        if rule.with_map:
            payload = {k: evaluate(expr, ctx) for k, expr in rule.with_map.items()}
        else:
            payload = dict(message.get("payload", {}))
            for key in ("entity_id", "relation_id", "from_id", "to_id"):
                if key in message:
                    payload.setdefault(key, message[key])

        process_name = rule.execute.target
        log.info("rule_fired", rule=rule.name, process=process_name)
        await self._engine.trigger(
            process_name, "latest", payload,
            correlation_id=f"rule:{rule.name}:{message.get('event', '')}",
        )

    async def _build_context(self, message: dict[str, Any]) -> dict[str, Any]:
        """Contexto para condition/with: event.*, entity.*, relation.*"""
        payload = dict(message.get("payload", {}))
        event_ctx: dict[str, Any] = {**message, **payload}
        ctx: dict[str, Any] = {"event": event_ctx, "payload": payload}
        subject = str(message.get("subject", ""))

        async with self._sessionmaker() as session:
            if message.get("subject_kind") == "entity" and message.get("entity_id"):
                row = await session.scalar(select(EntityState).where(
                    EntityState.entity_type == subject,
                    EntityState.entity_id == str(message["entity_id"])))
                if row is not None:
                    snapshot = {**row.campos, "estado": row.estado, "id": row.entity_id}
                    event_ctx["entity"] = snapshot
                    ctx["entity"] = {subject: snapshot, **snapshot}
            if message.get("subject_kind") == "relation" and message.get("relation_id"):
                try:
                    rid = uuid.UUID(str(message["relation_id"]))
                    row = await session.get(RelationState, rid)
                except ValueError:
                    row = None
                if row is not None:
                    snapshot = {**row.campos, "estado": row.estado,
                                "from_id": row.from_id, "to_id": row.to_id,
                                "id": str(row.id)}
                    event_ctx["relation"] = snapshot
                    event_ctx.setdefault("from_id", row.from_id)
                    event_ctx.setdefault("to_id", row.to_id)
                    ctx["relation"] = {subject: snapshot, **snapshot}
        return ctx

    # ---------------------------------------------------------------- timers

    async def _timer_loop(self) -> None:
        interval = max(5, self._settings.timer_scan_interval)
        while True:
            try:
                await asyncio.sleep(interval)
                await self._scan_timers()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("timer_scan_error", error=str(exc))

    async def _scan_timers(self) -> None:
        domain = await self._domain.load()
        timer_rules = [r for r in domain.merged.rules.values() if r.timer is not None]
        if not timer_rules:
            return
        now = datetime.now(timezone.utc)
        for rule in timer_rules:
            assert rule.timer is not None
            cutoff = now - timedelta(seconds=rule.timer.after_seconds)
            async with self._sessionmaker() as session:
                events = (await session.execute(
                    select(EntityEvent).where(
                        EntityEvent.event_name == rule.timer.since,
                        EntityEvent.occurred_at <= cutoff,
                    ).order_by(EntityEvent.occurred_at).limit(500)
                )).scalars().all()
            for event in events:
                await self._check_timer_event(rule, event)

    async def _check_timer_event(self, rule: RuleDef, event: EntityEvent) -> None:
        subject_key = f"{event.entity_type}:{event.entity_id}"
        async with self._sessionmaker() as session:
            already = await session.scalar(select(RuleTimerLog).where(
                RuleTimerLog.rule_name == rule.name,
                RuleTimerLog.subject_key == subject_key))
            if already is not None:
                return

        message = {
            "event": rule.timer.since if rule.timer else "",
            "subject": event.entity_type,
            "subject_kind": "relation" if "relation_id" in event.payload else "entity",
            "entity_id": event.entity_id,
            "relation_id": event.payload.get("relation_id"),
            "from_id": event.payload.get("from_id"),
            "to_id": event.payload.get("to_id"),
            "payload": dict(event.payload),
        }
        ctx = await self._build_context(message)
        assert rule.timer is not None
        if rule.timer.condition is not None and not evaluate(rule.timer.condition, ctx):
            return  # la condición dejó de cumplirse: no disparar (aún)

        async with self._sessionmaker() as session:
            session.add(RuleTimerLog(rule_name=rule.name, subject_key=subject_key))
            try:
                await session.commit()
            except IntegrityError:
                return  # otro worker ya lo disparó

        if rule.with_map:
            payload = {k: evaluate(expr, ctx) for k, expr in rule.with_map.items()}
        else:
            payload = dict(event.payload)
        if rule.execute is not None:
            log.info("timer_rule_fired", rule=rule.name, subject=subject_key)
            await self._engine.trigger(
                rule.execute.target, "latest", payload,
                correlation_id=f"timer:{rule.name}:{subject_key}",
            )
