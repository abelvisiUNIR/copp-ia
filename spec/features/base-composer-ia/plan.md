---
project: copp-ia
type: plan
status: implementada
feature: base-composer-ia
provenance: copp-ia@devyos@4c44b4c
created: 2026-09-14
---

<!-- status: borrador | consolidada | implementada (linea base as-built) -->
<!-- Lo escribe el subagente `disenador-tecnico` (comando /disenar). En as-built, "Enfoque" y
     "Archivos que toca" describen como esta resuelto hoy, con cita. -->


# Plan de implementacion — Linea base del composer IA

> As-built. Describe como esta resuelto hoy, no un cambio a hacer. Insumo: `spec.md` y
> `seguridad.md` de esta carpeta; lo que ya documentan se referencia y no se repite. Todo lo que
> no lleva `(inferencia)` se comprobo leyendo el archivo citado en el working tree de
> `copp-ia@devyos@4c44b4c` (el working tree solo tiene cambios sin commitear en `.claude/` y
> `spec/features/`). Las lineas de codigo coinciden con las que cita `spec.md` (`ffd585d`): el
> commit intermedio solo toca la wiki.

## Enfoque

Un servicio FastAPI con estado solo en Postgres, dividido en dos capas:

- **Proveedor LLM detras de un ABC de un metodo** — `LLMProvider.generate(prompt) -> str`
  (`teleflow/composer_service/providers.py:171-177`), cuatro implementaciones elegidas por
  `LLM_PROVIDER` (`teleflow/composer_service/providers.py:269-408`,
  `teleflow/common/config.py:36-39`). `get_provider` falla en vez de caer al stub
  (`teleflow/composer_service/providers.py:418-447`) y se invoca en el `lifespan` para que una
  configuracion imposible no arranque (`teleflow/composer_service/main.py:37-47`). Todas las
  llamadas HTTP al proveedor pasan por `_post_json`, que reintenta solo lo transitorio con el
  criterio de status compartido (`teleflow/composer_service/providers.py:191-254`,
  `teleflow/common/retry.py:26-28`, `:41-48`), y las respuestas `200` inservibles se convierten
  en error con `_texto_o_error` (`teleflow/composer_service/providers.py:257-266`).
- **Ciclo de vida del borrador PR-style** — `POST /compose` genera, limpia fences, valida contra
  el parser-service sin condicionar el guardado y persiste un `FlowDraft`
  (`teleflow/composer_service/main.py:60-105`, `:108-135`); `approve`/`reject`/`PATCH source`
  operan solo sobre `pending` (`teleflow/composer_service/main.py:163-276`). Aprobar despliega
  llamando al gateway con la key de bootstrap (`teleflow/composer_service/main.py:172-179`), asi
  que la aprobacion hereda la re-validacion y la inmutabilidad de versiones del registro
  (`spec.md:399-403`). El contrato de salida es uno solo, `_draft_out`
  (`teleflow/composer_service/main.py:279-301`).

Consumidores (fuera del modulo, citados como frontera):

- **gateway** — unico camino externo. `POST /compose` con `compose:write` y `compose_timeout`
  (`teleflow/gateway/main.py:775-781`); `GET /drafts` y `GET /drafts/{rest}` con `compose:read`;
  `POST /drafts/{rest}` (approve y reject) con `compose:write`
  (`teleflow/gateway/main.py:784-800`); `PATCH /drafts/{id}/source` con `flows:deploy`
  (`teleflow/gateway/main.py:803-816`). Todo pasa por `_proxy`, que arma headers desde cero y
  devuelve el cuerpo entero del upstream (`teleflow/gateway/main.py:409-433`). Ademas el gateway
  es **servidor** del composer: recibe el deploy de la aprobacion en `POST /flows/{name}`
  (`teleflow/gateway/main.py:604-652`).
- **review-ui** — cliente en `review-ui/src/api.js:26-47`. Lista y abre borradores
  (`review-ui/src/App.jsx:76`, `:85-100`), corrige la fuente (`review-ui/src/App.jsx:117-137`),
  aprueba con dos confirmaciones del lado del cliente (`review-ui/src/App.jsx:144-171`), rechaza
  con actor `'dev'` fijo (`review-ui/src/App.jsx:173-184`), muestra badge, proveedor y diff
  contra modelo o version desplegada (`review-ui/src/App.jsx:238-241`, `:266-281`) y compone
  enviando la fuente `latest` como `base_source` (`review-ui/src/App.jsx:457-468`). Detalle en
  `spec/features/base-review-ui/spec.md:82-87`.
- **CLI** — `tflow compose` (sin `base_source`), `tflow drafts`, `tflow approve` con actor `cli`
  por default (`teleflow/cli.py:119-146`, `:209-221`). No hay `reject` ni edicion.
- **parser-service** — dependencia, no consumidor: `POST /parse` al componer y al editar
  (`teleflow/composer_service/main.py:118-122`). Ver
  `spec/features/base-lenguaje-tflow/plan.md:37-38`.

Enfoques descartados, con su ADR:

- LLM fijo (solo Claude), configuracion del proveedor en base de datos, sistema de plugins —
  `wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:35-36`.
- Fallback al stub con `warning` subido a `error`; fallback al stub devolviendo `503`; rechazar
  con `422` el borrador que no compila; guardar `validation` dentro de `comments`; validar
  importando el parser como libreria —
  `wiki/Knowledge/decisions/2026-07-25-composer-llm-fallos-explicitos.md:114-127`.
- No permitir editar y documentar el camino del archivo; editor completo con autocompletado;
  validar en el navegador; exponer solo `base_source`; editar sin revalidar —
  `wiki/Knowledge/decisions/2026-08-27-correccion-del-borrador-en-la-revision.md:144-163`.

Contradicciones con ADRs vigentes:

- **ADR-003 describe un fallback que ya no existe** y `.env.example` con `anthropic`
  (`wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:29-31`); el codigo levanta
  (`teleflow/composer_service/providers.py:434-439`). Ya en `spec.md:447-451`. Corresponde
  **enmendar ADR-003** marcando ese punto como reemplazado por el ADR de fallos explicitos.
- **El ADR de correccion dice que lo editado se valida via `POST /parse` y que ningun formulario
  envia `base_source`** (`2026-08-27-correccion-del-borrador-en-la-revision.md:59-63`, `:68-70`);
  el codigo usa `PATCH /drafts/{id}/source` y el formulario si lo envia. Ya en
  `spec.md:452-461`. Corresponde **enmendar ese ADR**, no el codigo.
- **Decision 4 del ADR de fallos explicitos cumplida a medias**: pide reusar el clasificador
  transitorio/permanente existente (`2026-07-25-composer-llm-fallos-explicitos.md:69-74`,
  `:93-95`), y el composer reusa el de status pero no el de errores de transporte (ver Riesgos).
  Aca el que se aparta es el codigo.
- **La direccion de producto choca con la interfaz fijada por ADR-003.** ADR-003 decide
  `generate(prompt)→str` como contrato (`2026-06-30-adr-003-llm-configurable.md:19-21`); el
  asistente conversacional con `@capacidades` (`AGENTS.md:15-17`) necesita otra forma (ver
  Riesgos). Una feature que lo encare tiene que **proponer la enmienda de ADR-003**, no
  extender el ABC en silencio.

## Archivos que toca

Archivos que componen el modulo y su rol.

| Archivo | Rol |
|---|---|
| `teleflow/composer_service/main.py` | App FastAPI: `lifespan` que valida el proveedor (`:37-47`); `ComposeRequest` (`:54-57`); `POST /compose` con mapeo 422/500/502 y limpieza de fences (`:60-105`); `_validate_source` con `parses: None` (`:108-135`); `GET /drafts` topeado a 100 (`:138-145`); `GET /drafts/{id}` (`:148-154`); `approve` con deploy via gateway (`:157-195`); `reject` (`:198-217`); `PATCH /drafts/{id}/source` con sus tres garantias (`:220-276`); `_draft_out` (`:279-301`). Docstring incompleto (`:1-9`, `spec.md:474-477`) |
| `teleflow/composer_service/providers.py` | `DSL_SYSTEM_PROMPT` con un ejemplo "completo y valido" (`:20-148`); `LLMConfigurationError` / `LLMRequestRejected` / `LLMTransientError` (`:151-168`); `LLMProvider` (`:171-177`); `_retry_after` (`:180-188`); `_post_json` (`:191-254`); `_texto_o_error` (`:257-266`); `AnthropicProvider` 120 s (`:269-301`), `OpenAIProvider` 120 s (`:304-334`), `OllamaProvider` 600 s sin streaming (`:337-372`), `StubProvider` (`:375-408`); `get_provider` (`:411-447`) |
| `teleflow/composer_service/__init__.py` | Marca de paquete |
| `teleflow/common/config.py` | `parser_url`, `composer_url`, `gateway_url` (`:29`, `:32-33`); `teleflow_api_key` y scopes de la key de bootstrap que usa la aprobacion (`:18`, `:23`); capa IA `llm_*` y `compose_timeout` (`:35-58`); `get_settings` cacheada por proceso (`:96-98`). Compartido, no propio |
| `teleflow/common/retry.py` | `is_retryable_status` y `full_jitter_delay`, usados por `_post_json` (`:26-28`, `:41-48`). `is_retryable_transport_error` (`:31-38`) existe y el composer no lo usa |
| `teleflow/common/models.py` | `FlowDraft` (`:174-207`). Compartido |
| `teleflow/common/db.py` · `teleflow/common/logging.py` · `teleflow/common/observability.py` | Sesion y `db_ping` (`teleflow/composer_service/main.py:23`); `setup_logging` (`:34`); `/health`, `/ready` con `db_ping`, `/metrics` HTTP genericas (`teleflow/common/observability.py:28-64`, `teleflow/composer_service/main.py:51`) |
| `alembic/versions/0001_initial.py` · `0003_draft_validation.py` · `0007_fuente_generada_del_borrador.py` | Esquema de `flow_drafts` (ver Migraciones) |
| `teleflow/gateway/main.py` | Frontera: rutas del composer (`:773-816`), `_proxy` (`:409-433`), cliente unico de 60 s (`:51`), deploy que recibe la aprobacion (`:604-652`) |
| `teleflow/gateway/auth.py` | Frontera: `FLOWS_DEPLOY` (`:30`), `COMPOSE_READ` / `COMPOSE_WRITE` "generar/aprobar borradores" (`:37-38`), clasificacion de escritura para auditoria (`:155-158`) |
| `teleflow/cli.py` | Frontera: `compose`, `drafts`, `approve` (`:119-146`, `:209-221`) |
| `review-ui/src/api.js` · `review-ui/src/App.jsx` | Frontera: cliente y pantalla de revision (ver Enfoque); modulo propio en `spec/features/base-review-ui/` |
| `review-ui/nginx.conf.template` | Frontera: cierra la cadena de timeouts en 720 s (`seguridad.md:95-97`) |
| `docker-compose.yml` · `.env.example` · `helm/teleflow/values.yaml` · `helm/teleflow/templates/_helpers.tpl` | Configuracion: `LLM_*` en el ancla comun (`docker-compose.yml:15-18`), servicio sin puertos (`docker-compose.yml:117-125`); ejemplo con `stub` (`.env.example:26-37`); `LLM_PROVIDER: stub` y 1 replica (`helm/teleflow/values.yaml:26-28`, `:92-95`); `LLM_API_KEY` por `secretKeyRef` (`helm/teleflow/templates/_helpers.tpl:272-276`) |
| `tests/test_composer.py` | Tests del modulo (ver Tests) |

## Reutiliza

Lo que una feature que toque el composer (o el futuro asistente) ya tiene resuelto:

- `_post_json` — POST JSON con reintento solo de lo transitorio, `retry-after`, `ReadTimeout`
  sin reintento y cuerpo de error truncado (`teleflow/composer_service/providers.py:191-254`).
  Sirve para cualquier llamada a un proveedor, no solo para generar `.tflow`.
- `_texto_o_error` — "un 200 no es un exito" para texto truncado o vacio
  (`teleflow/composer_service/providers.py:257-266`).
- Las tres excepciones y su mapeo a `422`/`500`/`502`
  (`teleflow/composer_service/providers.py:151-168`, `teleflow/composer_service/main.py:71-83`).
- `get_provider` + validacion en `lifespan`: patron de "configuracion imposible no arranca"
  (`teleflow/composer_service/providers.py:418-447`, `teleflow/composer_service/main.py:37-47`).
- `_validate_source`, con el estado `parses: None` para "no se pudo verificar"
  (`teleflow/composer_service/main.py:108-135`).
- `_draft_out` — contrato unico de borrador que ya consumen pantalla y CLI
  (`teleflow/composer_service/main.py:279-301`).
- Maquina de estados `pending → approved | rejected` con historial en `comments`
  (`teleflow/composer_service/main.py:169-170`, `:209-210`, `:253-254`).
- `teleflow/common/retry.py` — `is_retryable_status`, `is_retryable_transport_error`,
  `full_jitter_delay` (`:26-48`).
- Gateway: `_proxy(..., timeout=)` (`teleflow/gateway/main.py:409-433`) y
  `auth.require_por_metodo` (`teleflow/gateway/main.py:793-798`) para cualquier cambio de scope.
- `review-ui/src/diff.js` (`lineDiff`) para mostrar diffs; ya lo usa la revision
  (`2026-08-27-correccion-del-borrador-en-la-revision.md:57-58`).
- Dobles de test en `tests/test_composer.py`: `_RespuestaHTTP` / `_ClienteSecuencia` /
  `_proveedor_responde` (`:97-139`), `_settings_llm` con esperas en 0 (`:142-148`),
  `_FakeClient` / `_parser_responde` (`:269-295`), `_FakeSession` (`:336-346`),
  `_SesionConBorrador` / `_borrador` / `_editar` (`:434-464`). Los de aprobar y rechazar
  necesitarian ademas un doble del deploy: hoy `_FakeClient.post` no recibe `headers`
  (`tests/test_composer.py:284`) y `approve` los manda (`teleflow/composer_service/main.py:174-176`).
- Fixture `client` con scopes del gateway (`tests/test_gateway_scopes.py:21-22`) y sink de
  auditoria (`tests/test_auditoria.py:25-26`) para probar el scope de approve.

## Migraciones

Alembic: **no** en esta carpeta (as-built, no cambia codigo). Tabla propia: `flow_drafts`.

| Tabla.columna | Creada en | Quien la escribe / lee |
|---|---|---|
| `flow_drafts.id`, `.name` (`String(200)`, indice), `.description`, `.source`, `.base_source`, `.status` (indice, default `pending`), `.comments` (JSONB, `[]`), `.created_at`, `.updated_at` | `alembic/versions/0001_initial.py:114-126` (ORM `teleflow/common/models.py:174-207`) | Escribe `compose`, `approve`, `reject`, `edit` (`teleflow/composer_service/main.py:97-101`, `:187-192`, `:211-215`, `:265-273`); lee `_draft_out`. `updated_at` se actualiza por `onupdate` (`teleflow/common/models.py:205-207`) y no se expone (`spec.md:143-145`) |
| `flow_drafts.provider`, `.validation` (JSONB) | `alembic/versions/0003_draft_validation.py:17-27` | `compose` y `edit` (`teleflow/composer_service/main.py:99`, `:269`); los muestra la pantalla (`review-ui/src/App.jsx:238`, `:266-267`) |
| `flow_drafts.source_generado` | `alembic/versions/0007_fuente_generada_del_borrador.py:16-27` | Solo la primera edicion (`teleflow/composer_service/main.py:265-266`); deriva `editado` (`:294`) y el diff contra modelo (`review-ui/src/App.jsx:278-280`) |
| `flow_definitions`, `flow_latest` (indirecto) | `alembic/versions/0001_initial.py:18-36` | Los escribe el registry cuando la aprobacion despliega por el gateway (`teleflow/gateway/main.py:632-641`) |
| `audit_log` (indirecto) | `alembic/versions/0004_audit_log.py:18` | El gateway registra `POST /compose`, `approve`, `reject` y `PATCH source`; el deploy queda a nombre de `bootstrap (env)` (`seguridad.md:109`) |

Compatibilidad hacia atras: `0003` y `0007` agregan columnas nullable sin backfill, asi que un
pod con la imagen anterior sigue leyendo y escribiendo la tabla durante un upgrade
`(inferencia: el ORM viejo no mapea las columnas nuevas y el INSERT las deja en null)`. El
downgrade de ambas borra datos (`seguridad.md:123`). Una columna nueva deberia seguir el mismo
patron (`spec.md:410-412`); la siguiente migracion seria `0008` (`spec/constitution/tech_stack.md:56-58`).

## Tests

Existentes, por archivo. La lista de criterios `(sin test)` esta en `spec.md:165-389`; no se
repite aca.

- Unitarios:
  - `tests/test_composer.py` — **34 funciones** (busqueda `def test_`: 34 coincidencias;
    `spec.md:435` dice 36), cinco parametrizadas (`:37`, `:48`, `:80`, `:87`, `:192`):
    - seleccion de proveedor y arranque (`:38-93`, `:382-401`, `:406-424`);
    - reintentos y clasificacion (`:151-201`), respuestas 200 inservibles (`:203-233`),
      `max_tokens` en OpenAI (`:235-253`), timeout de lectura (`:604-619`);
    - validacion contra el parser (`:298-333`) y `compose` completo con stub (`:349-377`);
    - edicion de la fuente, ocho casos `test_editar_*` y `test_la_segunda_edicion_*` (`:467-572`);
    - `test_la_cadena_de_timeouts_es_estrictamente_creciente` (`:622`), que lee el primer
      `timeout=` del archivo y no el de Ollama (`spec.md:462-468`).
    - Sin tests de `approve_draft`, `reject_draft`, `list_drafts`, `get_draft` ni del mapeo HTTP
      de `compose` (`spec.md:75-81`).
  - `tests/test_gateway_scopes.py` — `(indirecto)`
    `test_sin_config_la_key_global_conserva_todos_los_permisos` (`:100`), que incluye `/drafts`
    (`:104`). Ningun test fija el scope de `approve` ni el de `PATCH source`.
  - `tests/test_auditoria.py` — `(indirecto)` `test_todo_scope_esta_clasificado` (`:206`),
    `test_toda_ruta_con_scope_de_escritura_pasa_por_el_marcador` (`:225`).
  - `tests/test_openapi_contract.py` — `(indirecto)` `test_los_operation_id_son_unicos` (`:37`),
    `test_toda_ruta_esta_agrupada_en_una_familia_conocida` (`:50`, familia `composer` en `:16`).
  - `tests/test_adapters.py` — `(indirecto)` `test_rest_status_transitorio_es_retryable`
    (`:172`): mismo criterio de status que usa `_post_json`.
  - `tests/test_parser.py` — `(indirecto)` `test_un_identificador_con_tilde_no_parsea` (`:265`):
    fija una regla que el prompt describe, no el ejemplo del prompt.
- e2e (`-m e2e`): **ninguno**. Busqueda de `compose|drafts|composer` en `tests/e2e/`: solo
  menciones a `docker compose` en docstrings.
- Playwright (requiere el stack, `(indirecto)`): `review-ui/tests/revision.spec.js` — aprobar
  despliega (`:71`), rechazar no despliega (`:89`), proveedor y estado (`:103`), tres estados
  (`:145`), aprobar lo que no compila pide confirmacion (`:167`), guardar revalida en los dos
  sentidos (`:239`), cambios sin guardar (`:259`, `:275`), diff contra modelo (`:294`), marca de
  corregido (`:314`).
- CLI: sin tests de `compose`, `drafts` ni `approve` (busqueda de `teleflow.cli` en `tests/`:
  sin coincidencias).

## Riesgos

Limites conscientes y huecos observados. Los que ya documentaron `spec.md` ("No entra" y
"Discrepancias") y `seguridad.md` ("Huecos") se **referencian**; el detalle esta alla.

| Riesgo | Mitigacion |
|---|---|
| **Huecos funcionales ya documentados** en `spec.md` "No entra": aprobar y rechazar sin test Python (`:75-81`), identidad del actor (`:82-92`), scope de la aprobacion (`:93-101`), sin limites de tamaño (`:102-106`), `name` sin validar (`:107-110`), prompt injection (`:111-120`), tool-use y conversacion (`:121-126`), reproducibilidad (`:127-129`), concurrencia (`:130-136`), fallos de transporte al aprobar (`:137-142`), historial sin fecha (`:143-145`), paginacion y borrado (`:146-148`), sin metricas propias (`:149-153`), CLI incompleto (`:154-155`). | Ninguna tecnica. Varios son decisiones: ver candidatos a ADR. |
| **Huecos de seguridad ya documentados** en `seguridad.md`: alta — aprobar despliega con `compose:write` y key de bootstrap (`:106`); alta — prompt injection hacia `${env.*}` (`:107`); media — datos personales a proveedor externo (`:108`), actor real perdido (`:109`), `name` interpolado en la URL del deploy (`:110`), composer sin auth en la red interna (`:111`), sin limites de entrada (`:112`), DoS economico (`:113`), pool del gateway (`:114`), `LLM_API_KEY` en todos los servicios (`:115`), sin retencion (`:116`); bajas (`:117-123`). | Parcial: scopes, rate limit por key, auditoria y re-validacion en el deploy (`seguridad.md:46-100`). La direccion esta en cada fila de `seguridad.md`. |
| **Discrepancias doc ↔ codigo ya documentadas** (`spec.md:443-485`): ADR-003 con fallback retirado, ADR de correccion desactualizado, test de timeouts que mide otro proveedor, `LLM_MAX_TOKENS`/`LLM_RETRY_*`/`COMPOSE_TIMEOUT` que no llegan al contenedor, docstring incompleto, proveedor del `lifespan` descartado. | Ninguna. Enmendar los dos ADRs (ver Enfoque). |
| **Errores de transporte clasificados todos como transitorios.** `_post_json` trata cualquier `httpx.HTTPError` distinto de `ReadTimeout` como red y reintenta (`teleflow/composer_service/providers.py:222-223`); no importa `is_retryable_transport_error` (`teleflow/composer_service/providers.py:16`), que existe justamente para no gastar reintentos en `UnsupportedProtocol`/`InvalidURL` (`teleflow/common/retry.py:14-23`, `:31-38`). `get_provider` no valida `LLM_BASE_URL` al arrancar (`teleflow/composer_service/providers.py:418-447`). `(inferencia)`: un `LLM_BASE_URL` sin esquema consume 3 intentos y sale como `502` "Proveedor LLM no disponible" en vez de `500` "mal configurado", con el servicio arriba. Aparta al codigo de la decision 4 del ADR de fallos explicitos. Sin test. | Ninguna. |
| **La aprobacion empata timeouts con el gateway.** El composer espera el deploy 60 s (`teleflow/composer_service/main.py:173`) y el gateway proxea `POST /drafts/{rest}` con el timeout del cliente, 60 s (`teleflow/gateway/main.py:51`, `:426-428`, `:799-800`): el empate que `teleflow/common/config.py:54-57` describe como el que tapa el error real. El deploy del otro lado encadena parse y register, cada uno con hasta 60 s (`teleflow/gateway/main.py:399-406`). `(inferencia)`: con un deploy lento el revisor recibe `502 Servicio no disponible` mientras el composer termina y marca `approved`, o levanta `ReadTimeout` sin manejar con el flow ya registrado. `test_la_cadena_de_timeouts_es_estrictamente_creciente` solo cubre `/compose` (`tests/test_composer.py:622-644`). | Ninguna. |
| **El ejemplo del system prompt no se contrasta con la gramatica.** `DSL_SYSTEM_PROMPT` presenta un "EJEMPLO COMPLETO Y VÁLIDO" (`teleflow/composer_service/providers.py:35-136`) y ningun test lo parsea (busqueda de `DSL_SYSTEM_PROMPT` fuera de `.venv`: solo `providers.py` y `spec.md`). Un cambio de `teleflow/dsl/teleflow.lark` puede dejar al prompt enseñando sintaxis invalida sin nada en rojo; la unica señal es que los borradores empiezan a salir `parses: false`. Que el ejemplo compile hoy no se ejecuto. Complementa `spec.md:404-407`. | Ninguna. |
| **¿Asume un solo proceso?** El estado en memoria, no: el proveedor se construye por request (`teleflow/composer_service/main.py:64`), `Settings` es inmutable y cacheada por proceso (`teleflow/common/config.py:96-98`) y el `lifespan` solo valida (`:43`), asi que N replicas son equivalentes. **La carrera de la aprobacion, en cambio, ni siquiera necesita replicas**: el chequeo de `pending` (`teleflow/composer_service/main.py:166-170`) y el commit (`:192`) tienen en el medio un `await` al gateway (`:173-179`), y dos requests en el mismo event loop pueden pasar los dos el chequeo `(inferencia, no ejecutado)`. `replicas: 1` (`helm/teleflow/values.yaml:92-95`) no la evita y nada fija ese 1: a diferencia de `metrics-service` (`helm/teleflow/values.yaml:96-100`) no hay comentario ni test. `deployments.yaml` no declara `strategy` (busqueda en `helm/teleflow/templates/`), asi que durante un `helm upgrade` conviven pod viejo y nuevo `(inferencia: default RollingUpdate de Kubernetes)`. Complementa `spec.md:130-136` y `seguridad.md:120`. | Ninguna. Sin `with_for_update` en el composer (`seguridad.md:120`). |
| **Fallas silenciosas: degradaciones sin señal.** Tres estados degradados quedan solo en logs: parser caido → borradores `parses: None` con `log.error` (`teleflow/composer_service/main.py:128`); credencial rotada o modelo retirado en runtime → `500` por request con `/ready` en `200`, porque la readiness solo mira la base (`teleflow/composer_service/main.py:51`, `:79`); reintentos contra el proveedor (`teleflow/composer_service/providers.py:250-251`). El composer no define metricas propias (`spec.md:149-153`) y las alertas del chart son `up == 0` y las de metricas de negocio (`helm/teleflow/alerts/alerts.yml:21-25`, `:40`, `:63`). Es el patron #14: degradar sin publicar la señal (`wiki/Knowledge/concepts/fallas-silenciosas.md:80-88`). | Parcial: el borrador y el HTTP dicen la verdad al usuario; nadie mas se entera. |
| **Fallas silenciosas: excepciones que saltan el registro.** En `approve`, un gateway caido o un cuerpo de error no JSON salen como excepcion no manejada (`teleflow/composer_service/main.py:173-179`, `:184`); el middleware de metricas registra despues de `call_next` (`teleflow/common/observability.py:33-44`), asi que esa falla no quedaria contada en `teleflow_http_requests_total` `(inferencia por el patron #6, fallas-silenciosas.md:69-73; no ejecutado)`. Si el deploy da `201` y el commit falla, el flow queda registrado y el borrador `pending`; reaprobar con la misma version choca con la inmutabilidad del registry y el revisor lee "El deploy falló" sobre algo que se desplego `(inferencia)`. | Ninguna. |
| **Fallas silenciosas: las guardas de aprobacion viven en la pantalla.** "No compila / no se pudo verificar, ¿aprobar igual?" y "cambios sin guardar" son `confirm()` del navegador (`review-ui/src/App.jsx:148-159`); el servidor aprueba sin mirar `validation` (`teleflow/composer_service/main.py:163-195`) y `tflow approve` no pregunta nada (`teleflow/cli.py:139-146`). Un borrador que no compila igual no llega al registro porque el gateway re-valida (`seguridad.md:78-80`), pero `parses: None` y "compila y hace lo inverso" (`2026-08-27-correccion-del-borrador-en-la-revision.md:31-34`) pasan sin friccion por cualquier cliente que no sea la pantalla. | Parcial: re-validacion del gateway. |
| **Interfaz conversacional: contrato de un turno.** `generate(prompt) -> str` (`teleflow/composer_service/providers.py:171-177`), fijado por ADR-003 (`2026-06-30-adr-003-llm-configurable.md:19-21`); cada proveedor arma `messages` con un unico `user` (`teleflow/composer_service/providers.py:286`, `:320-323`, `:355-358`) y el unico consumidor es `compose` (`teleflow/composer_service/main.py:72`). El asistente con `@capacidades` (`AGENTS.md:15-17`) necesita historial, herramientas y seleccion de capacidad; su carpeta no existe (`spec.md:121-126`). | Ninguna. Cambiar la firma exige enmendar ADR-003. |
| **Interfaz conversacional: una respuesta con herramientas se leeria como fallo.** Anthropic solo toma bloques `type == "text"` (`teleflow/composer_service/providers.py:298`), OpenAI solo `message.content` (`:332`), y texto vacio es `LLMRequestRejected` "Probá reformular" (`:263-265`). `(inferencia, formato de terceros no verificado en el repo)`: un turno que pide ejecutar una herramienta, sin texto, terminaria en `422` al usuario. | Ninguna. |
| **Interfaz conversacional: la salida se asume `.tflow`.** Un solo system prompt, constante y repetido en tres payloads, que ordena responder "SOLO con el contenido del archivo" (`teleflow/composer_service/providers.py:20`, `:285`, `:321`, `:356`); `compose` recorta fences y valida contra el parser como si todo fuera DSL (`teleflow/composer_service/main.py:86-95`). No hay forma de elegir prompt por capacidad. | Ninguna. `_post_json`, las excepciones y `_texto_o_error` si son reutilizables (ver Reutiliza). |
| **Interfaz conversacional: sin streaming ni lugar para la conversacion.** Ningun proveedor pide streaming (Ollama con `"stream": False`, `teleflow/composer_service/providers.py:353`) y `_proxy` devuelve el cuerpo completo (`teleflow/gateway/main.py:432-433`): turnos bloqueantes de hasta 600 s (`teleflow/common/config.py:49-58`), que ademas retienen conexiones del pool (`seguridad.md:114`). No hay tabla para turnos; `comments` es la traza humana y el ADR ya rechazo mezclarle registros de maquina (`2026-07-25-composer-llm-fallos-explicitos.md:122-124`). Persistir conversaciones pide tabla nueva y `0008` compatible hacia atras. | Ninguna. |
| **Interfaz conversacional: aprobacion con key de servicio como patron a no copiar.** La aprobacion despliega con `TELEFLOW_API_KEY` (`teleflow/composer_service/main.py:176`, scopes `*` por default `teleflow/common/config.py:23`) y `_proxy` no propaga la identidad de quien pide (`teleflow/gateway/main.py:412-418`). `(inferencia)`: un asistente que ejecute `@capacidades` (desplegar, disparar, firmar) con este mismo patron actuaria con todos los scopes en nombre de cualquier usuario, y el hueco alto de `seguridad.md:106-107` pasaria de "un borrador inducido puede desplegarse" a "una conversacion inducida puede operar". Ver `spec/features/base-gateway-y-acceso/seguridad.md:189-190`. | Ninguna. Decision previa a cualquier capacidad que escriba. |
| **Interfaz conversacional: lo reutilizable esta en el servidor, no en la pantalla.** La revision y la correccion son pantallas (`2026-08-27-correccion-del-borrador-en-la-revision.md:67-79`) y la direccion vigente no propone pantallas nuevas (`AGENTS.md:17`). La maquina de estados, la revalidacion y `source_generado` estan en el composer y un asistente las hereda; las confirmaciones de aprobacion no (fila de guardas en la pantalla). | Parcial: el contrato `_draft_out` es independiente del cliente. |

**Candidatos a ADR** (una linea cada uno; no se escriben aca):

- **Enmienda de ADR-003: contrato del proveedor para conversacion y tool-use (mensajes, herramientas, streaming, prompt por capacidad)** — hoy `generate(prompt)->str` (`teleflow/composer_service/providers.py:171-177`); en la misma enmienda, marcar como reemplazado el fallback al stub (`spec.md:447-451`).
- **Identidad delegada entre servicios: el composer (y el asistente) actua con la identidad de quien pide, no con la key de bootstrap** — `teleflow/composer_service/main.py:176`, `teleflow/gateway/main.py:412-418`, `seguridad.md:106`, `:109`.
- **Scope de la aprobacion de borradores y separacion entre quien compone y quien aprueba** — `teleflow/gateway/main.py:795-798` frente a la decision 5 de `2026-08-27-correccion-del-borrador-en-la-revision.md:77-78`.
- **Donde se hacen cumplir las guardas de aprobacion (no compila, sin verificar, fuente no guardada): servidor o cliente** — `review-ui/src/App.jsx:148-159`, `teleflow/composer_service/main.py:163-195`.
- **Concurrencia sobre un borrador: bloqueo de fila o version optimista en approve/edit** — `teleflow/composer_service/main.py:166-192`, `:250-273`.
- **Datos hacia proveedores LLM externos y retencion de `flow_drafts`** — `seguridad.md:108`, `:116`.
- **Limites y presupuesto del composer: tamaño de entrada, cuota por `/compose`, concurrencia y cadena de timeouts incluida la aprobacion** — `seguridad.md:112-114`, `teleflow/composer_service/main.py:173`.
- **Persistencia de conversaciones del asistente: tabla propia, retencion y relacion con `flow_drafts`** — `2026-07-25-composer-llm-fallos-explicitos.md:122-124`.
- **Señales de degradacion del composer (parser caido, proveedor mal configurado en runtime, reintentos) y sus alertas** — `teleflow/composer_service/main.py:51`, `:128`, `helm/teleflow/alerts/alerts.yml:21-25`.
- **Enmienda del ADR de correccion del borrador: validacion via `PATCH /drafts/{id}/source` y `base_source` ya enviado por el formulario** — `spec.md:452-461`.

## Verificacion

Que la linea base sigue describiendo el codigo. Desde la raiz del repo, con el venv activo.

```
mypy .
pytest -m "not e2e" -q
pytest tests/test_composer.py -q
pytest tests/test_gateway_scopes.py tests/test_auditoria.py tests/test_openapi_contract.py tests/test_adapters.py -q
```

Contra el stack (compose levantado con `LLM_PROVIDER=stub`, key de desarrollo o
`TELEFLOW_API_KEY` definida):

```
docker compose up --build -d
pytest -m e2e -q
cd review-ui && npm ci && npm run test:install && npx playwright test tests/revision.spec.js
tflow compose alta_socio --description "alta de socio"
tflow drafts
tflow approve <draft_id> --version 1.0.0
```

`pytest -m e2e` no ejercita el composer (no hay e2e Python del modulo): lo que prueba aprobar y
rechazar por la API real es `review-ui/tests/revision.spec.js`. Con el stub, `tflow compose`
imprime un esqueleto con el pedido comentado (`teleflow/composer_service/providers.py:385-408`) y
`tflow approve` sale con codigo 1 si el composer responde `>= 400` (`teleflow/cli.py:144-145`,
`teleflow/cli.py:44-49`).
