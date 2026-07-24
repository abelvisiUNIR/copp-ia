"""Vista 360 del objeto de negocio (sección 7 del documento).

Agrega en una sola respuesta: estado de la entity, relaciones activas e
históricas, procesos en vuelo, alertas de reglas y línea de tiempo.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.logging import get_logger
from teleflow.common.models import (
    EntityEvent,
    EntityState,
    ProcessInstance,
    RelationState,
)
from teleflow.dsl.ast_nodes import RelationDef, View360Def
from teleflow.dsl.evaluator import evaluate
from teleflow.executor_service.domain import DomainLoader
from teleflow.executor_service.entities import DomainError

log = get_logger(component="view360")

ACTIVE_STATUSES = ("TRIGGERED", "IN_PROGRESS", "WAITING_SIGNAL", "RETRYING")


class View360Service:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession],
                 domain_loader: DomainLoader):
        self._sessionmaker = sessionmaker
        self._domain = domain_loader

    async def build(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        domain = await self._domain.load()
        view = self._find_view(domain.merged.views, entity_type)

        async with self._sessionmaker() as session:
            entity = await session.scalar(select(EntityState).where(
                EntityState.entity_type == entity_type,
                EntityState.entity_id == entity_id))
            if entity is None:
                raise DomainError(f"{entity_type}/{entity_id} no encontrado", 404)

            relations = await self._build_relations(session, domain, view,
                                                    entity_type, entity_id)
            processes = await self._build_processes(session, view,
                                                    entity_type, entity_id)
            timeline = await self._build_timeline(session, view,
                                                  entity_type, entity_id, relations)
            alerts = await self._build_alerts(domain, view, relations, entity)

        return {
            "entity": entity_type,
            "id": entity_id,
            "estado_actual": entity.estado,
            "campos": entity.campos,
            "relaciones_activas": [r for r in relations if r.get("_activa")],
            "relaciones_historicas": [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in relations if not r.get("_activa")
            ],
            "procesos_activos": processes,
            "alertas": alerts,
            "timeline": timeline,
        }

    def _find_view(self, views: dict[str, View360Def],
                   entity_type: str) -> View360Def | None:
        for view in views.values():
            if view.entity is not None and view.entity.target == entity_type:
                return view
        return views.get(entity_type)

    async def _build_relations(self, session: AsyncSession, domain: Any,
                               view: View360Def | None,
                               entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        rel_types = ([vr.relation.target for vr in view.relations]
                     if view and view.relations
                     else list(domain.merged.relations.keys()))
        results: list[dict[str, Any]] = []
        for rel_type in dict.fromkeys(rel_types):
            rel_def = domain.merged.relations.get(rel_type)
            rows = (await session.execute(select(RelationState).where(
                RelationState.relation_type == rel_type,
                or_(RelationState.from_id == entity_id,
                    RelationState.to_id == entity_id)))).scalars().all()
            for row in rows:
                other_id = row.to_id if row.from_id == entity_id else row.from_id
                other_type = None
                if rel_def is not None:
                    if row.from_id == entity_id and rel_def.to_ref is not None:
                        other_type = rel_def.to_ref.target
                    elif rel_def.from_ref is not None:
                        other_type = rel_def.from_ref.target
                item: dict[str, Any] = {
                    "tipo": rel_type,
                    "relation_id": str(row.id),
                    "estado": row.estado,
                    **row.campos,
                }
                if other_type:
                    other = await session.scalar(select(EntityState).where(
                        EntityState.entity_type == other_type,
                        EntityState.entity_id == other_id))
                    if other is not None:
                        item[other_type] = {"id": other_id, **other.campos}
                        nombre = other.campos.get("nombre")
                        if nombre:
                            item[f"{other_type}_nombre"] = nombre
                terminal = self._is_terminal(rel_def, row.estado)
                item["_activa"] = not terminal
                results.append(item)
        return results

    def _is_terminal(self, rel_def: RelationDef | None, estado: str) -> bool:
        if rel_def is None or rel_def.lifecycle is None:
            return False
        outgoing = {t.from_state for t in rel_def.lifecycle.transitions}
        return estado not in outgoing

    async def _build_processes(self, session: AsyncSession, view: View360Def | None,
                               entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        query = select(ProcessInstance).where(
            ProcessInstance.status.in_(ACTIVE_STATUSES))
        if view is not None and view.active_processes \
                and view.active_processes.include:
            names = [r.target for r in view.active_processes.include]
            query = query.where(ProcessInstance.flow_name.in_(names))
        rows = (await session.execute(query.limit(200))).scalars().all()
        key = f"{entity_type}_id"
        out = []
        for row in rows:
            payload = row.trigger_payload or {}
            if str(payload.get(key, "")) != entity_id:
                continue
            out.append({
                "flow": row.flow_name,
                "instance_id": str(row.id),
                "status": row.status,
                "current_step": row.current_step,
            })
        return out

    async def _build_timeline(self, session: AsyncSession, view: View360Def | None,
                              entity_type: str, entity_id: str,
                              relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limit = view.timeline.limit if view and view.timeline else 50
        order_desc = not (view and view.timeline and view.timeline.order == "asc")
        rel_ids = [r["relation_id"] for r in relations]
        query = select(EntityEvent).where(or_(
            (EntityEvent.entity_type == entity_type)
            & (EntityEvent.entity_id == entity_id),
            EntityEvent.entity_id.in_(rel_ids) if rel_ids else false(),
        ))
        query = query.order_by(
            EntityEvent.occurred_at.desc() if order_desc
            else EntityEvent.occurred_at.asc()).limit(limit)
        rows = (await session.execute(query)).scalars().all()
        return [{
            "fecha": row.occurred_at.isoformat(),
            "evento": row.event_name,
            "detalle": row.payload.get("detalle", ""),
        } for row in rows]

    async def _build_alerts(self, domain: Any, view: View360Def | None,
                            relations: list[dict[str, Any]],
                            entity: EntityState) -> list[dict[str, Any]]:
        if view is None or not view.alerts:
            return []
        alerts: list[dict[str, Any]] = []
        entity_snapshot = {**entity.campos, "estado": entity.estado,
                           "id": entity.entity_id}
        for alert_ref in view.alerts:
            rule = domain.merged.rules.get(alert_ref.target)
            if rule is None:
                continue
            condition = rule.timer.condition if rule.timer else rule.condition
            if condition is None:
                continue
            # evaluar la condición contra la entity y cada relación activa
            base_ctx = {"entity": entity_snapshot,
                        "event": {"entity": entity_snapshot}, **entity_snapshot}
            contexts = [base_ctx]
            for rel in relations:
                if not rel.get("_activa"):
                    continue
                rel_data = {k: v for k, v in rel.items() if not k.startswith("_")}
                contexts.append({**base_ctx,
                                 "relation": {rel["tipo"]: rel_data, **rel_data}})
            for ctx in contexts:
                try:
                    if evaluate(condition, ctx):
                        detalle = ""
                        rel_ctx = ctx.get("relation")
                        if isinstance(rel_ctx, dict):
                            tipo = next(iter(rel_ctx), "")
                            detalle = f"relación {tipo}"
                        alerts.append({
                            "rule": rule.name,
                            "severidad": "warning",
                            "mensaje": f"Regla '{rule.name}' activa"
                                       + (f" ({detalle})" if detalle else ""),
                        })
                        break
                except Exception as exc:
                    # la alerta no se pudo evaluar: sin log, la 360 diría "todo bien"
                    # cuando en realidad no sabemos.
                    log.warning("alert_not_evaluable", rule=rule.name, error=str(exc))
                    continue
        return alerts
