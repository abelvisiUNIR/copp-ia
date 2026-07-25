---
project: copp-ia
type: backlog
provenance: copp-ia@devyos@5941771
created: 2026-07-25
updated: 2026-07-25
tags: [backlog, calidad, seguridad, producto, auditoria]
---

# Backlog de endurecimiento — huecos encontrados en la revisión del 2026-07-25

> Documento **vivo**. Provenance: `copp-ia@devyos@5941771`. Sale de una revisión transversal
> del repo pedida por el owner ("toda recomendación, idea o mejora que le aporte a la app").
> No reemplaza al [[roadmap]] — ahí están las fases; acá están los huecos concretos con su
> evidencia, para poder priorizarlos sin volver a buscarlos.

## Cómo leer esta página
Cada ítem tiene **Hecho** (verificado, con archivo y línea), **Por qué importa** y **Costo
estimado**. Lo que es proyección y no lectura de código va marcado `(inferencia)`.

---

## 1. No hay auditoría persistida — solo logs
**Estado:** ✅ **cerrado 2026-07-25** ([[auditoria-persistida]], `982f12b` + `072070a`) —
tabla `audit_log` append-only (migración `0004`), escritura enganchada en `auth.require` para
que ninguna ruta quede afuera, y `GET /audit` con scope propio `audit:read`. Ver
[[2026-07-25-auditoria-persistida]]. · **Prioridad original:** alta

**Hecho.** `teleflow/common/models.py` define 11 tablas y **ninguna es de auditoría**:
`flow_definitions`, `flow_latest`, `process_instances`, `instance_transitions`,
`entity_state`, `entity_events`, `relation_state`, `signals`, `flow_drafts`,
`rule_timer_log`, `api_keys`. La identidad de la key **sí** se conserva a propósito
(`gateway/main.py:252`: "no se borra la fila: la identidad se conserva para la auditoría"),
pero el registro de **qué hizo** esa key va a stdout — `gateway/auth.py:81`: "`name` va a los
logs (auditoría)".

**Por qué importa.** Un `POST` al gateway despliega código ejecutable. "Quién desplegó qué
versión y cuándo" tiene que ser una consulta, no un grep sobre logs rotados.
`(inferencia)` en un organismo público suele ser requisito duro y no mejora, dado que el
producto se instancia por organismo ([[2026-06-30-adr-005-aislamiento-instancia]]).

**Costo.** Bajo: está el 90%. Ya hay identidad por key, ya hay scopes que nombran la acción
([[seguridad-api-keys]]) y ya existe el patrón de tabla append-only (`instance_transitions`,
`entity_events`). Es una tabla + un middleware + una migración.

## 2. `registry-service` no tiene un solo test
**Estado:** ✅ **cerrado 2026-07-25** (`registry-cobertura`, `4c7ce34`) — 23 tests (17
unitarios + 6 e2e contra Postgres real). Aparecieron **tres defectos**: un prerelease se
ordenaba por encima de su release y se volvía `latest`, un prerelease que empataba también
movía el pointer (por el `>=`), y la carrera entre el `SELECT` y el `INSERT` devolvía 500 en
vez de 409. · **Prioridad original:** alta

**Hecho.** `tests/` cubre adapters, api_keys, business_metrics, dag, engine_retry,
error_handling, events, gateway_scopes, observability, openapi, parser, tooling y validator,
más `tests/e2e/`. **Sin tests: `registry_service`, `composer_service` y `cli.py`.**

**Por qué importa.** El registry existe para garantizar el **versionado inmutable** de flows.
El invariante "una versión ya desplegada no se sobreescribe" es su razón de ser y hoy no lo
prueba nada: es la clase de garantía que un refactor rompe en silencio y que se descubre
cuando alguien ya pisó una versión en producción.

**Costo.** Bajo. (El hueco de `composer_service` lo cierra [[composer-llm-hardening]]; el de
`cli.py` queda anotado acá.)

## 3. El rate limit es por proceso — y es la segunda vez que aparece el mismo supuesto
**Estado:** abierto · **Prioridad:** media (decisión), baja (implementación)

**Hecho.** `gateway/main.py:92` — `_buckets` es un dict en memoria del proceso. Con N réplicas
del gateway el límite efectivo es N × `rate_limit_rpm`. Es **el mismo límite** ya anotado
conscientemente al cerrar [[seguridad-api-keys]]: "la purga es del proceso; con varias réplicas
haría falta invalidación por Redis pub/sub".

**Por qué importa.** Dos features distintas comparten un supuesto que nadie escribió: *el
gateway corre en un solo proceso*. Redis ya está en el stack. Mismo patrón que
[[fallas-silenciosas]], pero con un supuesto en vez de un error: no hace ruido hasta que se
escala.

**Acción recomendada.** Un **ADR corto que lo decida de una vez** — "el gateway es
single-process por diseño hasta Fase E" o "el estado compartido va a Redis" — en vez de
re-descubrirlo en la tercera feature.

## 4. `/execute` no tiene idempotencia
**Estado:** abierto · **Prioridad:** media-alta

**Hecho.** `gateway/main.py:405-408` es un proxy plano al executor, sin `Idempotency-Key` ni
deduplicación.

**Por qué importa.** `(inferencia)` un cliente que reintenta por timeout dispara dos instancias
del proceso: dos expedientes, dos notificaciones al ciudadano, dos llamadas a la integración
REST. En orquestación de negocio el doble disparo no es un problema de performance, es un dato
incorrecto en el mundo real.

**Costo.** Bajo **ahora** (un header + una tabla de claves vistas), alto después: retrofitear
idempotencia con instancias ya creadas en producción obliga a decidir qué hacer con los
duplicados que ya existen.

## 5. `review-ui`: el componente con más poder y menos cobertura
**Estado:** abierto · **Prioridad:** media

**Hecho.** 266 líneas en 4 archivos (`App.jsx` 186, `api.js` 43, `diff.js` 31, `main.jsx` 6).
Cero tests, sin lint. CI solo buildea la imagen Python (`ci.yml:78-84`); el front se construye
únicamente dentro del `docker compose up` del job e2e. La API key vive en `localStorage`
(`api.js:6`).

**Por qué importa.** Desde ahí se **aprueba y despliega** código (`approve` → deploy vía
gateway). Es la superficie donde un error tiene el mayor radio de daño y la única sin red de
seguridad.

## 6. Backup/restore probado — separarlo y adelantarlo de Fase E
**Estado:** abierto · **Prioridad:** media (subir antes de producción)

**Hecho.** `roadmap.md:113` lo lista dentro de Fase E, junto a Helm en k8s, HPA, StatefulSets
en HA y runbooks.

**Por qué importa.** Es lo único de esa lista que, si falta el día que se necesita, **no tiene
arreglo posible**. Un `pg_dump` + restore verificado por un test vale hoy más que los Helm
charts, y no depende de tener k8s.

## 7. `review-ui` se buildea sin lockfile — el bundle no es reproducible
**Estado:** abierto · **Prioridad:** media-baja

**Hecho.** `review-ui/package.json` declara rangos flotantes (`react: ^18.3.1`,
`vite: ^5.3.1`) y **no hay `package-lock.json` versionado**. El `Dockerfile` hace
`COPY package.json ./` + `RUN npm install`, así que ni siquiera usaría un lockfile si
existiera: cada build resuelve versiones de nuevo.

**Por qué importa.** `(inferencia)` dos builds de la misma commit en fechas distintas pueden
producir bundles distintos. Para un producto que se instala por organismo, "el front que
tiene el cliente" no es una función de la commit.

**Costo.** Bajo, y son dos mitades que van juntas: versionar el lockfile **y** cambiar el
`Dockerfile` a `COPY package.json package-lock.json ./` + `npm ci`. Versionar el lock sin lo
segundo no cambia nada.

---

## Ideas de producto (no son deuda)
- **UI operativa mínima antes que la colección `.http`.** El roadmap la marca opcional
  (`roadmap.md:105`), pero ataca la pregunta operativa real —"¿por qué se frenó este
  expediente?"— y los datos ya están en `instance_transitions`. `(inferencia)` valor operativo
  mayor que el de la colección `.http`, a costo comparable.
- **`tflow trace <instance_id>`** — línea de tiempo de una instancia desde
  `instance_transitions`, sin levantar UI. El CLI ya tiene `status` (`cli.py:99`); esto sería
  su versión narrativa. Verificar primero cuánto de esto ya cubre `status`.

## Orden propuesto
1. ~~Auditoría persistida (1)~~ ✅ · ~~Tests del registry (2)~~ ✅ — ambos hechos 2026-07-25.
2. **Antes de tener tráfico real** (se abaratan mucho decidiéndolos temprano): idempotencia de
   `/execute` (4) y el ADR de estado compartido del gateway (3).
3. **Antes de Fase E:** backup/restore (6), la red de seguridad de `review-ui` (5) y el
   lockfile del front (7).

## Hallazgos laterales, todavía abiertos
- **Postgres no se publica al host** en `docker-compose.yml`. No es un bug —es más seguro— pero
  hace que cualquier test que toque la base pague ~4 s en conexiones fallidas antes de darse
  cuenta. Descubierto al implementar la auditoría; resuelto ahí con un sink en memoria, pero el
  próximo que escriba un test con DB se lo va a encontrar de nuevo.
- **La API del registry no valida que `version` sea semver.** `banana` se registra y queda al
  fondo del orden (hay un test que lo fija). Rechazarlo es un cambio de contrato que rompería
  instalaciones con versiones libres, así que se documenta en vez de cortarlo — pero si alguna
  vez se decide validar, es acá.
- **`audit_log.details` es un footgun.** Hoy solo el deploy lo usa (versión + checksum). Nada
  impide que mañana alguien meta ahí un dato personal, justo en la tabla que más se conserva y
  más gente puede leer. Vale una lista blanca de claves si el uso crece.

## Sources
`teleflow/common/models.py` · `teleflow/gateway/main.py:92,252,405-408` ·
`teleflow/gateway/auth.py:81` · `teleflow/cli.py:99` · `review-ui/src/*` ·
`.github/workflows/ci.yml:78-84` · `tests/` · [[roadmap]] · [[seguridad-api-keys]] ·
[[fallas-silenciosas]] · [[composer-llm-hardening]]
