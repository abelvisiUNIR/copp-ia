"""api-gateway :8000 — único punto de entrada externo.

Auth (X-TeleFlow-API-Key) · rate limiting (token bucket por API key) ·
routing hacia los servicios core. Los clientes solo conocen este endpoint.

Deploy de un flow: POST /flows/{name}
  gateway → parser-service (valida) → registry-service (persiste)
"""
import asyncio
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from prometheus_client import Counter

from teleflow.common.config import Settings, get_settings
from teleflow.common.db import db_ping, get_sessionmaker, init_db
from teleflow.common.logging import setup_logging
from teleflow.common.models import ApiKey, AuditLog
from teleflow.common.observability import setup_observability
from teleflow.gateway import auth

log = setup_logging("api-gateway")

PUBLIC_PATHS = {"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"}

client: httpx.AsyncClient | None = None

#: Estado de proceso del gateway (conexión Redis y tarea del listener).
state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global client
    settings = get_settings()
    client = httpx.AsyncClient(timeout=60.0)
    init_db(settings)   # las API keys viven en Postgres (tabla api_keys)

    # Redis solo para invalidar el cache de keys entre réplicas. Si no está, el gateway
    # funciona igual: la purga local sigue andando y el TTL sigue siendo el techo.
    try:
        state["redis"] = aioredis.from_url(settings.redis_url, decode_responses=True)
        state["listener"] = asyncio.create_task(_escuchar_revocaciones())
    except Exception as exc:
        log.warning("redis_unavailable_at_startup", error=str(exc))

    yield

    listener = state.get("listener")
    if listener is not None:
        listener.cancel()
    redis = state.get("redis")
    if redis is not None:
        await redis.aclose()
    await client.aclose()


# Declara el esquema de auth en OpenAPI para que Swagger muestre "Authorize" y
# envíe el header. auto_error=False: la validación real la hace el middleware.
api_key_scheme = APIKeyHeader(name="X-TeleFlow-API-Key", auto_error=False)

app = FastAPI(title="TeleFlow API Gateway", version="1.0.0", lifespan=lifespan,
              dependencies=[Depends(api_key_scheme)])
# El gateway no tenía readiness real: sin Postgres no puede resolver ninguna key de la tabla
# `api_keys` **ni** escribir auditoría, así que declararse listo sería mentir.
setup_observability(app, "api-gateway", ready_check=db_ping)


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


#: Buckets por proceso. Dejaron de ser el mecanismo principal —ahora el contador vive en
#: Redis y lo comparten todas las réplicas— pero se conservan como red de seguridad para
#: cuando Redis no está: limitar por proceso protege menos que limitar de verdad, y muchísimo
#: más que no limitar.
_buckets: dict[str, TokenBucket] = {}

RATE_LIMIT_DEGRADADO = Counter(
    "teleflow_rate_limit_degraded_total",
    "Requests limitados por proceso porque Redis no respondió",
)


async def permite_el_limite(api_key: str, settings: Settings) -> bool:
    """Ventana fija por minuto, compartida entre réplicas.

    `INCR` + `EXPIRE` y no token bucket: el bucket necesita leer-modificar-escribir con estado
    propio, que en Redis pide script Lua o transacción. La ventana fija son dos comandos y
    ningún estado que mantener; a 120 rpm el suavizado en los bordes no cambia nada práctico.

    La key va **hasheada**: Redis no es lugar para una credencial, ni siquiera como parte del
    nombre de una clave.
    """
    redis = state.get("redis")
    if redis is not None:
        ventana = int(time.time() // 60)
        clave = f"ratelimit:{auth.hash_key(api_key)}:{ventana}"
        try:
            usados = await redis.incr(clave)
            if usados == 1:
                # Dos ventanas de vida: la clave se limpia sola y sobrevive al borde.
                await redis.expire(clave, 120)
            return bool(usados <= settings.rate_limit_rpm)
        except Exception as exc:
            # Un limitador caído no puede convertirse en una caída del producto. Se degrada al
            # bucket del proceso —lo que había antes— y **se cuenta**: si nadie mira este
            # contador, el límite vuelve a ser N× con N réplicas sin que se entere nadie.
            RATE_LIMIT_DEGRADADO.inc()
            log.error("rate_limit_redis_failed", error=str(exc))

    return _buckets.setdefault(api_key, TokenBucket(settings.rate_limit_rpm)).allow()


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

    if not await permite_el_limite(api_key, settings):
        return JSONResponse(status_code=429,
                            content={"detail": "Rate limit excedido"})

    request.state.identidad = identidad
    return await call_next(request)


# ------------------------------------------------------------------ auditoría

AUDIT_WRITE_FAILURES = Counter(
    "teleflow_audit_write_failures_total",
    "Registros de auditoría que no se pudieron escribir",
)


@app.middleware("http")
async def auditar(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Registra la acción **después** de conocer su resultado.

    Se declara después de `auth_and_rate_limit` para quedar por fuera de él: así ve también
    los 401, que ese middleware corta antes de llegar a ninguna ruta.

    Qué se registra lo decide el scope que la ruta exigió (`auth.marcar_scope`), no una lista
    de rutas: una ruta nueva con scope de escritura queda auditada sin que su autor haga nada.
    """
    publico = request.url.path in PUBLIC_PATHS or request.method == "OPTIONS"

    try:
        response = await call_next(request)
    except Exception:
        # Una ruta que revienta es el intento **más** interesante de registrar: sin esto, un
        # deploy que crashea a mitad de camino no dejaba rastro (el 500 lo arma un middleware
        # de Starlette que está por fuera de este, así que `call_next` propaga la excepción).
        if not publico:
            await _registrar_auditoria(request, 500, auth.scope_exigido(request))
        raise

    if publico:
        return response

    scope = auth.scope_exigido(request)
    # 401/403/429 = "no te dejé". Se registran siempre, aunque la acción fuera de lectura:
    # son la señal más barata de una credencial filtrada probando permisos o martillando.
    # En estos casos el scope suele venir vacío, porque el request no llegó a la ruta.
    denegado = response.status_code in (401, 403, 429)
    if not denegado and scope not in auth.SCOPES_AUDITADOS:
        return response  # lectura exitosa: no se audita (ver el ADR)

    await _registrar_auditoria(request, response.status_code, scope)
    return response


def _subject_de(path: str) -> str | None:
    """Identificador del recurso: todo lo que sigue a la colección.

    `/flows/alta_socio` → `alta_socio`; `/entities/socio/12345` → `socio/12345`.

    Se queda con **todos** los segmentos, no solo el primero: en las rutas anidadas el
    primero es el *tipo* y el segundo el registro, y una auditoría que dijera "alguien
    modificó un socio" sin decir cuál no sirve para lo que existe.

    Genérico a propósito: derivarlo de una tabla de rutas sería otra lista que mantener.
    """
    partes = [p for p in path.split("/") if p]
    return "/".join(partes[1:])[:200] if len(partes) > 1 else None


async def _registrar_auditoria(request: Request, status_code: int, scope: str) -> None:
    identidad: auth.Identidad | None = getattr(request.state, "identidad", None)
    try:
        async with get_sessionmaker()() as session:
            session.add(AuditLog(
                actor_name=identidad.name if identidad is not None else "key inválida",
                actor_key_id=identidad.key_id if identidad is not None else None,
                scope=scope,
                method=request.method,
                path=str(request.url.path)[:500],
                subject=_subject_de(request.url.path),
                status_code=status_code,
                details=auth.detalles_de(request),
            ))
            await session.commit()
    except Exception as exc:
        # `except Exception` deliberado y **no silencioso**: la acción ya ocurrió y no se puede
        # deshacer, así que romper la respuesta no arregla nada. Pero quedarse sin auditoría
        # tiene que ser visible — de ahí el contador (alertable) y el log de error. Ver el
        # límite consciente en el ADR: esto es best-effort en el margen.
        AUDIT_WRITE_FAILURES.inc()
        log.error("audit_write_failed", error=str(exc), method=request.method,
                  path=request.url.path, status_code=status_code, scope=scope)


# ------------------------------------------------------ resolución de la key

# hash de la key -> (identidad, vence_en). Evita ir a la DB en cada request.
_cache_keys: dict[str, tuple[auth.Identidad, float]] = {}

#: Canal donde se anuncian las keys revocadas. Cada réplica del gateway escucha y purga la
#: suya: sin esto, revocar solo cortaba en el proceso que atendió el `DELETE`, y las demás
#: seguían aceptando la credencial hasta que venciera su propio TTL.
CANAL_REVOCACIONES = "teleflow:keys:revocadas"

REVOCACIONES_RECIBIDAS = Counter(
    "teleflow_key_revocations_received_total",
    "Revocaciones de key recibidas por pub/sub desde otra réplica",
)
REVOCACIONES_NO_PUBLICADAS = Counter(
    "teleflow_key_revocations_unpublished_total",
    "Revocaciones que no se pudieron anunciar al resto de las réplicas",
)


def purgar_cache(key_hash: str) -> None:
    """Saca una key del cache de **este** proceso, sin esperar el TTL.

    Es la mitad local de la revocación: el anuncio a las demás réplicas lo hace
    `anunciar_revocacion`.
    """
    _cache_keys.pop(key_hash, None)


async def anunciar_revocacion(key_hash: str) -> None:
    """Purga local + anuncio al resto de las réplicas.

    El `DELETE /keys/{id}` solo pasa por **una** réplica; las demás se enteran por acá. El TTL
    de `api_key_cache_ttl` queda como red de seguridad si el mensaje se pierde, no como el
    mecanismo principal: para una credencial filtrada, esos segundos son justo lo que la
    revocación existe para evitar.
    """
    purgar_cache(key_hash)
    redis = state.get("redis")
    if redis is None:
        return  # sin Redis configurado: queda la purga local y el TTL
    try:
        await redis.publish(CANAL_REVOCACIONES, key_hash)
    except Exception as exc:
        # No se rompe la revocación por esto: local ya quedó purgada y las otras réplicas
        # tienen el TTL. Pero que el anuncio falle **no puede ser invisible**: la ventana
        # vuelve a ser de `api_key_cache_ttl` segundos sin que nadie lo sepa.
        REVOCACIONES_NO_PUBLICADAS.inc()
        log.error("key_revocation_publish_failed", error=str(exc))


async def _escuchar_revocaciones() -> None:
    """Suscripción con reconexión: el listener nunca muere (mismo patrón que el executor)."""
    import redis.exceptions as redis_exc

    while True:
        try:
            redis = state.get("redis")
            if redis is None:
                return
            pubsub = redis.pubsub()
            await pubsub.subscribe(CANAL_REVOCACIONES)
            log.info("key_revocation_listener_started", channel=CANAL_REVOCACIONES)
            try:
                while True:
                    try:
                        mensaje = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=5.0)
                    except (TimeoutError, redis_exc.TimeoutError):
                        continue  # timeout periódico: la suscripción sigue viva
                    if mensaje is None or mensaje.get("type") != "message":
                        continue
                    key_hash = mensaje["data"]
                    if isinstance(key_hash, bytes):
                        key_hash = key_hash.decode("utf-8")
                    purgar_cache(str(key_hash))
                    REVOCACIONES_RECIBIDAS.inc()
                    log.info("key_revocation_applied")
            finally:
                await pubsub.aclose()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.error("key_revocation_listener_crashed_restarting", error=repr(exc))
            await asyncio.sleep(3)


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


async def _proxy(request: Request, base_url: str, path: str,
                 extra_headers: dict[str, str] | None = None) -> Response:
    """Reenvía al servicio interno. Los headers se arman **desde cero**, no se copian los del
    cliente: así nada del exterior se cuela hacia adentro. Una ruta que necesita propagar un
    header concreto lo pasa por `extra_headers`, explícito y a la vista."""
    assert client is not None
    body = await request.body()
    headers = {"Content-Type": "application/json"} if body else {}
    headers.update(extra_headers or {})
    try:
        upstream = await client.request(
            request.method,
            f"{base_url}{path}",
            content=body if body else None,
            params=dict(request.query_params),
            headers=headers,
        )
    except httpx.RequestError:  # conexión rechazada, timeout, DNS
        return _bad_gateway(base_url)
    return Response(content=upstream.content, status_code=upstream.status_code,
                    media_type=upstream.headers.get("content-type", "application/json"))


# ------------------------------------------------------------ consulta de auditoría

@app.get("/audit", tags=["audit"], operation_id="listar_auditoria",
         dependencies=[Depends(auth.require(auth.AUDIT_READ))])
async def listar_auditoria(
    actor: str | None = None,
    scope: str | None = None,
    subject: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    solo_denegados: bool = False,
    limit: int = 100,
) -> Response:
    """Registro de auditoría, del más reciente al más viejo.

    Sin filtros devuelve las últimas `limit` acciones. `subject` matchea por prefijo, para
    que `socio` traiga también `socio/12345` (ver cómo se arma el subject en `_subject_de`).
    """
    query = select(AuditLog).order_by(AuditLog.occurred_at.desc())
    if actor:
        query = query.where(AuditLog.actor_name == actor)
    if scope:
        query = query.where(AuditLog.scope == scope)
    if subject:
        query = query.where(AuditLog.subject.startswith(subject))
    if desde is not None:
        query = query.where(AuditLog.occurred_at >= desde)
    if hasta is not None:
        query = query.where(AuditLog.occurred_at <= hasta)
    if solo_denegados:
        query = query.where(AuditLog.status_code.in_((401, 403, 429)))

    async with get_sessionmaker()() as session:
        filas = (await session.execute(query.limit(max(1, min(limit, 1000))))).scalars().all()

    return JSONResponse([{
        "occurred_at": f.occurred_at.isoformat() if f.occurred_at else None,
        "actor_name": f.actor_name,
        "actor_key_id": str(f.actor_key_id) if f.actor_key_id else None,
        "scope": f.scope,
        "method": f.method,
        "path": f.path,
        "subject": f.subject,
        "status_code": f.status_code,
        "details": f.details,
    } for f in filas])


# --------------------------------------------------------- gestión de keys

class CrearKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)   # identidad, p.ej. "integracion-ceibal"
    scopes: list[str]


@app.post("/keys", status_code=201, tags=["keys"], operation_id="crear_key",
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


@app.delete("/keys/{key_id}", tags=["keys"], operation_id="revocar_key",
            dependencies=[Depends(auth.require(auth.KEYS_ADMIN))])
async def revocar_key(key_id: uuid.UUID) -> Response:
    """Revoca una key (`active=False`) y la saca del cache **sin reiniciar el stack**.

    No se borra la fila: la identidad se conserva para la auditoría (qué hizo esa key).
    """
    async with get_sessionmaker()() as session:
        fila = await session.get(ApiKey, key_id)
        if fila is None:
            return JSONResponse(status_code=404, content={"detail": "key no encontrada"})
        if not fila.active:
            return JSONResponse(status_code=409,
                                content={"detail": f"la key '{fila.name}' ya está revocada"})
        fila.active = False
        key_hash, name = fila.key_hash, fila.name
        await session.commit()

    await anunciar_revocacion(key_hash)
    log.info("api_key_revoked", key_name=name, key_id=str(key_id))
    return JSONResponse(content={"id": str(key_id), "name": name, "active": False})


@app.post("/keys/{key_id}/rotate", tags=["keys"], operation_id="rotar_key",
          dependencies=[Depends(auth.require(auth.KEYS_ADMIN))])
async def rotar_key(key_id: uuid.UUID) -> Response:
    """Genera un secreto nuevo para la misma identidad y scopes. El viejo deja de valer ya.

    Rotar (no revocar + crear) mantiene el `name`, así la auditoría no se corta al cambiar
    el secreto.
    """
    secreto = auth.generar_key()
    async with get_sessionmaker()() as session:
        fila = await session.get(ApiKey, key_id)
        if fila is None:
            return JSONResponse(status_code=404, content={"detail": "key no encontrada"})
        if not fila.active:
            return JSONResponse(
                status_code=409,
                content={"detail": f"la key '{fila.name}' está revocada: no se rota"})
        hash_viejo = fila.key_hash
        fila.key_hash = auth.hash_key(secreto)
        name, scopes = fila.name, [str(s) for s in fila.scopes]
        await session.commit()

    # El secreto viejo deja de entrar en el acto, y en **todas** las réplicas.
    await anunciar_revocacion(hash_viejo)
    log.info("api_key_rotated", key_name=name, key_id=str(key_id))
    return JSONResponse(content={
        "id": str(key_id),
        "name": name,
        "scopes": scopes,
        "key": secreto,
        "aviso": "guardá esta key ahora: la anterior ya no sirve",
    })


@app.get("/keys", tags=["keys"], operation_id="listar_keys",
         dependencies=[Depends(auth.require(auth.KEYS_ADMIN))])
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


@app.post("/flows/{name}", tags=["flows"], operation_id="desplegar_flow",
          dependencies=[Depends(auth.require(auth.FLOWS_DEPLOY))])
async def deploy_flow(name: str, req: DeployRequest, request: Request) -> Response:
    """Valida en parser-service y persiste en registry-service."""
    settings = get_settings()
    # Enriquecimiento para la auditoría: la versión y el checksum permiten responder "¿esta
    # versión es la que se publicó?" sin guardar el código. El checksum se agrega abajo,
    # cuando el parser lo devuelve.
    auth.detallar(request, version=req.version)
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
    auth.detallar(request, checksum=parsed.get("checksum"))
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


@app.post("/parse", tags=["flows"], operation_id="validar_flow",
          dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def parse_only(request: Request) -> Response:
    """Solo valida: no persiste nada, por eso alcanza con flows:read."""
    return await _proxy(request, get_settings().parser_url, "/parse")


# -------------------------------------------------------- routing registry

@app.get("/flows", tags=["flows"], operation_id="listar_flows",
         dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def list_flows(request: Request) -> Response:
    return await _proxy(request, get_settings().registry_url, "/flows")


@app.get("/flows/{name}", tags=["flows"], operation_id="listar_versiones_flow",
         dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def flow_versions(request: Request, name: str) -> Response:
    return await _proxy(request, get_settings().registry_url, f"/flows/{name}")


@app.get("/flows/{name}/{version}", tags=["flows"],
         operation_id="obtener_version_flow",
         dependencies=[Depends(auth.require(auth.FLOWS_READ))])
async def flow_version(request: Request, name: str, version: str) -> Response:
    return await _proxy(request, get_settings().registry_url,
                        f"/flows/{name}/{version}")


# -------------------------------------------------------- routing executor

@app.post("/execute", tags=["instances"], operation_id="ejecutar_flow",
          dependencies=[Depends(auth.require(auth.INSTANCES_TRIGGER))])
async def execute(request: Request) -> Response:
    """Dispara un proceso. Con `Idempotency-Key`, reintentar no crea una instancia nueva.

    El header se propaga explícitamente: el proxy no copia los del cliente, así que sin esta
    línea la clave se perdería en el camino y quien la mandó creería estar protegido.
    """
    clave = request.headers.get("Idempotency-Key")
    return await _proxy(request, get_settings().executor_url, "/execute",
                        extra_headers={"Idempotency-Key": clave} if clave else None)


@app.get("/instances", tags=["instances"], operation_id="listar_instancias",
         dependencies=[Depends(auth.require(auth.INSTANCES_READ))])
async def instances(request: Request) -> Response:
    return await _proxy(request, get_settings().executor_url, "/instances")


@app.get("/instances/{instance_id}", tags=["instances"],
         operation_id="obtener_instancia",
         dependencies=[Depends(auth.require(auth.INSTANCES_READ))])
async def instance(request: Request, instance_id: str) -> Response:
    return await _proxy(request, get_settings().executor_url,
                        f"/instances/{instance_id}")


@app.post("/instances/{instance_id}/signal", tags=["instances"],
          operation_id="enviar_signal",
          dependencies=[Depends(auth.require(auth.INSTANCES_SIGNAL))])
async def signal(request: Request, instance_id: str) -> Response:
    return await _proxy(request, get_settings().executor_url,
                        f"/instances/{instance_id}/signal")


@app.post("/instances/{instance_id}/retry", tags=["instances"],
          operation_id="reintentar_instancia",
          dependencies=[Depends(auth.require(auth.INSTANCES_RETRY))])
async def retry(request: Request, instance_id: str) -> Response:
    return await _proxy(request, get_settings().executor_url,
                        f"/instances/{instance_id}/retry")


_ENTITY_SCOPES = {"GET": auth.ENTITIES_READ,      # incluye la vista 360
                  "POST": auth.ENTITIES_WRITE,
                  "PATCH": auth.ENTITIES_WRITE}


# Un decorador por método: `api_route(methods=[...])` genera una operación por método y
# todas heredarían el mismo operation_id, que en un cliente generado colisiona.
@app.api_route("/entities/{rest:path}", methods=["GET"], tags=["entities"],
               operation_id="consultar_entities",   # incluye la vista 360
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
@app.api_route("/entities/{rest:path}", methods=["POST"], tags=["entities"],
               operation_id="crear_entity",
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
@app.api_route("/entities/{rest:path}", methods=["PATCH"], tags=["entities"],
               operation_id="actualizar_entity",
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
async def entities(request: Request, rest: str) -> Response:
    return await _proxy(request, get_settings().executor_url, f"/entities/{rest}")


@app.api_route("/relations/{rest:path}", methods=["GET"], tags=["entities"],
               operation_id="consultar_relations",
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
@app.api_route("/relations/{rest:path}", methods=["POST"], tags=["entities"],
               operation_id="crear_relation",
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
@app.api_route("/relations/{rest:path}", methods=["PATCH"], tags=["entities"],
               operation_id="actualizar_relation",
               dependencies=[Depends(auth.require_por_metodo(_ENTITY_SCOPES))])
async def relations(request: Request, rest: str) -> Response:
    return await _proxy(request, get_settings().executor_url, f"/relations/{rest}")


# -------------------------------------------------------- routing composer

@app.api_route("/compose", methods=["POST"],
               tags=["composer"], operation_id="componer_draft",
               dependencies=[Depends(auth.require(auth.COMPOSE_WRITE))])
async def compose(request: Request) -> Response:
    return await _proxy(request, get_settings().composer_url, "/compose")


@app.api_route("/drafts", methods=["GET"],
               tags=["composer"], operation_id="listar_drafts",
               dependencies=[Depends(auth.require(auth.COMPOSE_READ))])
async def drafts(request: Request) -> Response:
    return await _proxy(request, get_settings().composer_url, "/drafts")


@app.api_route("/drafts/{rest:path}", methods=["GET"], tags=["composer"],
               operation_id="obtener_draft",
               dependencies=[Depends(auth.require_por_metodo(
                   {"GET": auth.COMPOSE_READ, "POST": auth.COMPOSE_WRITE}))])
@app.api_route("/drafts/{rest:path}", methods=["POST"], tags=["composer"],
               operation_id="operar_draft",   # p.ej. /drafts/{id}/approve
               dependencies=[Depends(auth.require_por_metodo(
                   {"GET": auth.COMPOSE_READ, "POST": auth.COMPOSE_WRITE}))])
async def draft_ops(request: Request, rest: str) -> Response:
    return await _proxy(request, get_settings().composer_url, f"/drafts/{rest}")
