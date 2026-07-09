"""composer-service :8004 — genera borradores .tflow desde lenguaje natural.

Flujo PR-style:
  POST /compose            — analista describe el proceso → borrador (pending)
  GET  /drafts             — lista para la review-ui
  GET  /drafts/{id}        — detalle con diff base
  POST /drafts/{id}/approve — el dev aprueba → deploy vía gateway
  POST /drafts/{id}/reject  — rechaza con comentario
"""
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.common.config import get_settings
from teleflow.common.db import db_ping, dispose_db, get_session, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.models import FlowDraft
from teleflow.common.observability import setup_observability
from teleflow.composer_service.providers import get_provider

log = setup_logging("composer-service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db(get_settings())
    yield
    await dispose_db()


app = FastAPI(title="TeleFlow composer-service", version="1.0.0", lifespan=lifespan)
setup_observability(app, "composer-service", ready_check=db_ping)


class ComposeRequest(BaseModel):
    name: str
    description: str
    base_source: str | None = None


@app.post("/compose", status_code=201)
async def compose(req: ComposeRequest,
                  session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    provider = get_provider(settings)
    prompt = req.description
    if req.base_source:
        prompt += ("\n\nVersión actual del flow (modificala según el pedido):\n"
                   + req.base_source)
    try:
        source = await provider.generate(prompt)
    except Exception as exc:
        log.error("llm_generation_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Error del proveedor LLM: {exc}")

    # limpiar fences de markdown si el modelo los agregó
    source = source.strip()
    if source.startswith("```"):
        lines = source.splitlines()
        source = "\n".join(l for l in lines if not l.strip().startswith("```"))

    draft = FlowDraft(name=req.name, description=req.description,
                      source=source, base_source=req.base_source)
    session.add(draft)
    await session.commit()
    log.info("draft_created", flow_name=req.name, draft_id=str(draft.id),
             provider=settings.llm_provider)
    return _draft_out(draft)


@app.get("/drafts")
async def list_drafts(status: str | None = None,
                      session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    query = select(FlowDraft).order_by(FlowDraft.created_at.desc())
    if status:
        query = query.where(FlowDraft.status == status)
    rows = (await session.execute(query.limit(100))).scalars().all()
    return [_draft_out(r, include_source=False) for r in rows]


@app.get("/drafts/{draft_id}")
async def get_draft(draft_id: uuid.UUID,
                    session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    draft = await session.get(FlowDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    return _draft_out(draft)


class ApproveRequest(BaseModel):
    version: str
    actor_id: str = ""
    comment: str = ""


@app.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: uuid.UUID, req: ApproveRequest,
                        session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    draft = await session.get(FlowDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    if draft.status != "pending":
        raise HTTPException(status_code=409, detail=f"Borrador ya {draft.status}")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.gateway_url}/flows/{draft.name}",
            headers={"X-TeleFlow-API-Key": settings.teleflow_api_key},
            json={"source": draft.source, "version": req.version,
                  "description": f"Aprobado desde draft {draft_id}"},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=422,
            detail={"message": "El deploy falló — el borrador sigue pending",
                    "upstream": response.json()},
        )

    draft.status = "approved"
    draft.comments = list(draft.comments) + [{
        "actor": req.actor_id, "action": "approve", "comment": req.comment,
        "version": req.version,
    }]
    await session.commit()
    log.info("draft_approved", draft_id=str(draft_id), flow_name=draft.name,
             version=req.version, actor_id=req.actor_id)
    return {**_draft_out(draft), "deploy": response.json()}


class RejectRequest(BaseModel):
    actor_id: str = ""
    comment: str = ""


@app.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: uuid.UUID, req: RejectRequest,
                       session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    draft = await session.get(FlowDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    if draft.status != "pending":
        raise HTTPException(status_code=409, detail=f"Borrador ya {draft.status}")
    draft.status = "rejected"
    draft.comments = list(draft.comments) + [{
        "actor": req.actor_id, "action": "reject", "comment": req.comment,
    }]
    await session.commit()
    log.info("draft_rejected", draft_id=str(draft_id), actor_id=req.actor_id)
    return _draft_out(draft)


def _draft_out(draft: FlowDraft, include_source: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "draft_id": str(draft.id),
        "name": draft.name,
        "description": draft.description,
        "status": draft.status,
        "comments": draft.comments,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }
    if include_source:
        out["source"] = draft.source
        out["base_source"] = draft.base_source
    return out
