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
from datetime import datetime, timezone
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
from teleflow.composer_service.providers import (
    LLMConfigurationError,
    LLMRequestRejected,
    LLMTransientError,
    get_provider,
)

log = setup_logging("composer-service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Se construye acá a propósito: si `LLM_PROVIDER` no se puede satisfacer, el servicio no
    # arranca. Descubrirlo por request significa descubrirlo cuando alguien ya escribió el
    # pedido, y antes significaba no descubrirlo nunca (caía al stub en silencio).
    provider = get_provider(settings)
    log.info("llm_provider_ready", provider=provider.name)
    init_db(settings)
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
    # Tres finales distintos, tres códigos distintos: antes todo era 502, así que un prompt
    # rechazado y un proveedor caído se veían igual desde el cliente.
    try:
        source = await provider.generate(prompt)
    except LLMRequestRejected as exc:
        log.warning("llm_request_rejected", provider=provider.name, error=str(exc))
        raise HTTPException(status_code=422, detail=f"El proveedor rechazó el pedido: {exc}")
    except LLMConfigurationError as exc:
        # Nuestra instalación está mal (credencial, modelo, max_tokens): no es culpa de quien
        # pidió el borrador, y reintentar no lo arregla.
        log.error("llm_misconfigured", provider=provider.name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Composer mal configurado: {exc}")
    except LLMTransientError as exc:
        log.error("llm_unavailable", provider=provider.name, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Proveedor LLM no disponible: {exc}")

    # limpiar fences de markdown si el modelo los agregó
    source = source.strip()
    if source.startswith("```"):
        lines = source.splitlines()
        source = "\n".join(l for l in lines if not l.strip().startswith("```"))

    # Se valida antes de guardar, pero **no** condiciona el guardado: un borrador que no
    # compila suele estar a dos líneas de hacerlo, y la generación ya se pagó. Lo que no
    # puede pasar es que llegue a un revisor humano sin que nadie sepa que no compila —
    # antes eso se descubría recién en el deploy, después de la revisión.
    validation = await _validate_source(source, req.name)

    draft = FlowDraft(name=req.name, description=req.description,
                      source=source, base_source=req.base_source,
                      provider=provider.name, validation=validation)
    session.add(draft)
    await session.commit()
    # `provider.name` (lo que corrió), no `settings.llm_provider` (lo que se pidió).
    log.info("draft_created", flow_name=req.name, draft_id=str(draft.id),
             provider=provider.name, parses=validation["parses"])
    return _draft_out(draft)


async def _validate_source(source: str, name: str) -> dict[str, Any]:
    """Pasa el borrador por el `parser-service`. Nunca levanta por culpa del parser.

    `parses: None` significa **no se pudo verificar**, y es un estado distinto de "compila".
    Si el parser está caído, la generación no se bloquea, pero la degradación queda escrita
    en el borrador: dar por bueno lo que no se verificó sería el mismo problema que este
    cambio arregla, un nivel más abajo.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{get_settings().parser_url}/parse",
                json={"source": source, "name": name},
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Solo transporte y respuesta ilegible: un bug nuestro no puede disfrazarse de
        # "parser caído", así que cualquier otra excepción sigue de largo.
        log.error("draft_validation_unavailable", flow_name=name, error=str(exc))
        return {"parses": None, "issues": [], "error": str(exc), "checked_at": checked_at}

    return {
        "parses": bool(data.get("valid")),
        "issues": data.get("issues", []),
        "checked_at": checked_at,
    }


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
        # Van también en el listado (`include_source=False`): son justamente lo que decide
        # si vale la pena abrir un borrador.
        "provider": draft.provider,
        "validation": draft.validation,
    }
    if include_source:
        out["source"] = draft.source
        out["base_source"] = draft.base_source
    return out
