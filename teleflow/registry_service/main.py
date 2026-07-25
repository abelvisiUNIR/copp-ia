"""registry-service :8003 — versionado inmutable de flows.

Una versión registrada nunca cambia. `latest` es un pointer mutable
en flow_latest que avanza al registrar una versión mayor (semver).
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.common.config import get_settings
from teleflow.common.db import db_ping, dispose_db, get_session, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.models import FlowDefinition, FlowLatest
from teleflow.common.observability import setup_observability

log = setup_logging("registry-service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db(get_settings())
    yield
    await dispose_db()


app = FastAPI(title="TeleFlow registry-service", version="1.0.0", lifespan=lifespan)
setup_observability(app, "registry-service", ready_check=db_ping)


class RegisterRequest(BaseModel):
    source: str
    version: str
    description: str = ""
    ast: dict[str, Any] = Field(default_factory=dict)
    checksum: str = ""


class FlowOut(BaseModel):
    flow_id: str
    name: str
    version: str
    status: str
    created_at: datetime | None = None


def _semver_key(version: str) -> tuple[tuple[int, ...], int, str]:
    """Orden de versiones. Un **prerelease va antes** que su release, no después.

    La versión anterior quitaba los no-dígitos de cada chunk, así que `1.0.0-rc1` daba
    `(1, 0, 1)` — **mayor** que `1.0.0`— y `1.0.0-beta` daba `(1, 0, 0)`, que con el `>=` de
    `register_flow` también avanzaba el pointer. En los dos casos `latest` terminaba
    apuntando a un candidato, y el executor disparaba procesos con él.

    Devuelve `(números, 1 si es release / 0 si es prerelease, etiqueta)`. La etiqueta ordena
    entre prereleases del mismo release (`alpha` < `beta` < `rc`, por orden alfabético, que es
    lo que manda semver para identificadores no numéricos).
    """
    nucleo, _, prerelease = version.partition("-")
    numeros = []
    for chunk in nucleo.split("."):
        digitos = "".join(ch for ch in chunk if ch.isdigit())
        numeros.append(int(digitos) if digitos else 0)
    # 1 = release, 0 = prerelease: a igualdad de números, el release gana.
    return (tuple(numeros), 0 if prerelease else 1, prerelease)


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
    elif _semver_key(req.version) > _semver_key(latest.version):
        # `>` y no `>=`: a igualdad de orden, el pointer se queda donde está. Con `>=`, un
        # `1.0.0-beta` registrado después de `1.0.0` movía `latest` a la beta.
        latest.version = req.version

    try:
        await session.commit()
    except IntegrityError:
        # El chequeo de arriba lee antes de insertar: entre el SELECT y el INSERT hay una
        # ventana donde dos registros concurrentes de la misma versión pasan los dos. La
        # garantía la sostiene el UniqueConstraint(name, version) — como debe ser — pero sin
        # esto el segundo cliente recibía un 500 donde el caso secuencial da 409.
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"La versión {req.version} de '{name}' ya existe y es inmutable",
        )
    log.info("flow_registered", flow_name=name, version=req.version)
    return FlowOut(
        flow_id=str(definition.id), name=name, version=req.version, status="registered"
    )


@app.get("/flows")
async def list_flows(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(FlowLatest))).scalars().all()
    return [
        {"name": r.name, "latest": r.version, "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]


@app.get("/flows/{name}")
async def list_versions(
    name: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
