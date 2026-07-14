"""api-gateway :8000 — único punto de entrada externo.

Auth (X-TeleFlow-API-Key) · rate limiting (token bucket por API key) ·
routing hacia los servicios core. Los clientes solo conocen este endpoint.

Deploy de un flow: POST /flows/{name}
  gateway → parser-service (valida) → registry-service (persiste)
"""
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from teleflow.common.config import Settings, get_settings
from teleflow.common.db import get_sessionmaker, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.models import ApiKey
from teleflow.common.observability import setup_observability
from teleflow.gateway import auth

log = setup_logging("api-gateway")

PUBLIC_PATHS = {"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"}

client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global client
    client = httpx.AsyncClient(timeout=60.0)
    init_db(get_settings())   # las API keys viven en Postgres (tabla api_keys)
    yield
    await client.aclose()


# Declara el esquema de auth en OpenAPI para que Swagger muestre "Authorize" y
# envíe el header. auto_error=False: la validación real la hace el middleware.
api_key_scheme = APIKeyHeader(name="X-TeleFlow-API-Key", auto_error=False)

app = FastAPI(title="TeleFlow API Gateway", version="1.0.0", lifespan=lifespan,
              dependencies=[Depends(api_key_scheme)])
setup_observability(app, "api-gateway")


# ------------------------------------------------------------ rate limiting

class TokenBucket:
    def __init__(self, rate_per_minute: int):
        self.capacity = float(rate_per_minute)
        self.tokens = float(rate_per_minute)
        self.rate = rate_per_minute / 60.0
        self.updated = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_buckets: dict[str, TokenBucket] = {}


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Autentica (¿quién es esta key?) y limita. La **autorización** por scope la hace cada
    ruta con `Depends(require(...))`: el permiso depende del endpoint, no de la key sola."""
    if request.url.path in PUBLIC_PATHS or request.method == "OPTIONS":
        return await call_next(request)
    settings = get_settings()
    api_key = request.headers.get("X-TeleFlow-API-Key", "")

    identidad = await resolver_identidad(api_key, settings)
    if identidad is None:
        return JSONResponse(status_code=401, content={"detail": "API key inválida"})

    bucket = _buckets.setdefault(api_key, TokenBucket(settings.rate_limit_rpm))
    if not bucket.allow():
        return JSONResponse(status_code=429,
                            content={"detail": "Rate limit excedido"})

    request.state.identidad = identidad
    return await call_next(request)


# ------------------------------------------------------ resolución de la key

# hash de la key -> (identidad, vence_en). Evita ir a la DB en cada request; el TTL es
# también la ventana máxima que sobrevive una key revocada (ver Chunk 3).
_cache_keys: dict[str, tuple[auth.Identidad, float]] = {}


@lru_cache
def get_bootstrap_scopes() -> frozenset[str]:
    """Scopes de la key global de env. Un scope mal escrito revienta acá, explícito."""
    return auth.parse_scopes(get_settings().teleflow_api_key_scopes)


async def resolver_identidad(api_key: str, settings: Settings) -> auth.Identidad | None:
    """Key de env (bootstrap) o key de la DB. `None` = inválida, revocada o inexistente.

    La de bootstrap se resuelve **sin tocar la DB**: si Postgres está caído o la migración
    no corrió, el operador no queda afuera de su propia plataforma.
    """
    if not api_key:
        return None
    if secrets.compare_digest(api_key, settings.teleflow_api_key):
        return auth.Identidad(name=auth.BOOTSTRAP_KEY_NAME,
                              scopes=get_bootstrap_scopes())

    hashed = auth.hash_key(api_key)
    cacheada = _cache_keys.get(hashed)
    if cacheada is not None and cacheada[1] > time.monotonic():
        return cacheada[0]

    try:
        async with get_sessionmaker()() as session:
            identidad = await auth.resolver_key(session, api_key)
            if identidad is not None:
                await session.execute(
                    update(ApiKey).where(ApiKey.id == identidad.key_id)
                    .values(last_used_at=func.now()))
                await session.commit()
    except (SQLAlchemyError, OSError) as exc:
        # la DB no responde (OSError = conexión rechazada, no la envuelve SQLAlchemy):
        # no se puede afirmar que la key sea válida -> 401, nunca un 500 con stack.
        # La key de bootstrap sigue andando: el operador no queda afuera.
        log.error("api_key_lookup_failed", error=str(exc))
        return None

    if identidad is None:
        _cache_keys.pop(hashed, None)
        return None
    _cache_keys[hashed] = (identidad,
                           time.monotonic() + settings.api_key_cache_ttl)
    return identidad


# ----------------------------------------------------------------- helpers

class UpstreamDown(Exception):
    """Un servicio core no respondió: se traduce a 502, nunca a un 500 con stack."""

    def __init__(self, base_url: str, exc: Exception):
        self.base_url = base_url
        super().__init__(str(exc))


def _bad_gateway(base_url: str) -> JSONResponse:
    return JSONResponse(status_code=502,
                        content={"detail": f"Servicio no disponible: {base_url}"})


async def _post_upstream(base_url: str, path: str,
                         payload: dict[str, Any]) -> httpx.Response:
    """POST a un servicio core. `RequestError` (conexión, timeout, DNS) → UpstreamDown."""
    assert client is not None
    try:
        return await client.post(f"{base_url}{path}", json=payload)
    except httpx.RequestError as exc:
        raise UpstreamDown(base_url, exc) from exc


async def _proxy(request: Request, base_url: str, path: str) -> Response:
    assert client is not None
    body = await request.body()
    try:
        upstream = await client.request(
            request.method,
            f"{base_url}{path}",
            content=body if body else None,
            params=dict(request.query_params),
            headers={"Content-Type": "application/json"} if body else {},
        )
    except httpx.RequestError:  # conexión rechazada, timeout, DNS
        return _bad_gateway(base_url)
    return Response(content=upstream.content, status_code=upstream.status_code,
                    media_type=upstream.headers.get("content-type", "application/json"))


# --------------------------------------------------------- gestión de keys

class CrearKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)   # identidad, p.ej. "integracion-ceibal"
    scopes: list[str]


@app.post("/keys", status_code=201,
          dependencies=[Depends(auth.require(auth.KEYS_ADMIN))])
async def crear_key(req: CrearKeyRequest) -> Response:
    """Crea una key con permisos acotados. El secreto se devuelve **una sola vez**."""
    try:
        scopes = auth.parse_scopes(",".join(req.scopes))
    except auth.UnknownScopeError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    secreto = auth.generar_key()
    fila = ApiKey(name=req.name, key_hash=auth.hash_key(secreto),
                  scopes=sorted(scopes), active=True)
    try:
        async with get_sessionmaker()() as session:
            session.add(fila)
            await session.commit()
            key_id = fila.id
    except IntegrityError:
        return JSONResponse(status_code=409,
                            content={"detail": f"ya existe una key '{req.name}'"})

    log.info("api_key_created", key_name=req.name, scopes=sorted(scopes))
    return JSONResponse(status_code=201, content={
        "id": str(key_id),
        "name": req.name,
        "scopes": sorted(scopes),
        "key": secreto,   # única vez que se ve: solo se guarda el hash
        "aviso": "guardá esta key ahora: no se puede volver a mostrar",
    })


@app.get("/keys", dependencies=[Depends(auth.require(auth.KEYS_ADMIN))])
async def listar_keys() -> Response:
    """Lista las credenciales. Nunca devuelve secretos ni hashes."""
    async with get_sessionmaker()() as session:
        filas = (await session.execute(
            select(ApiKey).order_by(ApiKey.created_at))).scalars().all()
    return JSONResponse(content=[{
        "id": str(f.id),
        "name": f.name,
        "scopes": [str(s) for s in f.scopes],
        "active": f.active,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "last_used_at": f.last_used_at.isoformat() if f.last_used_at else None,
    } for f in filas])


# ------------------------------------------------------- deploy de flows

class DeployRequest(BaseModel):
    source: str
    version: str
    description: str = ""


@app.post("/flows/{name}", dependencies=[Depends(auth.require(auth.FLOWS_DEPLOY))])
async def deploy_flow(name: str, req: DeployRequest) -> Response:
    """Valida en parser-service y persiste en registry-service."""
    settings = get_settings()
    try:
        parse_response = await _post_upstream(
            settings.parser_url, "/parse", {"source": req.source, "name": name})
    except UpstreamDown as down:
        return _bad_gateway(down.base_url)

    if parse_response.status_code != 200:
        return Response(content=parse_response.content,
                        status_code=parse_response.status_code,
                        media_type="application/json")
    parsed = parse_response.json()
    if not parsed["valid"]:
        return JSONResponse(status_code=422, content={
            "detail": "El flow no pasó la validación",
            "issues": parsed["issues"],
        })

    try:
        register_response = await _post_upstream(
            settings.registry_url, f"/flows/{name}",
            {
                "source": req.source,
                "version": req.version,
                "description": req.description,
                "ast": parsed["ast"],
                "checksum": parsed["checksum"],
            },
        )
    except UpstreamDown as down:
        return _bad_gateway(down.base_url)

    if register_response.status_code >= 400:
        return Response(content=register_response.content,
                        status_code=register_response.status_code,
                        media_type="application/json")
    result: dict[str, Any] = register_response.json()
    result["issues"] = parsed["issues"]  # warnings no bloqueantes
    log.info("flow_deployed", flow_name=name, version=req.version)
    return JSONResponse(status_code=201, content=result)


@app.post("/parse", dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def parse_only(request: Request) -> Response:
    """Solo valida: no persiste nada, por eso alcanza con flows:read."""
    return await _proxy(request, get_settings().parser_url, "/parse")


# -------------------------------------------------------- routing registry

@app.get("/flows", dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def list_flows(request: Request) -> Response:
    return await _proxy(request, get_settings().registry_url, "/flows")


@app.get("/flows/{name}", dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def flow_versions(request: Request, name: str) -> Response:
    return await _proxy(request, get_settings().registry_url, f"/flows/{name}")


@app.get("/flows/{name}/{version}",
         dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def flow_version(request: Request, name: str, version: str) -> Response:
    return await _proxy(request, get_settings().registry_url,
                        f"/flows/{name}/{version}")


# -------------------------------------------------------- routing executor

@app.post("/execute", dependencies=[Depends(auth.require(auth.INSTANCES_TRIGGER))])
async def execute(request: Request) -> Response:
    return await _proxy(request, get_settings().executor_url, "/execute")


@app.get("/instances", dependencies=[Depends(auth.require(auth.INSTANCES_READ))])
async def instances(request: Request) -> Response:
    return await _proxy(request, get_settings().executor_url, "/instances")


@app.get("/instances/{instance_id}",
         dependencies=[Depends(auth.require(auth.INSTANCES_READ))])
async def instance(request: Request, instance_id: str) -> Response:
    return await _proxy(request, get_settings().executor_url,
                        f"/instances/{instance_id}")


@app.post("/instances/{instance_id}/signal",
          dependencies=[Depends(auth.require(auth.INSTANCES_SIGNAL))])
async def signal(request: Request, instance_id: str) -> Response:
    return await _proxy(request, get_settings().executor_url,
                        f"/instances/{instance_id}/signal")


@app.post("/instances/{instance_id}/retry",
          dependencies=[Depends(auth.require(auth.INSTANCES_RETRY))])
async def retry(request: Request, instance_id: str) -> Response:
    return await _proxy(request, get_settings().executor_url,
                        f"/instances/{instance_id}/retry")


_ENTITY_SCOPES = {"GET": auth.ENTITIES_READ,      # incluye la vista 360
                  "POST": auth.ENTITIES_WRITE,
                  "PATCH": auth.ENTITIES_WRITE}


@app.api_route("/entities/{rest:path}", methods=["GET", "POST", "PATCH"],
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
async def entities(request: Request, rest: str) -> Response:
    return await _proxy(request, get_settings().executor_url, f"/entities/{rest}")


@app.api_route("/relations/{rest:path}", methods=["GET", "POST", "PATCH"],
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
async def relations(request: Request, rest: str) -> Response:
    return await _proxy(request, get_settings().executor_url, f"/relations/{rest}")


# -------------------------------------------------------- routing composer

@app.api_route("/compose", methods=["POST"],
               dependencies=[Depends(auth.require(auth.COMPOSE_WRITE))])
async def compose(request: Request) -> Response:
    return await _proxy(request, get_settings().composer_url, "/compose")


@app.api_route("/drafts", methods=["GET"],
               dependencies=[Depends(auth.require(auth.COMPOSE_READ))])
async def drafts(request: Request) -> Response:
    return await _proxy(request, get_settings().composer_url, "/drafts")


@app.api_route("/drafts/{rest:path}", methods=["GET", "POST"],
               dependencies=[Depends(auth.require_por_metodo(
                   {"GET": auth.COMPOSE_READ, "POST": auth.COMPOSE_WRITE}))])
async def draft_ops(request: Request, rest: str) -> Response:
    return await _proxy(request, get_settings().composer_url, f"/drafts/{rest}")
