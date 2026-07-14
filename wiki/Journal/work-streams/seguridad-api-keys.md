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
Arrancando el Chunk 1.

## Next Steps
- [ ] Definir el set de scopes (uno por familia de acción, no uno por ruta).
- [ ] `require(scope)` como dependencia de FastAPI; el middleware sigue autenticando y
      resuelve los scopes de la key en `request.state`.
- [ ] `TELEFLOW_API_KEY_SCOPES` (default `*` = todos) para poder correr una key restringida.
- [ ] Tests: 403 cuando falta el scope, 200/502 (o sea, pasa el auth) cuando lo tiene.
- [ ] Verificar en vivo contra el stack.

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
- 2026-07-14: creado. Chunk 1 (scopes por endpoint) en marcha.
