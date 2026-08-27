"""Gestión de entities y relations: estado, ciclo de vida, invariantes, eventos.

Cada transición valida la máquina de estados declarada en el .tflow,
emite los eventos de dominio declarados (a RabbitMQ y a entity_events)
y dispara la evaluación de reglas.
"""
from __future__ import annotations

import uuid
from typing import Any

from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from teleflow.common.logging import get_logger
from teleflow.common.models import EntityEvent, EntityState, RelationState
from teleflow.dsl.ast_nodes import (
    EntityDef,
    FieldDef,
    Lifecycle,
    RelationDef,
    TransitionDef,
)
from teleflow.dsl.evaluator import evaluate
from teleflow.executor_service.domain import DomainLoader
from teleflow.executor_service.events import EventBus

log = get_logger(component="entities")

# Un invariante salteado es una regla de negocio que NO se está aplicando: visible.
INVARIANTS_SKIPPED = Counter(
    "teleflow_invariants_skipped_total",
    "Invariantes no aplicados, por motivo",
    ["entity", "reason"],  # unparseable | not_evaluable
)


class DomainError(Exception):
    """Error de negocio: 404/409/422 según situación."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _validate_fields(defs: list[FieldDef], data: dict[str, Any],
                     partial: bool = False) -> dict[str, Any]:
    by_name = {f.name: f for f in defs}
    unknown = set(data) - set(by_name)
    if unknown:
        raise DomainError(f"Campos desconocidos: {sorted(unknown)}")
    result: dict[str, Any] = {}
    for fdef in defs:
        if fdef.name not in data:
            if not partial and fdef.required:
                raise DomainError(f"Campo requerido faltante: {fdef.name}")
            if not partial and fdef.has_default:
                result[fdef.name] = fdef.default
            continue
        value = data[fdef.name]
        if value is None:
            result[fdef.name] = None
            continue
        if fdef.type == "enum" and fdef.enum_values and value not in fdef.enum_values:
            raise DomainError(
                f"Campo '{fdef.name}': '{value}' no está en {fdef.enum_values}")
        if fdef.type == "number":
            if not isinstance(value, (int, float)):
                raise DomainError(f"Campo '{fdef.name}': se esperaba number")
            if fdef.range and not (fdef.range[0] <= value <= fdef.range[1]):
                raise DomainError(
                    f"Campo '{fdef.name}': {value} fuera de rango {fdef.range}")
        result[fdef.name] = value
    return result


def _find_transition(lc: Lifecycle | None, current: str, via: str) -> TransitionDef:
    if lc is None:
        raise DomainError("El tipo no declara lifecycle", 409)
    for t in lc.transitions:
        if t.via == via and t.from_state == current:
            return t
    valid = [t.via for t in lc.transitions if t.from_state == current]
    raise DomainError(
        f"Transición '{via}' inválida desde estado '{current}'. Válidas: {valid}", 409)


def _eval_ctx(campos: dict[str, Any], estado: str) -> dict[str, Any]:
    ctx = {**campos, "estado": estado}
    # Campo derivado: edad desde fecha_nac (invariantes tipo "edad >= 5")
    if "fecha_nac" in campos and campos.get("fecha_nac"):
        from teleflow.dsl.evaluator import _years_since

        years = _years_since(campos["fecha_nac"])
        if years is not None:
            ctx["edad"] = int(years)
    return ctx


class EntityService:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession],
                 domain_loader: DomainLoader, event_bus: EventBus):
        self._sessionmaker = sessionmaker
        self._domain = domain_loader
        self._bus = event_bus

    # ------------------------------------------------------------ entities

    async def _entity_def(self, entity_type: str) -> EntityDef:
        domain = await self._domain.load()
        entity_def = domain.merged.entities.get(entity_type)
        if entity_def is None:
            raise DomainError(f"entity '{entity_type}' no definida en el dominio", 404)
        return entity_def

    async def create_entity(self, entity_type: str, fields: dict[str, Any],
                            entity_id: str | None = None) -> dict[str, Any]:
        entity_def = await self._entity_def(entity_type)
        campos = _validate_fields(entity_def.fields, fields)
        self._check_invariants(entity_def, campos,
                               entity_def.lifecycle.initial if entity_def.lifecycle else "")
        initial = entity_def.lifecycle.initial if entity_def.lifecycle else "CREATED"
        eid = entity_id or str(uuid.uuid4())

        async with self._sessionmaker() as session:
            for fdef in entity_def.fields:
                if fdef.unique and campos.get(fdef.name) is not None:
                    dup = await session.scalar(
                        select(EntityState).where(
                            EntityState.entity_type == entity_type,
                            EntityState.campos[fdef.name].as_string()
                            == str(campos[fdef.name]),
                        )
                    )
                    if dup is not None:
                        raise DomainError(
                            f"Ya existe {entity_type} con {fdef.name}="
                            f"{campos[fdef.name]}", 409)
            row = EntityState(entity_type=entity_type, entity_id=eid,
                              estado=initial, campos=campos)
            session.add(row)
            event_name = f"{entity_type}.{initial.lower()}"
            session.add(EntityEvent(entity_type=entity_type, entity_id=eid,
                                    event_name=event_name,
                                    payload={"entity_id": eid, **campos}))
            await session.commit()

        await self._bus.publish(event_name, {
            "event": event_name, "subject": entity_type, "subject_kind": "entity",
            "entity_id": eid, "state": initial, "payload": campos,
        })
        log.info("entity_created", entity_type=entity_type, entity_id=eid, estado=initial)
        return {"entity_type": entity_type, "entity_id": eid,
                "estado": initial, "campos": campos}

    async def list_entities(self, entity_type: str, estado: str | None = None,
                            limit: int = 50) -> list[EntityState]:
        """Las entidades de un tipo, más recientes primero.

        Faltaba: se podía crear una entidad, buscarla por id y transicionarla, pero no
        preguntar "¿qué niños hay?". Sin esto, cualquier interfaz obliga a saberse los ids de
        memoria, que es justo lo que una interfaz viene a evitar.

        El tope duro de 500 no es paginación de verdad —no hay cursor— pero evita que una
        entidad con historia larga devuelva la tabla entera por descuido. Cuando haga falta
        paginar en serio, se agrega el cursor acá.
        """
        async with self._sessionmaker() as session:
            query = select(EntityState).where(EntityState.entity_type == entity_type)
            if estado:
                query = query.where(EntityState.estado == estado)
            query = query.order_by(EntityState.updated_at.desc()).limit(min(limit, 500))
            return list((await session.execute(query)).scalars().all())

    async def get_entity(self, entity_type: str, entity_id: str) -> EntityState:
        async with self._sessionmaker() as session:
            row = await session.scalar(
                select(EntityState).where(
                    EntityState.entity_type == entity_type,
                    EntityState.entity_id == entity_id,
                )
            )
        if row is None:
            raise DomainError(f"{entity_type}/{entity_id} no encontrado", 404)
        return row

    async def transition_entity(self, entity_type: str, entity_id: str, via: str,
                                actor_id: str | None = None) -> dict[str, Any]:
        entity_def = await self._entity_def(entity_type)
        async with self._sessionmaker() as session:
            row = await session.scalar(
                select(EntityState).where(
                    EntityState.entity_type == entity_type,
                    EntityState.entity_id == entity_id,
                ).with_for_update()
            )
            if row is None:
                raise DomainError(f"{entity_type}/{entity_id} no encontrado", 404)
            transition = _find_transition(entity_def.lifecycle, row.estado, via)
            self._check_invariants(entity_def, row.campos, transition.to_state)
            old_state = row.estado
            row.estado = transition.to_state

            emitted = [ev.emit for ev in entity_def.events
                       if ev.kind == "on_transition" and ev.trigger == via]
            payload = {"entity_id": entity_id, "from": old_state,
                       "to": transition.to_state, "via": via, "actor_id": actor_id,
                       **row.campos}
            for event_name in emitted:
                session.add(EntityEvent(entity_type=entity_type, entity_id=entity_id,
                                        event_name=event_name, payload=payload))
            await session.commit()

        for event_name in emitted or [f"{entity_type}.transitioned"]:
            await self._bus.publish(event_name, {
                "event": event_name, "subject": entity_type, "subject_kind": "entity",
                "entity_id": entity_id, "state": transition.to_state, "payload": payload,
            })
        log.info("entity_transitioned", entity_type=entity_type, entity_id=entity_id,
                 via=via, to_state=transition.to_state)
        return {"entity_type": entity_type, "entity_id": entity_id,
                "estado": transition.to_state, "via": via}

    async def update_entity_fields(self, entity_type: str, entity_id: str,
                                   patch: dict[str, Any]) -> dict[str, Any]:
        entity_def = await self._entity_def(entity_type)
        validated = _validate_fields(entity_def.fields, patch, partial=True)
        async with self._sessionmaker() as session:
            row = await session.scalar(
                select(EntityState).where(
                    EntityState.entity_type == entity_type,
                    EntityState.entity_id == entity_id,
                ).with_for_update()
            )
            if row is None:
                raise DomainError(f"{entity_type}/{entity_id} no encontrado", 404)
            changed = [k for k, v in validated.items() if row.campos.get(k) != v]
            row.campos = {**row.campos, **validated}
            flag_modified(row, "campos")
            self._check_invariants(entity_def, row.campos, row.estado)

            events = []
            for ev in entity_def.events:
                if ev.kind == "on_field_change" and ev.trigger in changed:
                    events.append(ev.emit)
                    session.add(EntityEvent(
                        entity_type=entity_type, entity_id=entity_id,
                        event_name=ev.emit,
                        payload={"entity_id": entity_id, "field": ev.trigger,
                                 "value": row.campos.get(ev.trigger)},
                    ))
            campos = dict(row.campos)
            estado = row.estado
            await session.commit()

        for event_name in events:
            await self._bus.publish(event_name, {
                "event": event_name, "subject": entity_type, "subject_kind": "entity",
                "entity_id": entity_id, "state": estado, "payload": campos,
            })
        return {"entity_type": entity_type, "entity_id": entity_id,
                "estado": estado, "campos": campos}

    def _check_invariants(self, entity_def: EntityDef, campos: dict[str, Any],
                          estado: str) -> None:
        from teleflow.dsl.parser import get_parser

        parser = get_parser()
        ctx = _eval_ctx(campos, estado)
        for inv in entity_def.invariants:
            try:
                expr = parser.parse_expr(inv)
            except Exception as exc:
                # el invariante NO PARSEA: está mal escrito y por lo tanto no se aplica
                # a nadie. No es un caso benigno: es una regla de negocio que no existe.
                log.error("invariant_unparseable", entity=entity_def.name,
                          invariant=inv, error=str(exc))
                INVARIANTS_SKIPPED.labels(entity_def.name, "unparseable").inc()
                continue
            try:
                ok = evaluate(expr, ctx)
            except Exception as exc:
                # no evaluable con ESTOS datos (p.ej. un campo optional vacío): benigno,
                # no bloquea la transición.
                log.debug("invariant_not_evaluable", entity=entity_def.name,
                          invariant=inv, error=str(exc))
                INVARIANTS_SKIPPED.labels(entity_def.name, "not_evaluable").inc()
                continue
            if not ok:
                raise DomainError(
                    f"Invariante violado en {entity_def.name}: \"{inv}\"", 422)

    # ----------------------------------------------------------- relations

    async def _relation_def(self, relation_type: str) -> RelationDef:
        domain = await self._domain.load()
        rel_def = domain.merged.relations.get(relation_type)
        if rel_def is None:
            raise DomainError(f"relation '{relation_type}' no definida", 404)
        return rel_def

    async def create_relation(self, relation_type: str, from_id: str, to_id: str,
                              fields: dict[str, Any]) -> dict[str, Any]:
        rel_def = await self._relation_def(relation_type)
        campos = _validate_fields(rel_def.fields, fields)
        initial = rel_def.lifecycle.initial if rel_def.lifecycle else "CREATED"

        # verificar que existan las entities de ambos lados
        if rel_def.from_ref is not None:
            await self.get_entity(rel_def.from_ref.target, from_id)
        if rel_def.to_ref is not None:
            await self.get_entity(rel_def.to_ref.target, to_id)

        async with self._sessionmaker() as session:
            row = RelationState(relation_type=relation_type, from_id=from_id,
                                to_id=to_id, estado=initial, campos=campos)
            session.add(row)
            await session.flush()
            rid = str(row.id)
            event_name = f"{relation_type}.{initial.lower()}"
            session.add(EntityEvent(
                entity_type=relation_type, entity_id=rid, event_name=event_name,
                payload={"relation_id": rid, "from_id": from_id, "to_id": to_id,
                         **campos}))
            await session.commit()

        message = {
            "event": event_name, "subject": relation_type, "subject_kind": "relation",
            "relation_id": rid, "from_id": from_id, "to_id": to_id,
            "state": initial, "payload": campos,
        }
        await self._bus.publish(event_name, message)
        # evento sintético de creación para reglas on_relation
        await self._bus.publish(f"relation.{relation_type}.created",
                                {**message, "event": f"relation.{relation_type}.created"})
        log.info("relation_created", relation_type=relation_type, relation_id=rid)
        return {"relation_type": relation_type, "relation_id": rid,
                "from_id": from_id, "to_id": to_id, "estado": initial, "campos": campos}

    async def get_relation(self, relation_type: str, relation_id: str) -> RelationState:
        async with self._sessionmaker() as session:
            row = await session.get(RelationState, uuid.UUID(relation_id))
        if row is None or row.relation_type != relation_type:
            raise DomainError(f"{relation_type}/{relation_id} no encontrada", 404)
        return row

    async def transition_relation(self, relation_type: str, relation_id: str, via: str,
                                  actor_id: str | None = None) -> dict[str, Any]:
        rel_def = await self._relation_def(relation_type)
        async with self._sessionmaker() as session:
            row = await session.get(RelationState, uuid.UUID(relation_id),
                                    with_for_update=True)
            if row is None or row.relation_type != relation_type:
                raise DomainError(f"{relation_type}/{relation_id} no encontrada", 404)
            transition = _find_transition(rel_def.lifecycle, row.estado, via)
            old_state = row.estado
            row.estado = transition.to_state
            emitted = [ev.emit for ev in rel_def.events
                       if ev.kind == "on_transition" and ev.trigger == via]
            payload = {"relation_id": relation_id, "from_id": row.from_id,
                       "to_id": row.to_id, "from": old_state,
                       "to": transition.to_state, "via": via, "actor_id": actor_id,
                       **row.campos}
            for event_name in emitted:
                session.add(EntityEvent(entity_type=relation_type,
                                        entity_id=relation_id,
                                        event_name=event_name, payload=payload))
            from_id, to_id = row.from_id, row.to_id
            await session.commit()

        for event_name in emitted or [f"{relation_type}.transitioned"]:
            await self._bus.publish(event_name, {
                "event": event_name, "subject": relation_type,
                "subject_kind": "relation", "relation_id": relation_id,
                "from_id": from_id, "to_id": to_id,
                "state": transition.to_state, "payload": payload,
            })
        return {"relation_type": relation_type, "relation_id": relation_id,
                "estado": transition.to_state, "via": via}

    async def update_relation_fields(self, relation_type: str, relation_id: str,
                                     patch: dict[str, Any]) -> dict[str, Any]:
        rel_def = await self._relation_def(relation_type)
        validated = _validate_fields(rel_def.fields, patch, partial=True)
        async with self._sessionmaker() as session:
            row = await session.get(RelationState, uuid.UUID(relation_id),
                                    with_for_update=True)
            if row is None or row.relation_type != relation_type:
                raise DomainError(f"{relation_type}/{relation_id} no encontrada", 404)
            changed = [k for k, v in validated.items() if row.campos.get(k) != v]
            row.campos = {**row.campos, **validated}
            flag_modified(row, "campos")
            events = []
            for ev in rel_def.events:
                if ev.kind == "on_field_change" and ev.trigger in changed:
                    events.append(ev.emit)
                    session.add(EntityEvent(
                        entity_type=relation_type, entity_id=relation_id,
                        event_name=ev.emit,
                        payload={"relation_id": relation_id, "field": ev.trigger,
                                 "value": row.campos.get(ev.trigger),
                                 "from_id": row.from_id, "to_id": row.to_id}))
            campos = dict(row.campos)
            estado = row.estado
            from_id, to_id = row.from_id, row.to_id
            await session.commit()

        for event_name in events:
            await self._bus.publish(event_name, {
                "event": event_name, "subject": relation_type,
                "subject_kind": "relation", "relation_id": relation_id,
                "from_id": from_id, "to_id": to_id, "state": estado,
                "payload": campos,
            })
        return {"relation_type": relation_type, "relation_id": relation_id,
                "estado": estado, "campos": campos}
