---
project: copp-ia
status: active
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
- [ ] **Chunk 2:** múltiples keys, hasheadas, con scopes e identidad propios.
- [ ] **Chunk 3:** rotación / revocación sin reiniciar el stack.

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

## Log
- 2026-07-14: **Chunk 1 cerrado** (`e86c834` + fix `31ad326`), mergeado a `devyos`. Suite 98,
  mypy 0. Sigue el Chunk 2.
- 2026-07-14: creado. Chunk 1 (scopes por endpoint) en marcha.
