---
project: copp-ia
status: completed
created: 2026-07-14
updated: 2026-07-14
tags: [fase-d, seguridad, gateway, api-keys, scopes, autorizacion]
---

# Seguridad — API keys con scopes

## Goal
Tercer ítem de **Fase D** ([[roadmap]], sección "Seguridad"): que una credencial pueda hacer
**solo lo que necesita**. Hoy hay una sola key global: quien puede leer una vista 360 puede
también **desplegar código** en el organismo.

## Context
Provenance: `copp-ia@devyos@9eee632` (código leído en esa rama/commit).

### Hecho verificado
`teleflow/gateway/main.py:70-82` — el middleware `auth_and_rate_limit` compara el header
`X-TeleFlow-API-Key` contra `settings.teleflow_api_key` (una sola string, en
`common/config.py`) y, si coincide, deja pasar **cualquier** ruta. No hay noción de permisos:
las 15 rutas del gateway (deploy de flows, trigger, signal, retry, entities, compose) son
equivalentes para el auth. El rate limit sí es por key (`_buckets`), así que la key ya es la
unidad de identidad — solo le falta autorización.

`PUBLIC_PATHS` (`main.py:26`) exime a `/health`, `/ready`, `/metrics` y la doc: eso está bien
y no se toca.

## Chunks
1. **Scopes por endpoint** (este chunk, rama `feat/api-key-scopes`): modelar los permisos,
   que el gateway los exija por ruta, y permitir restringir la key global por env.
   **Compatible hacia atrás:** sin config, la key global mantiene todos los scopes.
2. **Múltiples keys** con su propio conjunto de scopes, persistidas y **hasheadas**, con
   identidad para auditoría (quién disparó qué).
3. **Rotación / revocación** sin reiniciar el stack.

## Current State
**Chunk 1 ✅ hecho** y mergeado a `devyos`. Suite 87→**98**, mypy strict 0.
**Verificado en vivo:** con el default (`*`) todo sigue andando (deploy 201); con
`TELEFLOW_API_KEY_SCOPES=entities:read,instances:read` la misma key lee la 360 y las
instancias, pero recibe **403 en deploy, en `/execute` y al escribir entidades**.

Próximo: Chunk 2 (múltiples keys hasheadas con scopes propios e identidad para auditoría).

## Next Steps
- [x] 10 scopes por familia de acción (no uno por ruta) en `gateway/auth.py`.
- [x] `require(scope)` / `require_por_metodo(...)` como dependencias de FastAPI; el middleware
      autentica (401) y deja los scopes en `request.state`.
- [x] `TELEFLOW_API_KEY_SCOPES` (default `*`) — compatible hacia atrás.
- [x] 11 tests + verificación en vivo contra el stack.
- [x] **Bug encontrado de paso y arreglado** (`31ad326`): `deploy_flow` llamaba al parser y al
      registry **sin** atrapar errores de transporte (solo `_proxy` lo hacía) → con el parser
      caído el gateway reventaba con un **500 y stack** en vez de 502. Verificado apagando el
      parser: ahora responde 502 "Servicio no disponible". `_proxy` además pasó de
      `ConnectError` a `RequestError` (un timeout tampoco cae en 500).
- [x] **Chunk 2** (`6b9137f`, rama `feat/api-keys-db`): tabla `api_keys` (alembic `0002`) con
      identidad + hash SHA-256 + scopes; el gateway resuelve contra la DB con cache TTL; la key
      de env queda como **bootstrap** (se resuelve sin tocar la DB). `POST`/`GET /keys` bajo el
      scope nuevo `keys:admin`. **Bug real encontrado:** cuando Postgres no responde, la
      excepción es `ConnectionRefusedError` (un `OSError`) y **SQLAlchemy no la envuelve** — el
      `except SQLAlchemyError` no la atrapaba y el gateway habría dado 500. Ahora → 401.
- [x] **Chunk 3** (`a592f8f`, rama `feat/api-key-rotation`): `DELETE /keys/{id}` (revoca y
      **purga el cache en el acto**: el corte no espera los 30 s del TTL) y
      `POST /keys/{id}/rotate` (secreto nuevo, misma identidad y scopes). No se borra la fila:
      la auditoría se conserva.

## Decisions
- **Autenticación en el middleware, autorización en la ruta.** El middleware ya valida la key
  y el rate limit; el scope depende de la ruta, así que va como dependencia de cada endpoint.
  Alternativa descartada: una tabla `(método, patrón de path) → scope` dentro del middleware —
  se desincroniza silenciosamente al agregar una ruta.
- **Default permisivo, opt-in restrictivo.** Sin `TELEFLOW_API_KEY_SCOPES`, la key global
  conserva todos los scopes: ninguna instalación existente se rompe con el upgrade. La
  restricción es una decisión explícita del operador.

## Sources
- `teleflow/gateway/main.py` (middleware, rutas), `teleflow/common/config.py`
- [[roadmap]] (Fase D — Seguridad)

## Cierre (2026-07-14)

**Resultado:** los 3 chunks hechos y mergeados a `devyos`. Suite 87→**110**, mypy strict **0**,
e2e contra el stack real. Tercer ítem de Fase D cerrado.

En una línea: **una credencial ahora puede hacer solo lo suyo, tiene nombre propio, y se corta
al instante si se filtra.**

### Decisiones (las que hay que conocer para no romperlas)
- **La key de env quedó como bootstrap**, y se resuelve **sin tocar la DB**. Si Postgres no
  responde o la migración no corrió, el operador no queda afuera de su propia plataforma.
- **SHA-256, no bcrypt/argon2.** Son secretos aleatorios de alta entropía generados por el
  sistema, no contraseñas humanas: no hay nada que adivinar por fuerza bruta, y el hash se
  verifica en **cada request** (bcrypt solo agregaría latencia).
- **Cache con TTL** (patrón del `DomainLoader`), pero **la revocación purga el cache en el
  acto**: sin eso, "revocar" habría significado "en un ratito", que es inútil ante una fuga.
- **`keys:admin` es un scope como cualquier otro:** repartir permisos es un permiso. Una key
  común no puede crear, revocar ni rotar credenciales — tampoco la propia.

### Aprendizajes
- **La excepción que no era la que yo creía.** Cuando Postgres no responde, lo que llega es un
  `ConnectionRefusedError` (`OSError`) — SQLAlchemy **no** lo envuelve. Un `except
  SQLAlchemyError` "obvio" dejaba pasar el 500. Lo encontró un test que fallaba por la razón
  correcta, no el código.
- **Un cache convierte una feature de seguridad en una mentira si no se lo invalida.** La
  revocación "funcionaba" en la DB mientras la key seguía entrando 30 s por el cache.

## Límite conocido (no bloquea, decisión consciente)
La purga del cache es **del proceso**. Con varias réplicas del gateway, las demás siguen
aceptando la key revocada hasta que venza su propio TTL (≤ `api_key_cache_ttl`, default 30 s).
Para revocación inmediata cross-réplica haría falta invalidación por **Redis pub/sub** — el
executor ya usa ese patrón para las señales ([[2026-06-30-adr-002-durable-sleep]]). Queda como
candidato si se despliega el gateway con más de una réplica.

## Log
- 2026-07-14: **CERRADO** (`status: completed`). Chunks 2 y 3 hechos y mergeados a `devyos`.
- 2026-07-14: **Chunk 1 cerrado** (`e86c834` + fix `31ad326`), mergeado a `devyos`. Suite 98,
  mypy 0. Sigue el Chunk 2.
- 2026-07-14: creado. Chunk 1 (scopes por endpoint) en marcha.
