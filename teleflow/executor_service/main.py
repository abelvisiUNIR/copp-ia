"""executor-service :8002 — DAG engine async · durable sleep · signals.

Endpoints:
  POST /execute                          — dispara un proceso (async)
  GET  /instances/{id}                   — estado de la instancia
  GET  /instances                        — listado con filtros
  POST /instances/{id}/signal            — señal a human_task
  POST /instances/{id}/retry             — reintenta instancia FAILED
  POST /entities/{type} · /relations/... — gestión de dominio
  GET  /entities/{type}/{id}/360         — vista 360
"""
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.common.config import get_settings
from teleflow.common.db import db_ping, dispose_db, get_session, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.models import InstanceTransition, ProcessInstance
from teleflow.common.observability import setup_observability
from teleflow.dsl.parser import get_parser
from teleflow.executor_service.business_metrics import BusinessMetricsCollector
from teleflow.executor_service.domain import DomainLoader
from teleflow.executor_service.engine import ExecutionEngine
from teleflow.executor_service.entities import DomainError, EntityService
from teleflow.executor_service.events import EventBus
from teleflow.executor_service.rules import RuleEngine
from teleflow.executor_service.view360 import View360Service

log = setup_logging("executor-service")

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    sessionmaker = init_db(settings)
    domain_loader = DomainLoader(sessionmaker, get_parser(),
                                 ttl_seconds=settings.domain_cache_ttl)
    event_bus = EventBus(settings.rabbitmq_url, settings.events_exchange,
                         max_attempts=settings.event_max_attempts,
                         retry_base_delay=settings.event_retry_base_delay)
    entity_service = EntityService(sessionmaker, domain_loader, event_bus)
    engine = ExecutionEngine(sessionmaker, domain_loader, event_bus,
                             entity_service, settings)
    rule_engine = RuleEngine(sessionmaker, domain_loader, event_bus, engine, settings)
    view360 = View360Service(sessionmaker, domain_loader)
    business_metrics = BusinessMetricsCollector(sessionmaker, settings)

    try:
        await event_bus.connect()
    except Exception as exc:
        log.warning("rabbitmq_unavailable_at_startup", error=str(exc))
    await engine.start()
    await rule_engine.start()
    # Primer refresh en el arranque: sin esto el backlog recién aparece en /metrics tras el
    # primer intervalo, y un executor que reinicia mostraría cero trabajo pendiente mientras
    # tanto. Si la DB no está lista todavía, el loop lo reintenta solo.
    try:
        await business_metrics.refresh()
    except Exception as exc:
        log.warning("business_metrics_initial_refresh_failed", error=str(exc))
    await business_metrics.start()

    state.update(engine=engine, rule_engine=rule_engine, entities=entity_service,
                 view360=view360, bus=event_bus, domain=domain_loader,
                 business_metrics=business_metrics)
    log.info("executor_started", worker_concurrency=settings.worker_concurrency)
    yield
    await business_metrics.stop()
    await rule_engine.stop()
    await engine.stop()
    await event_bus.close()
    await dispose_db()


app = FastAPI(title="TeleFlow executor-service", version="1.0.0", lifespan=lifespan)
setup_observability(app, "executor-service", ready_check=db_ping)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# ------------------------------------------------------------------ ejecución


class ExecuteRequest(BaseModel):
    flow_name: str
    version: str = "latest"
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    # Alternativa al header `Idempotency-Key`, para quien llame al executor directo.
    idempotency_key: str | None = None


@app.post("/execute", status_code=202)
async def execute(
    req: ExecuteRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Dispara un proceso. Con `Idempotency-Key`, reintentar no crea una instancia nueva.

    El header manda sobre el campo del cuerpo: es la convención que los clientes conocen.
    """
    engine: ExecutionEngine = state["engine"]
    return await engine.trigger(req.flow_name, req.version, req.payload,
                                req.correlation_id,
                                idempotency_key or req.idempotency_key)


@app.post("/internal/execute", status_code=202, include_in_schema=False)
async def internal_execute(req: ExecuteRequest) -> dict[str, Any]:
    return await execute(req, idempotency_key=None)


@app.get("/instances")
async def list_instances(
    flow_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(ProcessInstance).order_by(ProcessInstance.created_at.desc())
    if flow_name:
        query = query.where(ProcessInstance.flow_name == flow_name)
    if status:
        query = query.where(ProcessInstance.status == status)
    rows = (await session.execute(query.limit(min(limit, 500)))).scalars().all()
    return [_instance_out(r) for r in rows]


@app.get("/instances/{instance_id}")
async def get_instance(
    instance_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    row = await session.get(ProcessInstance, instance_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Instancia no encontrada")
    transitions = (await session.execute(
        select(InstanceTransition).where(
            InstanceTransition.instance_id == instance_id
        ).order_by(InstanceTransition.occurred_at)
    )).scalars().all()
    out = _instance_out(row)
    out["context"] = row.context
    out["transitions"] = [{
        "from": t.from_status, "to": t.to_status, "step_name": t.step_name,
        "actor_id": t.actor_id, "occurred_at": t.occurred_at.isoformat(),
    } for t in transitions]
    return out


def _instance_out(row: ProcessInstance) -> dict[str, Any]:
    return {
        "instance_id": str(row.id),
        "flow_name": row.flow_name,
        "flow_version": row.flow_version,
        "correlation_id": row.correlation_id,
        "status": row.status,
        "current_step": row.current_step,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class SignalRequest(BaseModel):
    step_name: str
    signal: str
    actor_id: str | None = None
    signal_data: dict[str, Any] = Field(default_factory=dict)
    signal_id: str | None = None


@app.post("/instances/{instance_id}/signal")
async def signal_instance(instance_id: uuid.UUID, req: SignalRequest) -> dict[str, Any]:
    engine: ExecutionEngine = state["engine"]
    return await engine.signal(instance_id, req.step_name, req.signal,
                               req.actor_id, req.signal_data, req.signal_id)


@app.post("/instances/{instance_id}/retry")
async def retry_instance(instance_id: uuid.UUID) -> dict[str, Any]:
    engine: ExecutionEngine = state["engine"]
    return await engine.retry(instance_id)


# ------------------------------------------------------------------- entities


class CreateEntityRequest(BaseModel):
    entity_id: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class TransitionRequest(BaseModel):
    via: str
    actor_id: str | None = None


class PatchFieldsRequest(BaseModel):
    fields: dict[str, Any]


@app.post("/entities/{entity_type}", status_code=201)
async def create_entity(entity_type: str, req: CreateEntityRequest) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    return await svc.create_entity(entity_type, req.fields, req.entity_id)


@app.get("/entities/{entity_type}/{entity_id}")
async def get_entity(entity_type: str, entity_id: str) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    row = await svc.get_entity(entity_type, entity_id)
    return {"entity_type": row.entity_type, "entity_id": row.entity_id,
            "estado": row.estado, "campos": row.campos,
            "updated_at": row.updated_at.isoformat()}


@app.post("/entities/{entity_type}/{entity_id}/transition")
async def transition_entity(entity_type: str, entity_id: str,
                            req: TransitionRequest) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    return await svc.transition_entity(entity_type, entity_id, req.via, req.actor_id)


@app.patch("/entities/{entity_type}/{entity_id}")
async def patch_entity(entity_type: str, entity_id: str,
                       req: PatchFieldsRequest) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    return await svc.update_entity_fields(entity_type, entity_id, req.fields)


@app.get("/entities/{entity_type}/{entity_id}/360")
async def entity_360(entity_type: str, entity_id: str) -> dict[str, Any]:
    view: View360Service = state["view360"]
    return await view.build(entity_type, entity_id)


# ------------------------------------------------------------------ relations


class CreateRelationRequest(BaseModel):
    from_id: str
    to_id: str
    fields: dict[str, Any] = Field(default_factory=dict)


@app.post("/relations/{relation_type}", status_code=201)
async def create_relation(relation_type: str,
                          req: CreateRelationRequest) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    return await svc.create_relation(relation_type, req.from_id, req.to_id, req.fields)


@app.get("/relations/{relation_type}/{relation_id}")
async def get_relation(relation_type: str, relation_id: str) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    row = await svc.get_relation(relation_type, relation_id)
    return {"relation_type": row.relation_type, "relation_id": str(row.id),
            "from_id": row.from_id, "to_id": row.to_id, "estado": row.estado,
            "campos": row.campos, "updated_at": row.updated_at.isoformat()}


@app.post("/relations/{relation_type}/{relation_id}/transition")
async def transition_relation(relation_type: str, relation_id: str,
                              req: TransitionRequest) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    return await svc.transition_relation(relation_type, relation_id, req.via,
                                         req.actor_id)


@app.patch("/relations/{relation_type}/{relation_id}")
async def patch_relation(relation_type: str, relation_id: str,
                         req: PatchFieldsRequest) -> dict[str, Any]:
    svc: EntityService = state["entities"]
    return await svc.update_relation_fields(relation_type, relation_id, req.fields)
