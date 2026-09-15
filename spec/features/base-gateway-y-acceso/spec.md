---
project: copp-ia
type: spec
status: implementada
feature: base-gateway-y-acceso
provenance: copp-ia@devyos@4c44b4c
created: 2026-09-14
---

<!-- Linea base as-built: documenta lo que el codigo hace hoy. Nunca se sincroniza con Jira. -->
<!-- Lo escribe el subagente `analista-requisitos` (modo as-built). Ante conflicto, manda el codigo. -->


# Linea base — gateway y acceso (auth por API key, scopes, rate limit, auditoria, proxy, CLI)

## Que resuelve

Un organismo expone su plataforma a operadores, a la review-ui y a integraciones de terceros
por **un unico punto de entrada** (`teleflow/gateway/main.py:1-8`). Ese punto tiene que saber
quien es cada request, decidir si esa credencial puede hacer esa accion concreta, frenar el
abuso aunque el gateway corra con varias replicas, dejar constancia consultable de lo que se
hizo y de lo que se intento sin permiso, y reenviar a los servicios internos sin dejar pasar
nada del exterior.

Lo resuelve hoy asi (comprobado leyendo el codigo en `copp-ia@devyos@4c44b4c`; el working tree
solo tiene carpetas `spec/` sin trackear, asi que el codigo leido es el del commit):

- **Autenticacion por header `X-TeleFlow-API-Key`** en un middleware que corre antes de toda
  ruta no publica (`teleflow/gateway/main.py:145-163`). Dos origenes de identidad: la key de
  bootstrap de la variable de entorno, resuelta sin tocar la base
  (`teleflow/gateway/main.py:344-354`), y las keys de la tabla `api_keys`, buscadas por hash
  SHA-256 con cache local con TTL (`teleflow/gateway/main.py:356-381`,
  `teleflow/gateway/auth.py:95-109`).
- **Autorizacion por scope en cada ruta**, no por key: 12 scopes mas el comodin `*`
  (`teleflow/gateway/auth.py:29-51`), exigidos con `Depends(auth.require(...))` o
  `require_por_metodo` (`teleflow/gateway/auth.py:118-144`).
- **Gestion de credenciales** por API: crear, listar, revocar y rotar, con el secreto mostrado
  una sola vez y la revocacion propagada a todas las replicas por Redis pub/sub
  (`teleflow/gateway/main.py:271-335`, `teleflow/gateway/main.py:486-593`).
- **Rate limit compartido** entre replicas en Redis, con degradacion visible a un bucket por
  proceso (`teleflow/gateway/main.py:103-142`).
- **Auditoria persistida** en `audit_log` de toda escritura, de la lectura de la auditoria y de
  todo 401/403/429/500, clasificada por el scope que exigio la ruta
  (`teleflow/gateway/main.py:166-248`, `teleflow/gateway/auth.py:147-195`), y consultable con
  `GET /audit` (`teleflow/gateway/main.py:436-481`).
- **Proxy hacia los servicios internos** que arma los headers desde cero y traduce un upstream
  caido a 502 (`teleflow/gateway/main.py:384-433`).
- **Deploy de flows** en dos saltos: parser-service valida, registry-service persiste
  (`teleflow/gateway/main.py:596-652`).
- **Contrato OpenAPI** con `operation_id` y `tags` explicitos en cada ruta y el esquema de auth
  declarado (`teleflow/gateway/main.py:73-78`), exportable sin stack con `tflow openapi`
  (`teleflow/cli.py:149-162`).
- **CLI `tflow`** como cliente de linea de comandos del gateway (`teleflow/cli.py:1-18`,
  `pyproject.toml:47-48`).

### Catalogo de rutas y scopes: insumo del asistente conversacional

La direccion de producto vigente reemplaza las pantallas por un asistente conversacional con
`@capacidades` (`AGENTS.md:15-17`), cuyas capacidades se generan del OpenAPI del gateway
(direccion comunicada por el owner; la carpeta `spec/features/asistente-conversacional/` no
existe en este commit). **El catalogo de rutas, `operation_id` y scopes de este modulo es ese
insumo**: cada `operation_id` es el nombre estable de una capacidad y cada scope es el permiso
que la habilita. Lo que el OpenAPI generado hoy **no** trae (scopes, cuerpos y codigos reales de
las rutas proxeadas) esta en "No entra".

| Metodo y ruta | `operation_id` | Tag | Scope | Se audita con exito | Destino | Fuente |
|---|---|---|---|---|---|---|
| `GET /audit` | `listar_auditoria` | audit | `audit:read` | si | tabla `audit_log` | `teleflow/gateway/main.py:438-481` |
| `POST /keys` | `crear_key` | keys | `keys:admin` | si | tabla `api_keys` | `teleflow/gateway/main.py:491-519` |
| `DELETE /keys/{key_id}` | `revocar_key` | keys | `keys:admin` | si | `api_keys` + pub/sub | `teleflow/gateway/main.py:522-542` |
| `POST /keys/{key_id}/rotate` | `rotar_key` | keys | `keys:admin` | si | `api_keys` + pub/sub | `teleflow/gateway/main.py:545-576` |
| `GET /keys` | `listar_keys` | keys | `keys:admin` | si (`keys:admin` es de escritura) | `api_keys` | `teleflow/gateway/main.py:579-593` |
| `POST /flows/{name}` | `desplegar_flow` | flows | `flows:deploy` | si | parser → registry | `teleflow/gateway/main.py:604-652` |
| `POST /parse` | `validar_flow` | flows | `flows:read` | no | parser | `teleflow/gateway/main.py:655-659` |
| `GET /flows` | `listar_flows` | flows | `flows:read` | no | registry | `teleflow/gateway/main.py:664-667` |
| `GET /flows/{name}` | `listar_versiones_flow` | flows | `flows:read` | no | registry | `teleflow/gateway/main.py:670-673` |
| `GET /flows/{name}/{version}` | `obtener_version_flow` | flows | `flows:read` | no | registry | `teleflow/gateway/main.py:676-681` |
| `POST /execute` | `ejecutar_flow` | instances | `instances:trigger` | si | executor | `teleflow/gateway/main.py:686-696` |
| `GET /instances` | `listar_instancias` | instances | `instances:read` | no | executor | `teleflow/gateway/main.py:699-702` |
| `GET /instances/{instance_id}` | `obtener_instancia` | instances | `instances:read` | no | executor | `teleflow/gateway/main.py:705-710` |
| `POST /instances/{instance_id}/signal` | `enviar_signal` | instances | `instances:signal` | si | executor | `teleflow/gateway/main.py:713-718` |
| `POST /instances/{instance_id}/retry` | `reintentar_instancia` | instances | `instances:retry` | si | executor | `teleflow/gateway/main.py:721-726` |
| `GET /entities/{rest:path}` | `consultar_entities` | entities | `entities:read` | no | executor | `teleflow/gateway/main.py:729-746` |
| `POST /entities/{rest:path}` | `crear_entity` | entities | `entities:write` | si | executor | `teleflow/gateway/main.py:729-746` |
| `PATCH /entities/{rest:path}` | `actualizar_entity` | entities | `entities:write` | si | executor | `teleflow/gateway/main.py:729-746` |
| `GET /domain` | `consultar_dominio` | entities | `entities:read` | no | executor | `teleflow/gateway/main.py:749-757` |
| `GET /relations/{rest:path}` | `consultar_relations` | entities | `entities:read` | no | executor | `teleflow/gateway/main.py:760-770` |
| `POST /relations/{rest:path}` | `crear_relation` | entities | `entities:write` | si | executor | `teleflow/gateway/main.py:760-770` |
| `PATCH /relations/{rest:path}` | `actualizar_relation` | entities | `entities:write` | si | executor | `teleflow/gateway/main.py:760-770` |
| `POST /compose` | `componer_draft` | composer | `compose:write` | si | composer (timeout 660 s) | `teleflow/gateway/main.py:775-781` |
| `GET /drafts` | `listar_drafts` | composer | `compose:read` | no | composer | `teleflow/gateway/main.py:784-788` |
| `GET /drafts/{rest:path}` | `obtener_draft` | composer | `compose:read` | no | composer | `teleflow/gateway/main.py:791-800` |
| `POST /drafts/{rest:path}` | `operar_draft` | composer | `compose:write` | si | composer | `teleflow/gateway/main.py:791-800` |
| `PATCH /drafts/{draft_id}/source` | `editar_draft` | composer | `flows:deploy` | si | composer | `teleflow/gateway/main.py:803-816` |

27 operaciones. Publicas, sin `operation_id` ni scope: `/health`, `/ready`, `/metrics`, `/docs`,
`/openapi.json`, `/redoc` (`teleflow/gateway/main.py:39`). La columna "se audita" sale de
`SCOPES_AUDITADOS` (`teleflow/gateway/auth.py:155-170`); un 401/403/429/500 se audita en
cualquier ruta no publica (`teleflow/gateway/main.py:184-207`). La lista de `operation_id`
coincide una a una con `docs/openapi.json:15-1125` (comparada a mano, no por test).

## Objetivo

Que ningun request llegue a un servicio interno sin una credencial valida con el scope de esa
ruta, que toda escritura y todo intento denegado quede registrado con su resultado, y que la
revocacion de una credencial y el rate limit valgan en todas las replicas del gateway.

## Alcance

**Entra:**

- `teleflow/gateway/main.py` — middlewares de auth/rate limit y de auditoria, resolucion de
  identidad y cache, revocacion por pub/sub, `GET /audit`, rutas de keys, deploy, proxies y
  contrato OpenAPI.
- `teleflow/gateway/auth.py` — catalogo de scopes, `parse_scopes`, `Identidad`, `generar_key`,
  `hash_key`, `resolver_key`, `require`, `require_por_metodo`, clasificacion de scopes para
  auditoria y `detallar`.
- Configuracion que el modulo lee: `teleflow_api_key`, `teleflow_api_key_scopes`,
  `api_key_cache_ttl`, URLs internas, `compose_timeout` y `rate_limit_rpm`
  (`teleflow/common/config.py:17-33`, `teleflow/common/config.py:58`,
  `teleflow/common/config.py:92-93`).
- Tablas `api_keys` (`alembic/versions/0002_api_keys.py:18-31`) y `audit_log`
  (`alembic/versions/0004_audit_log.py:18-34`); modelos en `teleflow/common/models.py:226-269`.
- Claves y canal de Redis: `ratelimit:<hash>:<minuto>` (`teleflow/gateway/main.py:127-128`) y
  `teleflow:keys:revocadas` (`teleflow/gateway/main.py:259`).
- Metricas propias: `teleflow_rate_limit_degraded_total`, `teleflow_audit_write_failures_total`,
  `teleflow_key_revocations_received_total`, `teleflow_key_revocations_unpublished_total`
  (`teleflow/gateway/main.py:109-112`, `teleflow/gateway/main.py:168-171`,
  `teleflow/gateway/main.py:261-268`).
- `/health`, `/ready` (con `db_ping`) y `/metrics` montados por
  `setup_observability` (`teleflow/gateway/main.py:81`, `teleflow/common/observability.py:28-64`).
- Anexo clientes: `teleflow/cli.py` (`tflow`) y el artefacto `docs/openapi.json` que genera.

**No entra (y por que):**

Lo de severidad de seguridad esta analizado en `seguridad.md` de esta carpeta; aca se nombra y se
referencia, no se repite.

- **Key de bootstrap con default publico `dev-key-change-me` y scopes `*`.** Confirmado:
  `teleflow/common/config.py:18` y `teleflow/common/config.py:23`; `.env.example:4` y
  `.env.example:9` repiten los defaults. Es **decision fijada por test**: el default `*` existe
  para no romper instalaciones existentes (`teleflow/gateway/auth.py:7-8`,
  `tests/test_gateway_scopes.py::test_sin_config_la_key_global_conserva_todos_los_permisos`).
  La key de bootstrap no se revoca ni se rota por API: las rutas de keys solo operan filas de la
  base (`teleflow/gateway/main.py:529-531`, `teleflow/gateway/main.py:554-557`). Analisis y
  severidad: `seguridad.md:125`.
- **`/metrics`, `/docs`, `/openapi.json` y `/redoc` publicos.** Confirmado:
  `teleflow/gateway/main.py:39` y `teleflow/gateway/main.py:149-150`; tambien saltean la
  auditoria (`teleflow/gateway/main.py:184`, `teleflow/gateway/main.py:196-197`). Que `/health`
  sea publico lo fija un test (`tests/test_gateway_scopes.py::test_rutas_publicas_no_piden_scope`);
  el resto no tiene test. Motivo observado: son rutas de operacion y de contrato; que no se haya
  separado su exposicion es hueco. Severidad: `seguridad.md:126`, `seguridad.md:138`.
- **El OpenAPI no alcanza como catalogo de capacidades.** (1) Ninguna operacion declara su scope:
  el esquema `APIKeyHeader` se aplica con lista de scopes vacia a todas
  (`teleflow/gateway/main.py:75-78`, `docs/openapi.json:16-20`, `docs/openapi.json:1267-1272`) y
  el scope vive solo en la dependencia de cada ruta (`teleflow/gateway/auth.py:118-144`). (2) Las
  rutas proxeadas reciben `Request` crudo, asi que no declaran cuerpo, header `Idempotency-Key`
  ni el codigo real: `POST /execute` figura sin `requestBody` y con respuesta `200` generica
  (`docs/openapi.json:511-535`) aunque el executor responde `202`
  (`tests/e2e/test_idempotencia_e2e.py::test_el_header_llega_al_executor_y_deduplica`). Solo
  `POST /keys` y `POST /flows/{name}` tienen modelo de entrada
  (`teleflow/gateway/main.py:486-488`, `teleflow/gateway/main.py:598-601`). Motivo: el proxy es
  generico a proposito y el contrato se penso para clientes generados, no para un asistente
  `(inferencia)`. Es el primer hueco a resolver antes de generar `@capacidades`.
- **`docs/openapi.json` sin chequeo de sincronia.** Ningun test compara el archivo con
  `app.openapi()` (busqueda de `docs/openapi` y `cmd_` en `tests/`, `.github/workflows/` y
  `pyproject.toml`: sin coincidencias). Hoy coinciden los 27 `operation_id`; si una ruta cambia
  sin correr `tflow openapi`, el artefacto queda viejo en silencio.
- **`Idempotency-Key` no acotada por API key** `(frontera: executor)`. El gateway propaga solo
  el header, sin la identidad (`teleflow/gateway/main.py:694-696`); el executor busca la
  instancia por la clave sola (`teleflow/executor_service/engine.py:410-414`) y la restriccion
  `UNIQUE` es global (`alembic/versions/0005_idempotency_key.py:24-26`). Por lectura de codigo,
  no ejecutado: otra key que reuse la misma clave con el mismo pedido recibe el `instance_id` de
  la primera con `idempotent_replay: true` (`teleflow/executor_service/engine.py:423-424`), y con
  otro pedido recibe un 409 cuyo mensaje incluye el id de la instancia y el nombre del flow ajeno
  (`teleflow/executor_service/engine.py:418-420`). Sin test. No figura en `seguridad.md`: queda
  para que lo evalue `seguridad-infra`.
- **Sin limite de tamaño de body.** Confirmado: `_proxy` lee el cuerpo entero
  (`teleflow/gateway/main.py:416`), `DeployRequest.source` y `version` no tienen `max_length`
  (`teleflow/gateway/main.py:598-601`) y `CrearKeyRequest.scopes` es una lista sin tope
  (`teleflow/gateway/main.py:488`); la unica cota del modulo es `name` de la key
  (`teleflow/gateway/main.py:487`). Motivo: no se decidio un limite. Severidad: `seguridad.md:131`.
- **`audit_log.details` sin lista blanca de claves.** Confirmado: `auth.detallar` acepta
  cualquier `**datos` y los mezcla en `request.state` (`teleflow/gateway/auth.py:184-190`), y
  `detalles_de` los devuelve tal cual (`teleflow/gateway/auth.py:193-195`). Hoy el unico
  llamador es el deploy, con `version` y `checksum` (`teleflow/gateway/main.py:612`,
  `teleflow/gateway/main.py:624`). Motivo: anotado como "footgun" a resolver si el uso crece
  (`wiki/Knowledge/backlog-hardening.md:207-209`).
- **CLI sin tests y con key por defecto.** Confirmado: ningun test importa `teleflow.cli`
  (busqueda de `teleflow.cli|cmd_` en `tests/`: sin coincidencias) y `_client` usa
  `dev-key-change-me` y `http://localhost:8000` si faltan las variables (`teleflow/cli.py:30-37`).
  Motivo: el hueco de tests esta anotado y no priorizado
  (`wiki/Knowledge/backlog-hardening.md:55`, `wiki/Knowledge/backlog-hardening.md:62-63`).
  Severidad de la key por defecto: `seguridad.md:142`.
- **CLI con cobertura parcial de la API.** `tflow` no tiene comandos para keys, auditoria,
  reintento de instancias, entidades, relaciones, dominio, rechazo ni edicion de borradores
  (`teleflow/cli.py:176-225`), y `tflow execute` no manda `Idempotency-Key`
  (`teleflow/cli.py:87-96`), asi que reintentarlo tras un timeout dispara otra instancia
  `(inferencia: el executor sin clave crea una instancia por llamada,
  tests/e2e/test_idempotencia_e2e.py::test_sin_clave_cada_llamada_dispara)`. Motivo: no se
  decidio; la direccion de producto va al asistente, no a mas comandos `(inferencia)`.
- **Alertas sobre los contadores de degradacion.** `README.md:194`, `README.md:202` y los ADRs
  (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:73-74`,
  `wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:73-75`) llaman "la metrica a
  alertar" a `teleflow_rate_limit_degraded_total`, `teleflow_key_revocations_unpublished_total`
  y `teleflow_audit_write_failures_total`, pero `helm/teleflow/alerts/alerts.yml` solo define
  `TeleFlowServicioCaido`, `TeleFlowMetricasDeNegocioCongeladas` y
  `TeleFlowSinPublicadorDeMetricasDeNegocio` (`helm/teleflow/alerts/alerts.yml:21`,
  `helm/teleflow/alerts/alerts.yml:40`, `helm/teleflow/alerts/alerts.yml:63`); la busqueda de
  esos tres nombres fuera de `.venv` solo da el codigo, el README, la wiki y specs. Hueco: la
  degradacion se cuenta pero nadie la mira.
- **Requests cortados por auth o rate limit fuera de `teleflow_http_requests_total`.**
  `setup_observability` registra su middleware antes que los de auth y auditoria
  (`teleflow/gateway/main.py:81` frente a `teleflow/gateway/main.py:145` y
  `teleflow/gateway/main.py:174`) `(inferencia: Starlette envuelve en orden inverso de
  registro, asi que el middleware de metricas queda adentro y no ve los 401/429 que el de auth
  corta; no ejecutado)`. Solo quedan en `audit_log`.
- **Scope con typo en `TELEFLOW_API_KEY_SCOPES` no falla al arrancar.** `get_bootstrap_scopes`
  se evalua recien en el primer request con la key de bootstrap (`teleflow/gateway/main.py:338-354`),
  desde el middleware; `(inferencia)` la excepcion sale como 500 en ese request. Con keys de base
  el gateway sigue atendiendo. Sin test del camino completo; el parseo si esta probado
  (`tests/test_gateway_scopes.py::test_scope_con_typo_falla_en_vez_de_dar_menos_permisos`).
- **Filtros de `GET /audit` sin test.** En unitarios la sesion falsa devuelve siempre vacio
  (`tests/conftest.py:44-54`) y ningun e2e consulta `/audit` (busqueda de `/audit` en
  `tests/e2e/`: sin coincidencias). Los criterios de consulta quedan `(sin test)`.
- **Decisiones de diseño con limite consciente** (no son olvidos):
  - Lecturas exitosas no se auditan, salvo `audit:read`
    (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:41-48`,
    `tests/test_auditoria.py::test_una_lectura_exitosa_no_se_registra`).
  - No se guarda el cuerpo del request
    (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:50-65`,
    `tests/test_auditoria.py::test_el_deploy_registra_version_y_checksum_pero_no_el_source`).
  - Auditoria best-effort: si la escritura falla o el proceso muere, la accion no queda
    registrada (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:88-92`,
    `seguridad.md:130`). Sin purga automatica
    (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:100-102`).
  - Rate limit con ventana fija y degradacion al bucket del proceso si Redis falla
    (`wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:55-75`,
    `tests/test_revocacion_replicas.py::test_si_redis_falla_se_degrada_al_bucket_del_proceso`).
    Limites: `seguridad.md:135`.
  - Revocacion por pub/sub fire-and-forget con el TTL como techo
    (`wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:77-84`,
    `seguridad.md:134`). Redis no entra en `/ready`
    (`wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:109-111`).
- **Resto de huecos de seguridad del modulo**, ya analizados y no repetidos aca: path traversal
  en los proxies `{rest:path}` (`seguridad.md:121`), aprobacion de borradores con la key de
  bootstrap (`seguridad.md:122-123`, frontera composer), rate limit aplicado despues de
  autenticar (`seguridad.md:127`), `actor_id` libre del cuerpo (`seguridad.md:128`), `keys:admin`
  sin techo de scopes y keys sin vencimiento (`seguridad.md:129`), servicios internos sin auth
  propia (`seguridad.md:132`), header con bytes no ASCII → 500 (`seguridad.md:136`),
  `actor_name` suplantable (`seguridad.md:137`), `OPTIONS` sin auth (`seguridad.md:141`).
- **Semantica de lo que hay detras del proxy** (registry, executor, composer). Se usa como
  evidencia `(indirecto)` de que el proxy reenvia; se especifica en sus propias lineas base
  (p. ej. `spec/features/base-composer-ia/spec.md`).

## Criterios de aceptacion

Cada criterio nombra el test que lo comprueba. `(sin test)` = el codigo lo hace y ningun test lo
prueba. `(indirecto)` = lo prueba un test de otro modulo que pasa por el gateway. Los unitarios
corren sin Postgres ni Redis: `sink_auditoria` sustituye la sesion y Redis
(`tests/conftest.py:96-111`), y sin upstreams una ruta autorizada termina en 502
(`tests/test_gateway_scopes.py:6-7`).

### Autenticacion

- [ ] Dada una key que no es la de bootstrap ni existe en `api_keys`, cuando se pide una ruta no
  publica, entonces responde `401` (autentica antes de autorizar: no `403`) —
  `tests/test_gateway_scopes.py::test_key_invalida_sigue_dando_401_no_403`,
  `tests/e2e/test_api_keys_e2e.py::test_una_key_inexistente_da_401`. El cuerpo
  `{"detail": "API key inválida"}` (`teleflow/gateway/main.py:156`) — `(sin test)`
- [ ] Dado un request sin header `X-TeleFlow-API-Key` o con el header vacio, cuando llega a una
  ruta no publica, entonces responde `401` sin consultar la base
  (`teleflow/gateway/main.py:350-351`) — `(sin test)`
- [ ] Dado el valor de `TELEFLOW_API_KEY` en el header, cuando se autentica, entonces la
  identidad es `bootstrap (env)` con `key_id` nulo y los scopes de `TELEFLOW_API_KEY_SCOPES`
  (`teleflow/gateway/main.py:352-354`) — `tests/test_auditoria.py::test_una_escritura_queda_registrada`
  (fila con `actor_name == "bootstrap (env)"`). Que se resuelva con Postgres caido
  (`teleflow/gateway/main.py:347-349`) — `(sin test)`
- [ ] Dado `TELEFLOW_API_KEY_SCOPES` sin configurar (default `*`), cuando la key de bootstrap
  pide `GET /flows`, `/instances`, `/entities/nino/n1`, `/drafts`, `POST /execute` y
  `POST /flows/x`, entonces ninguna responde `403` —
  `tests/test_gateway_scopes.py::test_sin_config_la_key_global_conserva_todos_los_permisos`
- [ ] Dada una key creada por `POST /keys` con `instances:read` y `entities:read`, cuando pide
  `GET /instances`, entonces responde `200` —
  `tests/e2e/test_api_keys_e2e.py::test_la_key_creada_puede_leer_pero_no_desplegar`. Que ese
  uso actualice `api_keys.last_used_at` (`teleflow/gateway/main.py:365-368`) — `(sin test)`
- [ ] Dada una key de base valida ya resuelta, cuando vuelve a usarse antes de
  `API_KEY_CACHE_TTL` segundos (30 por default, `teleflow/common/config.py:26`), entonces se
  resuelve del cache sin ir a la base; una key inexistente no se cachea
  (`teleflow/gateway/main.py:357-359`, `teleflow/gateway/main.py:376-381`) — `(sin test)`
- [ ] Dada una key de base y Postgres sin responder (`SQLAlchemyError` u `OSError`), cuando se
  autentica, entonces responde `401` y no `500`, y se loguea `api_key_lookup_failed`
  (`teleflow/gateway/main.py:369-374`) — `(sin test)`
- [ ] Dado un request sin key, cuando pide una ruta publica, entonces pasa sin autenticar ni
  auditar:
  - `GET /health` responde `200` — `tests/test_gateway_scopes.py::test_rutas_publicas_no_piden_scope`,
    `tests/test_auditoria.py::test_las_rutas_publicas_no_se_auditan`
  - `/ready`, `/metrics`, `/docs`, `/openapi.json`, `/redoc` (`teleflow/gateway/main.py:39`) —
    `(sin test)`
  - cualquier ruta con metodo `OPTIONS` (`teleflow/gateway/main.py:149`) — `(sin test)`
- [ ] Dado Postgres caido, cuando se pide `GET /ready` al gateway, entonces responde `503` con
  `{"status":"not_ready"}` (`teleflow/gateway/main.py:81`,
  `teleflow/common/observability.py:50-60`) — `(sin test)`

### Scopes por ruta

- [ ] Dado el texto de configuracion de scopes, cuando se parsea, entonces `*` da los 12 scopes
  (tambien mezclado con otros), una lista separada por comas da exactamente esos, y vacio da
  ninguno — `tests/test_gateway_scopes.py::test_parse_scopes`
- [ ] Dado un scope inexistente (`flows:deply`), cuando se parsea, entonces se lanza
  `UnknownScopeError` con el nombre del scope en el mensaje —
  `tests/test_gateway_scopes.py::test_scope_con_typo_falla_en_vez_de_dar_menos_permisos`
- [ ] Dada una lista de scopes explicita sin `keys:admin`, cuando se parsea, entonces no incluye
  `keys:admin`; con `*` si lo incluye —
  `tests/test_api_keys.py::test_keys_admin_es_un_scope_mas_y_no_lo_da_una_key_comun`
- [ ] Dada una key a la que le falta el scope de la ruta, cuando la llama, entonces responde
  `403` con `detail` `la API key no tiene el scope '<scope>'` (`teleflow/gateway/auth.py:124-128`).
  Por ruta:
  - `POST /flows/{name}` sin `flows:deploy` (key con `entities:read,instances:read`) → `403` y
    `detail` contiene `flows:deploy` —
    `tests/test_gateway_scopes.py::test_key_de_solo_lectura_no_puede_desplegar`,
    `tests/e2e/test_api_keys_e2e.py::test_la_key_creada_puede_leer_pero_no_desplegar`
  - `GET /entities/nino/n1/360` con `entities:read` → no `403` —
    `tests/test_gateway_scopes.py::test_key_de_solo_lectura_si_puede_leer_la_360`
  - `/entities/...` con `entities:read`: `GET` no `403`, `POST` `403` —
    `tests/test_gateway_scopes.py::test_scope_de_lectura_no_habilita_escribir_entidades`
  - `/entities/...` con `entities:write`: `POST` y `PATCH` no `403`, `GET` `403` —
    `tests/test_gateway_scopes.py::test_scope_de_escritura_habilita_post_y_patch`
  - `/relations/...` con el mismo reparto por metodo (`teleflow/gateway/main.py:760-770`) —
    `(sin test)`
  - `GET /domain` exige `entities:read` (`teleflow/gateway/main.py:749-750`) — `(sin test)`
  - con `instances:trigger`: `POST /execute` no `403`; `POST /instances/i1/signal` y
    `/retry` `403` — `tests/test_gateway_scopes.py::test_disparar_no_habilita_firmar_ni_reintentar`;
    `POST /execute` sin `instances:trigger` → `403` —
    `tests/e2e/test_api_keys_e2e.py::test_la_key_creada_puede_leer_pero_no_desplegar`
  - `GET /flows`, `/flows/{name}`, `/flows/{name}/{version}` y `POST /parse` exigen
    `flows:read` (`teleflow/gateway/main.py:655-681`) — `(sin test)` del rechazo
  - `GET /drafts` y `GET /drafts/{...}` exigen `compose:read`; `POST /compose` y
    `POST /drafts/{...}` exigen `compose:write` (`teleflow/gateway/main.py:775-800`) —
    `(sin test)` del rechazo
  - `PATCH /drafts/{id}/source` exige `flows:deploy` y no `compose:write`
    (`teleflow/gateway/main.py:803-816`) — `(sin test)`
  - `POST /keys` sin `keys:admin` → `403` con `keys:admin` en `detail` —
    `tests/e2e/test_api_keys_e2e.py::test_la_key_creada_no_puede_crear_otras_keys`;
    `DELETE /keys/{id}` y `POST /keys/{id}/rotate` → `403` —
    `tests/e2e/test_api_keys_e2e.py::test_una_key_comun_no_puede_revocar_ni_rotar`;
    `GET /keys` — `(sin test)` del rechazo
  - `GET /audit` con `keys:admin,flows:deploy,entities:write` → `403` con `audit:read` en
    `detail` — `tests/test_auditoria.py::test_leer_la_auditoria_exige_su_propio_scope`

### Gestion de keys

- [ ] Dada una key con `keys:admin`, cuando hace `POST /keys` con `name` y `scopes` validos,
  entonces responde `201` con `id`, `name`, `scopes` ordenados, `key` que empieza con `tf_` y
  `aviso`, y en la base queda solo el hash —
  `tests/e2e/test_api_keys_e2e.py::test_la_key_creada_puede_leer_pero_no_desplegar` (fixture
  `key_de_solo_lectura`, `tests/e2e/test_api_keys_e2e.py:17-26`)
- [ ] Dadas dos llamadas a `generar_key`, cuando se comparan, entonces son distintas, empiezan
  con `tf_` y miden mas de 40 caracteres; y `hash_key` es determinista, de 64 hex, no contiene el
  secreto y cambia con cualquier caracter —
  `tests/test_api_keys.py::test_la_key_generada_es_aleatoria_y_no_adivinable`,
  `tests/test_api_keys.py::test_hash_estable_y_la_key_no_se_puede_recuperar`
- [ ] Dado un `POST /keys` con cualquiera de estos errores, cuando se procesa, entonces no se crea
  la key:
  - un scope desconocido → `422` con el mensaje de `UnknownScopeError`
    (`teleflow/gateway/main.py:495-498`) — `(sin test)`
  - un `name` ya usado → `409` `ya existe una key '<name>'` (`teleflow/gateway/main.py:508-510`) —
    `(sin test)`
  - `name` vacio o de mas de 200 caracteres → `422` de validacion
    (`teleflow/gateway/main.py:487`) — `(sin test)`
- [ ] Dadas keys creadas, cuando se pide `GET /keys` con `keys:admin`, entonces responde `200`,
  el cuerpo no contiene el secreto ni la palabra `key_hash`, y la key aparece con sus scopes —
  `tests/e2e/test_api_keys_e2e.py::test_el_secreto_no_se_puede_volver_a_ver`. Orden por
  `created_at` y campos `id, name, scopes, active, created_at, last_used_at`
  (`teleflow/gateway/main.py:584-593`) — `(sin test)`
- [ ] Dada una key activa en uso, cuando se hace `DELETE /keys/{id}`, entonces responde `200` con
  `active: false` y el siguiente request con esa key da `401` sin esperar el TTL —
  `tests/e2e/test_api_keys_e2e.py::test_revocar_corta_el_acceso_al_instante_sin_reiniciar`; y
  la fila sigue listada con `active: false` y su `name` —
  `tests/e2e/test_api_keys_e2e.py::test_revocar_conserva_la_identidad_para_auditoria`
- [ ] Dado un `DELETE /keys/{id}` sobre una key ya revocada, cuando se procesa, entonces responde
  `409` — `tests/e2e/test_api_keys_e2e.py::test_revocar_dos_veces_da_409`; sobre un id
  inexistente responde `404` `key no encontrada` (`teleflow/gateway/main.py:531-532`) —
  `(sin test)`
- [ ] Dada una key activa, cuando se hace `POST /keys/{id}/rotate`, entonces responde `200` con
  un `key` distinto, el mismo `id` y los mismos `scopes`; el secreto viejo da `401` y el nuevo
  `200` — `tests/e2e/test_api_keys_e2e.py::test_rotar_invalida_el_secreto_viejo_y_mantiene_la_identidad`.
  Rotar una key revocada da `409` y un id inexistente `404` (`teleflow/gateway/main.py:556-561`)
  — `(sin test)`

### Revocacion entre replicas

- [ ] Dada una revocacion con Redis disponible, cuando se llama a `anunciar_revocacion(hash)`,
  entonces se publica exactamente `(teleflow:keys:revocadas, hash)` —
  `tests/test_revocacion_replicas.py::test_revocar_anuncia_a_las_demas_replicas`
- [ ] Dado un hash vigente en el cache local, cuando se purga (por anuncio recibido o sin Redis),
  entonces sale del cache:
  - `purgar_cache(hash)` — `tests/test_revocacion_replicas.py::test_la_replica_que_escucha_purga_su_cache`
  - `anunciar_revocacion` sin Redis configurado —
    `tests/test_revocacion_replicas.py::test_revocar_purga_local_aunque_no_haya_redis`
  - `anunciar_revocacion` con `publish` fallando: no levanta excepcion y
    `teleflow_key_revocations_unpublished_total` sube en 1 —
    `tests/test_revocacion_replicas.py::test_si_el_anuncio_falla_no_rompe_pero_se_cuenta`
- [ ] Dadas dos replicas con la key cacheada y un bus comun, cuando la replica A revoca, entonces
  A la purga, B la conserva hasta recibir el mensaje y la purga al aplicarlo —
  `tests/test_revocacion_replicas.py::test_dos_replicas_comparten_la_revocacion`
- [ ] Dado el gateway arrancado con Redis, cuando llega un mensaje al canal, entonces el listener
  purga el hash y suma `teleflow_key_revocations_received_total`; si la suscripcion cae, se
  reintenta a los 3 s (`teleflow/gateway/main.py:302-335`) — `(sin test)`: los tests llaman a
  `purgar_cache` directo, no al listener
- [ ] Dada una rotacion, cuando termina, entonces el hash viejo se anuncia como revocado a las
  demas replicas (`teleflow/gateway/main.py:567-568`) — `(sin test)` entre replicas; el corte en
  una replica esta en
  `tests/e2e/test_api_keys_e2e.py::test_rotar_invalida_el_secreto_viejo_y_mantiene_la_identidad`

### Rate limit

- [ ] Dado `rate_limit_rpm = 3` y Redis disponible, cuando la misma key hace 5 requests en el
  mismo minuto, entonces los resultados son `permitido, permitido, permitido, rechazado,
  rechazado` y todo va a una sola clave —
  `tests/test_revocacion_replicas.py::test_el_limite_se_cuenta_en_redis_y_no_por_proceso`
- [ ] Dadas dos replicas sobre el mismo Redis con limite 3, cuando la A consume 2 y la B 2,
  entonces el cuarto request lo rechaza la B —
  `tests/test_revocacion_replicas.py::test_dos_replicas_comparten_el_contador`
- [ ] Dada la primera request del minuto, cuando se cuenta, entonces la clave de Redis contiene
  el hash de la key y no la key en claro, y se fija `EXPIRE` de 120 s —
  `tests/test_revocacion_replicas.py::test_la_clave_va_hasheada_y_expira_sola`
- [ ] Dado Redis fallando en `INCR` y limite 2, cuando llegan 4 requests, entonces los dos
  primeros pasan, el cuarto se rechaza por el bucket del proceso y
  `teleflow_rate_limit_degraded_total` sube en 4 —
  `tests/test_revocacion_replicas.py::test_si_redis_falla_se_degrada_al_bucket_del_proceso`
- [ ] Dada una key valida con el limite agotado, cuando hace un request, entonces responde `429`
  — `tests/test_auditoria.py::test_un_intento_cortado_por_rate_limit_deja_constancia`. Cuerpo
  `{"detail": "Rate limit excedido"}` (`teleflow/gateway/main.py:158-160`) y default de 120 rpm
  (`teleflow/common/config.py:93`) — `(sin test)`

### Auditoria

- [ ] Dada una accion con scope de escritura, cuando termina (aunque sea con error de upstream),
  entonces queda una fila con `scope`, `method`, `subject`, `actor_name` y `status_code` reales:
  `POST /flows/alta_socio` → `flows:deploy`, `POST`, `alta_socio`, `bootstrap (env)`, `>= 400` —
  `tests/test_auditoria.py::test_una_escritura_queda_registrada`
- [ ] Dado un deploy con `version: "2.1.0"`, cuando se audita, entonces `details.version ==
  "2.1.0"` y el `source` no aparece en ningun campo de la fila —
  `tests/test_auditoria.py::test_el_deploy_registra_version_y_checksum_pero_no_el_source`. Que
  `details.checksum` se agregue cuando el parser responde (`teleflow/gateway/main.py:624`) —
  `(sin test)`
- [ ] Dada una lectura exitosa (`GET /flows`), cuando termina, entonces no se escribe ninguna fila
  — `tests/test_auditoria.py::test_una_lectura_exitosa_no_se_registra`
- [ ] Dado un request que termina con cualquiera de estos resultados, cuando se audita, entonces
  queda exactamente una fila con ese `status_code`:
  - `403`, con el `scope` que la ruta exigio (anotado antes del chequeo) —
    `tests/test_auditoria.py::test_un_intento_denegado_queda_registrado_con_el_scope_que_se_intento`
  - `401`, con `scope == ""` y `actor_key_id` nulo —
    `tests/test_auditoria.py::test_una_key_invalida_queda_registrada`; `actor_name == "key inválida"`
    (`teleflow/gateway/main.py:231`) — `(sin test)`
  - `429` — `tests/test_auditoria.py::test_un_intento_cortado_por_rate_limit_deja_constancia`
  - `500` por una excepcion dentro de la ruta, con el `scope` de la ruta —
    `tests/test_auditoria.py::test_una_ruta_que_revienta_deja_constancia`
- [ ] Dado `POST /entities/socio/12345`, cuando se audita, entonces `subject == "socio/12345"` —
  `tests/test_auditoria.py::test_el_subject_conserva_el_registro_y_no_solo_el_tipo`. Recorte de
  `subject` a 200 y de `path` a 500 caracteres, y `subject` nulo para rutas de un segmento
  (`teleflow/gateway/main.py:222-223`, `teleflow/gateway/main.py:235`) — `(sin test)`
- [ ] Dado `GET /audit` con `audit:read`, cuando responde, entonces la propia consulta queda
  registrada con `scope == "audit:read"` —
  `tests/test_auditoria.py::test_leer_la_auditoria_queda_auditado`
- [ ] Dado el catalogo de scopes, cuando se clasifica, entonces `SCOPES_DE_ESCRITURA` y
  `SCOPES_DE_LECTURA` cubren `ALL_SCOPES`, no se superponen y no inventan scopes —
  `tests/test_auditoria.py::test_todo_scope_esta_clasificado`
- [ ] Dado cualquier scope de escritura, cuando `require(scope)` rechaza un request sin
  identidad, entonces antes de rechazar deja `scope_exigido(request) == scope` —
  `tests/test_auditoria.py::test_toda_ruta_con_scope_de_escritura_pasa_por_el_marcador`
- [ ] Dada una falla al escribir en `audit_log`, cuando termina el request, entonces la respuesta
  al cliente no cambia, `teleflow_audit_write_failures_total` sube en 1 y se loguea
  `audit_write_failed` (`teleflow/gateway/main.py:241-248`) — `(sin test)`
- [ ] Dadas filas en `audit_log`, cuando se pide `GET /audit`, entonces vienen de la mas reciente
  a la mas vieja con `occurred_at, actor_name, actor_key_id, scope, method, path, subject,
  status_code, details`, y los filtros se comportan asi (`teleflow/gateway/main.py:454-481`):
  - `actor` y `scope` por igualdad — `(sin test)`
  - `subject` por prefijo (`socio` trae `socio/12345`) — `(sin test)`
  - `desde` / `hasta` inclusivos sobre `occurred_at` — `(sin test)`
  - `solo_denegados=true` trae solo `401`, `403` y `429` — `(sin test)`
  - `limit` se acota a `1..1000` (default 100) — `(sin test)`

### Proxy hacia servicios internos

- [ ] Dado el parser-service caido, cuando se hace `POST /flows/{name}`, entonces responde `502`
  con `detail` que contiene `Servicio no disponible` y no `500` —
  `tests/test_gateway_scopes.py::test_deploy_con_el_parser_caido_da_502_no_500`
- [ ] Dado un servicio interno caido (conexion, timeout o DNS), cuando una ruta proxeada lo
  llama, entonces responde `502` `Servicio no disponible: <url>`
  (`teleflow/gateway/main.py:430-431`) — `(sin test)`: los tests de scopes pasan por ahi pero
  solo afirman `!= 403`
- [ ] Dada una respuesta del servicio interno, cuando el gateway la reenvia, entonces conserva
  codigo y cuerpo — `(indirecto)`:
  - `202` de `POST /execute` —
    `tests/e2e/test_idempotencia_e2e.py::test_el_header_llega_al_executor_y_deduplica`
  - `201` de `POST /entities/nino` y `200` de `GET /entities/nino/{id}/360` —
    `tests/e2e/test_event_driven_e2e.py::test_entity_rule_process_y_vista_360`
  - `200` con `status == "SIGNALED"` de `POST /instances/{id}/signal` —
    `tests/e2e/test_durable_sleep_e2e.py::test_durable_sleep_signal_approve`
  - `404` de `GET /flows/{name}/9.9.9` —
    `tests/e2e/test_registry_e2e.py::test_una_version_inexistente_da_404`
  - `media_type` tomado del `content-type` del upstream (`teleflow/gateway/main.py:432-433`) —
    `(sin test)`
- [ ] Dado un request con query string, cuando se proxea, entonces los parametros llegan al
  servicio: `GET /entities/nino?estado=ACTIVO&limit=200` devuelve solo las activas —
  `(indirecto)`
  `tests/e2e/test_entidades_e2e.py::test_el_filtro_por_estado_separa_lo_activo_de_lo_recien_registrado`
- [ ] Dado `POST /execute` con `Idempotency-Key`, cuando se repite con la misma clave y el mismo
  pedido, entonces las dos respuestas traen el mismo `instance_id` y la segunda
  `idempotent_replay: true`; sin clave, cada llamada crea otra instancia — `(indirecto)`
  `tests/e2e/test_idempotencia_e2e.py::test_el_header_llega_al_executor_y_deduplica`,
  `tests/e2e/test_idempotencia_e2e.py::test_sin_clave_cada_llamada_dispara`
- [ ] Dado un request de cliente con headers propios (incluida `X-TeleFlow-API-Key`), cuando se
  proxea, entonces al servicio interno solo llegan `Content-Type: application/json` (si hay
  cuerpo) y los `extra_headers` explicitos de la ruta (`teleflow/gateway/main.py:412-418`) —
  `(sin test)`
- [ ] Dado `POST /compose`, cuando se proxea, entonces usa `compose_timeout` (660 s) en vez de
  los 60 s del cliente (`teleflow/gateway/main.py:51`, `teleflow/gateway/main.py:779-781`) —
  `(sin test)` del uso en la ruta; que 660 quede entre el timeout del proveedor y el del nginx de
  la UI lo prueba `(indirecto)`
  `tests/test_composer.py::test_la_cadena_de_timeouts_es_estrictamente_creciente`

### Deploy de flows

- [ ] Dada una fuente valida y una version nueva, cuando se hace `POST /flows/{name}`, entonces
  responde `201` — `(indirecto)` `tests/e2e/test_registry_e2e.py::test_un_release_candidate_no_se_vuelve_latest`
  y el fixture `deployed` (`tests/e2e/conftest.py:54-60`). Que el cuerpo sea el del registry mas
  `issues` con los warnings del parser (`teleflow/gateway/main.py:649-652`) — `(sin test)`
- [ ] Dada una fuente que el parser marca `valid: false`, cuando se hace `POST /flows/{name}`,
  entonces responde `422` con `detail` `El flow no pasó la validación` e `issues`, y no llama al
  registry (`teleflow/gateway/main.py:625-629`) — `(sin test)`
- [ ] Dada una respuesta de error de un salto del deploy, cuando el gateway la recibe, entonces:
  - registry con `>= 400` → mismo codigo y cuerpo: `409` con `inmutable` al repetir version —
    `(indirecto)` `tests/e2e/test_registry_e2e.py::test_una_version_registrada_no_se_puede_pisar`
  - parser con codigo distinto de `200` → mismo codigo y cuerpo
    (`teleflow/gateway/main.py:619-622`) — `(sin test)`
  - registry caido → `502` (`teleflow/gateway/main.py:642-643`) — `(sin test)`

### Contrato OpenAPI

- [ ] Dada la app del gateway, cuando se recorren sus rutas incluidas en el esquema, entonces
  todas declaran `operation_id` explicito —
  `tests/test_openapi_contract.py::test_toda_ruta_declara_operation_id_explicito`
- [ ] Dado `app.openapi()`, cuando se listan los `operationId`, entonces:
  - no hay duplicados — `tests/test_openapi_contract.py::test_los_operation_id_son_unicos`
  - ninguno termina en `_<metodo>` como los autogenerados —
    `tests/test_openapi_contract.py::test_los_operation_id_no_son_los_autogenerados`
  - toda operacion tiene un tag de `keys, flows, instances, entities, composer, audit` —
    `tests/test_openapi_contract.py::test_toda_ruta_esta_agrupada_en_una_familia_conocida`
  - toda operacion declara `security: [{"APIKeyHeader": []}]` con header `X-TeleFlow-API-Key`
    (`teleflow/gateway/main.py:75-78`, `docs/openapi.json:1267-1272`) — `(sin test)`
- [ ] Dado el repo sin stack levantado, cuando se corre `tflow openapi [--output <ruta>]`,
  entonces escribe el JSON de `app.openapi()` en `docs/openapi.json` (o la ruta dada), crea el
  directorio si falta e imprime la cantidad de paths (`teleflow/cli.py:149-162`,
  `teleflow/cli.py:223-225`) — `(sin test)`

### CLI `tflow`

- [ ] Dadas `TELEFLOW_URL` y `TELEFLOW_API_KEY` (o sus defaults `http://localhost:8000` y
  `dev-key-change-me`), cuando se corre un comando, entonces llama al gateway con el header
  `X-TeleFlow-API-Key` y timeout de 60 s (`teleflow/cli.py:30-37`), y se comporta asi — todo
  `(sin test)`:
  - `validate <archivo>` → `POST /parse`; imprime `✓ válido` o `✗ inválido` y cada issue, y
    sale con codigo 1 si no es valido (`teleflow/cli.py:52-63`)
  - `deploy <archivo> --version V [--name N] [--description D]` → `POST /flows/{N}`, con `N` por
    defecto el nombre del archivo sin extension (`teleflow/cli.py:66-76`)
  - `flows`, `status <id>`, `drafts` → `GET /flows`, `GET /instances/{id}`, `GET /drafts`
    (`teleflow/cli.py:79-84`, `teleflow/cli.py:99-104`, `teleflow/cli.py:131-136`)
  - `execute <flow> [--version latest] [--payload JSON] [--correlation-id C]` → `POST /execute`
    (`teleflow/cli.py:87-96`)
  - `signal <id> --step S --signal X [--actor A] [--data JSON]` → `POST /instances/{id}/signal`
    (`teleflow/cli.py:107-116`)
  - `compose <nombre> --description D` → `POST /compose`; imprime `draft_id` y la fuente
    (`teleflow/cli.py:119-128`)
  - `approve <draft_id> --version V [--actor cli]` → `POST /drafts/{id}/approve`
    (`teleflow/cli.py:139-146`)
  - cualquier respuesta `>= 400` → imprime el cuerpo y sale con codigo 1 (`teleflow/cli.py:44-49`)
  - gateway inalcanzable → `No se pudo conectar a <url>` por stderr y codigo 2
    (`teleflow/cli.py:228-233`)
  - salida forzada a UTF-8 para consolas Windows (`teleflow/cli.py:166-170`)

## Impacto en lo existente

Esta carpeta no cambia codigo. Lo que depende del modulo, y por lo tanto se rompe si cambia:

- **Contrato de rutas y `operation_id`.** Renombrar un `operation_id` o mover una ruta de tag
  rompe clientes generados y, en la direccion vigente, las `@capacidades` del asistente que se
  generen del OpenAPI. `docs/openapi.json` hay que regenerarlo a mano con `tflow openapi`.
- **Catalogo de scopes.** Agregar un scope obliga a clasificarlo como lectura o escritura
  (`tests/test_auditoria.py::test_todo_scope_esta_clasificado`); las keys con `*` lo reciben
  automaticamente (`teleflow/gateway/auth.py:68-69`) y las de scopes explicitos no. Quitar o
  renombrar uno deja keys de `api_keys` con un scope que ya no existe: `resolver_key` no las
  valida contra el catalogo (`teleflow/gateway/auth.py:107-109`) y la bootstrap con ese nombre
  en `TELEFLOW_API_KEY_SCOPES` falla al primer uso (ver "No entra").
- **Consumidores del gateway.** La review-ui por su proxy nginx (`seguridad.md:41`); el composer
  al aprobar un borrador, con la key de bootstrap
  (`teleflow/composer_service/main.py:173-179`); la CLI; y todos los e2e, que usan el gateway
  como unica puerta (`tests/e2e/conftest.py:19-23`).
- **Tablas.** `api_keys` (`alembic/versions/0002_api_keys.py:18-31`) y `audit_log`
  (`alembic/versions/0004_audit_log.py:18-34`) son aditivas y sin FK entre si
  (`alembic/versions/0004_audit_log.py:23-27`). Una columna nueva sigue la numeracion `0008+` y
  convive con pods viejos (`spec/constitution/tech_stack.md:57-59`).
- **Replicas.** El chart corre el gateway con 2 replicas (`helm/teleflow/values.yaml:75-77`):
  cualquier estado nuevo en memoria del proceso repite el problema que resolvio el ADR de estado
  compartido (`wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:31-39`).
- **Tests.** Toda dependencia de I/O nueva del gateway tiene que sumarse al fixture
  `sink_auditoria` en el mismo commit (`wiki/Knowledge/backlog-hardening.md:200-202`,
  `tests/conftest.py:96-111`).
- **Aislamiento por instancia.** Nada en el modulo es multi-tenant: una instalacion, una tabla de
  keys, una auditoria (`wiki/Knowledge/decisions/2026-06-30-adr-005-aislamiento-instancia.md:19-20`).

## Fuentes

- `teleflow/gateway/main.py:39` — rutas publicas.
- `teleflow/gateway/main.py:115-163` — rate limit compartido y middleware de auth.
- `teleflow/gateway/main.py:174-248` — middleware de auditoria y escritura en `audit_log`.
- `teleflow/gateway/main.py:271-381` — cache de identidades, revocacion por pub/sub y
  resolucion de la key.
- `teleflow/gateway/main.py:399-433` — `_post_upstream` y `_proxy`.
- `teleflow/gateway/main.py:438-816` — rutas.
- `teleflow/gateway/auth.py:29-195` — scopes, identidad, autorizacion y marcador de auditoria.
- `teleflow/common/config.py:17-33`, `teleflow/common/config.py:58`,
  `teleflow/common/config.py:93` — configuracion del modulo.
- `teleflow/common/models.py:226-269` — `ApiKey` y `AuditLog`.
- `teleflow/common/observability.py:28-64` — `/health`, `/ready`, `/metrics`.
- `teleflow/cli.py:1-237` — CLI `tflow`.
- `alembic/versions/0002_api_keys.py:17-31`, `alembic/versions/0004_audit_log.py:17-34`.
- `docs/openapi.json` — contrato generado (27 operaciones).
- `tests/conftest.py:96-111` — dobles de Postgres y Redis para el gateway.
- `seguridad.md` — superficie, controles y huecos de seguridad de este modulo (provenance
  `copp-ia@devyos@ffd585d`; las lineas de `teleflow/gateway/` que cita coinciden con lo leido en
  `4c44b4c`).
- [[2026-07-25-auditoria-persistida]] — que se audita, que se guarda, best-effort, sin purga.
- [[2026-07-25-estado-compartido-gateway]] — rate limit en Redis, degradacion, revocacion por
  pub/sub.
- [[2026-06-30-adr-005-aislamiento-instancia]] — una instancia por organismo.
- [[2026-08-27-correccion-del-borrador-en-la-revision]] — `PATCH /drafts/{id}/source` con
  `flows:deploy` y `POST /parse` como validador del servidor.

## Discrepancias doc ↔ codigo

Comprobadas, sin corregir:

- `teleflow/gateway/main.py:3` dice "rate limiting (token bucket por API key)" y
  `docs/teleflow-arquitectura.typ:158` "token-bucket rate limiting por key"; el mecanismo
  principal es una ventana fija en Redis y el token bucket es solo la degradacion
  (`teleflow/gateway/main.py:115-142`).
- `teleflow/common/models.py:253` y el ADR de auditoria
  (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:38-40`) dicen que se registran
  los intentos denegados "401/403"; el codigo tambien registra `429` y `500`
  (`teleflow/gateway/main.py:186-194`, `teleflow/gateway/main.py:203`). `README.md:208` si dice
  401/403/429.
- El ADR de auditoria enumera `operation_id` entre las columnas que se guardan
  (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:51-53`); `audit_log` no tiene
  esa columna (`alembic/versions/0004_audit_log.py:18-34`) ni se escribe
  (`teleflow/gateway/main.py:230-239`).
- El ADR de estado compartido dice que `purgar_cache()` pasa a publicar en el canal
  (`wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:78-80`); en el codigo
  `purgar_cache` es solo local y publica `anunciar_revocacion`
  (`teleflow/gateway/main.py:271-299`).
- `teleflow/gateway/auth.py:57` dice que un scope inexistente en la config "se falla al arrancar,
  no en runtime"; la key de bootstrap se parsea en el primer request que la usa
  (`teleflow/gateway/main.py:338-354`).
- `teleflow/gateway/auth.py:39` describe `keys:admin` como "crear/listar credenciales"; tambien
  habilita revocar y rotar (`teleflow/gateway/main.py:522-547`).
- `.env.example:7-8` lista los scopes validos sin `audit:read`, que esta en el catalogo
  (`teleflow/gateway/auth.py:40`, `teleflow/gateway/auth.py:48`).
- `tests/test_revocacion_replicas.py:8` cita `helm/teleflow/values.yaml:28` para `replicas: 2`
  del gateway; en este commit esta en `helm/teleflow/values.yaml:77`.
- `docs/teleflow-api-reference.typ:312-314` dice que todos los endpoints requieren el header, que
  la key se configura en `TELEFLOW_API_KEY` y solo menciona `401`; hay rutas publicas
  (`teleflow/gateway/main.py:39`), keys en base (`teleflow/gateway/main.py:356-381`) y respuestas
  `403`/`429`. El mismo documento lista `GET /flows/{name}/versions`
  (`docs/teleflow-api-reference.typ:337-338`), que no existe: las versiones salen de
  `GET /flows/{name}` y una version de `GET /flows/{name}/{version}`
  (`teleflow/gateway/main.py:670-681`); y no documenta `/keys`, `/audit`, `/parse`, `/domain` ni
  `/instances/{id}/retry`.
- `AGENTS.md:104` prohibe `type: ignore` para pasar `mypy`; los dos middlewares del gateway lo
  usan (`teleflow/gateway/main.py:146`, `teleflow/gateway/main.py:175`). Que `mypy .` de 0 no se
  verifico en esta pasada.
