"""registry-service :8003 — versionado inmutable de flows.

Una versión registrada nunca cambia. `latest` es un pointer mutable
en flow_latest que avanza al registrar una versión mayor (semver).
"""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.common.config import get_settings
from teleflow.common.db import db_ping, dispose_db, get_session, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.models import FlowDefinition, FlowLatest
from teleflow.common.observability import setup_observability

log = setup_logging("registry-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(get_settings())
    yield
    await dispose_db()


app = FastAPI(title="TeleFlow registry-service", version="1.0.0", lifespan=lifespan)
setup_observability(app, "registry-service", ready_check=db_ping)


class RegisterRequest(BaseModel):
    source: str
    version: str
    description: str = ""
    ast: dict = Field(default_factory=dict)
    checksum: str = ""


class FlowOut(BaseModel):
    flow_id: str
    name: str
    version: str
    status: str
    created_at: datetime | None = None


def _semver_key(version: str) -> tuple:
    parts = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


@app.post("/flows/{name}", response_model=FlowOut, status_code=201)
async def register_flow(
    name: str, req: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> FlowOut:
    existing = await session.scalar(
        select(FlowDefinition).where(
            FlowDefinition.name == name, FlowDefinition.version == req.version
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"La versión {req.version} de '{name}' ya existe y es inmutable",
        )

    definition = FlowDefinition(
        name=name,
        version=req.version,
        source=req.source,
        ast=req.ast,
        checksum=req.checksum,
        status="registered",
    )
    session.add(definition)

    latest = await session.get(FlowLatest, name)
    if latest is None:
        session.add(FlowLatest(name=name, version=req.version))
    elif _semver_key(req.version) >= _semver_key(latest.version):
        latest.version = req.version

    await session.commit()
    log.info("flow_registered", flow_name=name, version=req.version)
    return FlowOut(
        flow_id=str(definition.id), name=name, version=req.version, status="registered"
    )


@app.get("/flows")
async def list_flows(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(FlowLatest))).scalars().all()
    return [
        {"name": r.name, "latest": r.version, "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]


@app.get("/flows/{name}")
async def list_versions(
    name: str, session: AsyncSession = Depends(get_session)
) -> dict:
    rows = (
        (await session.execute(
            select(FlowDefinition).where(FlowDefinition.name == name)
        )).scalars().all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' no encontrado")
    latest = await session.get(FlowLatest, name)
    return {
        "name": name,
        "latest": latest.version if latest else None,
        "versions": sorted(
            ({"version": r.version, "status": r.status, "checksum": r.checksum,
              "created_at": r.created_at.isoformat()} for r in rows),
            key=lambda v: _semver_key(v["version"]),
            reverse=True,
        ),
    }


@app.get("/flows/{name}/{version}")
async def get_flow(
    name: str, version: str, session: AsyncSession = Depends(get_session)
) -> dict:
    if version == "latest":
        latest = await session.get(FlowLatest, name)
        if latest is None:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' no encontrado")
        version = latest.version
    row = await session.scalar(
        select(FlowDefinition).where(
            FlowDefinition.name == name, FlowDefinition.version == version
        )
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Flow '{name}' versión '{version}' no encontrado"
        )
    return {
        "flow_id": str(row.id),
        "name": row.name,
        "version": row.version,
        "source": row.source,
        "ast": row.ast,
        "checksum": row.checksum,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }
