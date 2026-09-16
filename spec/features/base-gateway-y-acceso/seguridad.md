---
project: copp-ia
type: seguridad
status: implementada
feature: base-gateway-y-acceso
provenance: copp-ia@devyos@ffd585d
reviewed: 2026-09-14
---

# Seguridad e infraestructura — Base del gateway y el acceso

> Linea base as-built. Provenance: `copp-ia@devyos@ffd585d`. Alcance: `teleflow/gateway/main.py`,
> `teleflow/gateway/auth.py`, `teleflow/cli.py`, las tablas `api_keys` y `audit_log`
> (`alembic/versions/0002_api_keys.py`, `0004_audit_log.py`), la exposicion del gateway
> (`docker-compose.yml`, `helm/teleflow/templates/ingress.yaml`, `values.yaml`,
> `values-production.yaml`) y sus consumidores internos: composer-service (aprueba con la key
> del servicio) y review-ui (guarda la key en el navegador). Lo que cae en otro modulo pero lo
> habilita un contrato de este va marcado `(frontera: <modulo>)`.
> Codigo de terceros citado desde `.venv/Lib/site-packages/` (no versionado): httpx 0.28.1,
> uvicorn 0.49.0, starlette 1.2.1, fastapi 0.136.3, redis 8.0.0 (versiones de sus
> `*.dist-info`). **Nada de lo marcado `(inferencia)` se ejecuto**: es lectura de codigo.

## Superficie expuesta

| Superficie | Quien puede llegar | Control | Fuente |
|---|---|---|---|
| `GET /health`, `/ready`, `/metrics`, `/docs`, `/openapi.json`, `/redoc` (gateway) | cualquiera que llegue al puerto 8000 o al Ingress | **ninguno**: saltean auth, rate limit y auditoria | `teleflow/gateway/main.py:39,149-150,184,196-197`; `teleflow/common/observability.py:46-64` |
| `OPTIONS` sobre cualquier ruta | cualquiera | ninguno (saltea auth, rate limit y auditoria) | `teleflow/gateway/main.py:149,184` |
| `GET /audit` | key valida | `audit:read`; auditado | `teleflow/gateway/main.py:438-481` |
| `POST /keys`, `GET /keys`, `DELETE /keys/{id}`, `POST /keys/{id}/rotate` | key valida | `keys:admin` | `teleflow/gateway/main.py:491-593` |
| `POST /flows/{name}` | key valida | `flows:deploy` | `teleflow/gateway/main.py:604-652` |
| `POST /parse`, `GET /flows`, `/flows/{name}`, `/flows/{name}/{version}` | key valida | `flows:read` | `teleflow/gateway/main.py:655-681` |
| `POST /execute` | key valida | `instances:trigger` | `teleflow/gateway/main.py:686-696` |
| `GET /instances`, `/instances/{id}` | key valida | `instances:read` | `teleflow/gateway/main.py:699-710` |
| `POST /instances/{id}/signal` · `/retry` | key valida | `instances:signal` · `instances:retry` | `teleflow/gateway/main.py:713-726` |
| `GET\|POST\|PATCH /entities/{rest:path}`, `/relations/{rest:path}` | key valida | `entities:read` (GET) / `entities:write` (POST, PATCH) — **ver hueco de path traversal** | `teleflow/gateway/main.py:729-746,760-770` |
| `GET /domain` | key valida | `entities:read` | `teleflow/gateway/main.py:749-757` |
| `POST /compose`, `GET /drafts`, `GET\|POST /drafts/{rest:path}` | key valida | `compose:read` / `compose:write` | `teleflow/gateway/main.py:775-800` |
| `PATCH /drafts/{id}/source` | key valida | `flows:deploy` | `teleflow/gateway/main.py:803-816` |
| composer-service → `POST {GATEWAY_URL}/flows/{draft.name}` | composer, al aprobar | **key de bootstrap** (`TELEFLOW_API_KEY`, scopes `*` por default) | `teleflow/composer_service/main.py:173-179` |
| review-ui → `/api/*` (nginx) → gateway | navegador del operador | key leida de `localStorage` y mandada en header | `review-ui/src/api.js:1-15`; `review-ui/nginx.conf.template:30-35` |
| CLI `tflow` → gateway | operador | key de `TELEFLOW_API_KEY` (default `dev-key-change-me`) | `teleflow/cli.py:30-37` |
| executor, composer, registry, parser directos (sin gateway) | cualquier pod/contenedor de la red interna | **ninguno** (sin auth propia) | `teleflow/executor_service/main.py:98-317`, `teleflow/composer_service/main.py:60-276`; `ClusterIP` `helm/teleflow/templates/deployments.yaml:76-81` |
| Tabla `api_keys` | gateway (lee/escribe) | solo hash | `alembic/versions/0002_api_keys.py:18-31` |
| Tabla `audit_log` | gateway (escribe), `audit:read` (lee) | append-only por convencion de la API | `alembic/versions/0004_audit_log.py:18-34` |
| Redis: `ratelimit:<hash>:<ventana>` y canal `teleflow:keys:revocadas` | gateway | red interna | `teleflow/gateway/main.py:127-133,259` |

**Exposicion del gateway.** Compose publica `8000:8000` (`docker-compose.yml:148-149`)
`(inferencia: sin IP de bind, Docker escucha en todas las interfaces del host)`. Helm: Service
`ClusterIP` por default (`helm/teleflow/values.yaml:145-147`, `helm/teleflow/templates/deployments.yaml:77-78`); el
Ingress es opt-in (`helm/teleflow/values.yaml:148-149`, `helm/teleflow/templates/ingress.yaml:16`) y publica **todo** el gateway con
`path: /` `pathType: Prefix` (`helm/teleflow/templates/ingress.yaml:62-63`), incluidas las rutas publicas de la tabla.
`helm/teleflow/values-production.yaml:42-45` lo enciende con `className: nginx` y `annotations: {}`.

## Controles existentes

- **Keys de la DB hasheadas con SHA-256**, nunca en claro: `hash_key` (`teleflow/gateway/auth.py:95-97`),
  columna `key_hash String(64)` unica e indexada (`alembic/versions/0002_api_keys.py:24`). El
  secreto es `tf_` + `secrets.token_urlsafe(32)` (`teleflow/gateway/auth.py:90-92`); se devuelve una sola vez
  (`teleflow/gateway/main.py:513-519`) y no se loguea (`teleflow/gateway/main.py:512` loguea nombre y scopes).
  `GET /keys` no devuelve secretos ni hashes (`teleflow/gateway/main.py:586-593`). La eleccion de SHA-256 sobre
  bcrypt esta justificada por la entropia (`teleflow/common/models.py:229-232`).
- **Key de bootstrap comparada en tiempo constante**: `secrets.compare_digest(api_key,
  settings.teleflow_api_key)` (`teleflow/gateway/main.py:352`), resuelta sin tocar la DB (`teleflow/gateway/main.py:347-354`).
  Header vacio → `None` antes de comparar (`teleflow/gateway/main.py:350-351`).
- **Sin oraculo de enumeracion en el 401**: key inexistente, revocada o DB caida devuelven el
  mismo `{"detail": "API key inválida"}` (`teleflow/gateway/main.py:155-156,369-378`). La busqueda en DB es por
  igualdad del hash (`teleflow/gateway/auth.py:102-104`) `(inferencia: el atacante no controla el prefijo del
  hash, asi que el timing del indice no filtra la key)`.
- **12 scopes + comodin**: `ALL_SCOPES` con 12 entradas (`teleflow/gateway/auth.py:29-49`); `*` expande a
  todos (`teleflow/gateway/auth.py:51,68-69`); un scope desconocido falla (`teleflow/gateway/auth.py:70-75`), y para la key de
  bootstrap falla al primer uso de `get_bootstrap_scopes` (`teleflow/gateway/main.py:338-341`). Autorizacion
  por ruta con `require`/`require_por_metodo` → 403 (`teleflow/gateway/auth.py:118-144`); todas las rutas no
  publicas del gateway llevan una de las dos (`teleflow/gateway/main.py:438-816`).
- **Revocacion compartida**: `DELETE /keys/{id}` pone `active=False` sin borrar la fila
  (`teleflow/gateway/main.py:522-542`); `resolver_key` filtra `active` (`teleflow/gateway/auth.py:103`). Purga local + `PUBLISH`
  en `teleflow:keys:revocadas` (`teleflow/gateway/main.py:280-299`); cada replica escucha con reconexion y purga
  (`teleflow/gateway/main.py:302-335`). Si el publish falla: contador `teleflow_key_revocations_unpublished_total`
  + `log.error` (`teleflow/gateway/main.py:294-299`). Techo si se pierde el mensaje: TTL del cache,
  `api_key_cache_ttl = 30` s (`teleflow/common/config.py:25-26`, `teleflow/gateway/main.py:379-380`).
- **Rotacion** de keys de DB: nuevo secreto, mismo `name` y scopes, hash viejo anunciado como
  revocado (`teleflow/gateway/main.py:545-576`); rotar o revocar una key ya revocada da 409 (`teleflow/gateway/main.py:533-535,558-561`).
- **Rate limit compartido**: ventana fija por minuto en Redis con la key **hasheada** en el
  nombre de la clave (`teleflow/gateway/main.py:115-134`), 120 rpm por default (`teleflow/common/config.py:93`,
  `docker-compose.yml:26`). Si Redis falla, degrada al token bucket del proceso y lo cuenta en
  `teleflow_rate_limit_degraded_total` + `log.error` (`teleflow/gateway/main.py:135-142`). Timeouts de Redis de 5 s
  por default (terceros: `.venv/Lib/site-packages/redis/_defaults.py:7-8`).
- **Auditoria persistida**: toda ruta con scope de escritura, `audit:read` y todo 401/403/429 se
  registra despues de conocer el resultado (`teleflow/gateway/main.py:174-208`, `teleflow/gateway/auth.py:155-170`); el scope se
  anota antes del chequeo, asi un 403 registra lo intentado (`teleflow/gateway/auth.py:121-123`). Una excepcion
  en la ruta se registra como 500 (`teleflow/gateway/main.py:186-194`). El middleware de auditoria queda por
  fuera del de auth (declarado despues; Starlette inserta al frente y envuelve en orden inverso,
  terceros `.venv/Lib/site-packages/starlette/applications.py:75,101`). Sin FK a `api_keys`, la
  identidad sobrevive a la revocacion (`alembic/versions/0004_audit_log.py:23-27`). No guarda el cuerpo del
  request (`teleflow/common/models.py:257-258`); el deploy agrega solo version y checksum (`teleflow/gateway/main.py:609-612,624`).
  `GET /audit` acota `limit` a 1..1000 (`teleflow/gateway/main.py:469`).
- **Falla de auditoria visible**: `except Exception` con contador
  `teleflow_audit_write_failures_total` + `log.error` (`teleflow/gateway/main.py:241-248`); limite consciente
  documentado (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:88-92`).
- **El proxy arma los headers desde cero**: no reenvia los del cliente (tampoco la API key)
  hacia los servicios internos; solo `Idempotency-Key` se propaga explicito (`teleflow/gateway/main.py:409-418,694-696`).
- **Errores de upstream sin stack**: `RequestError` → 502 generico (`teleflow/gateway/main.py:386-406,430-431`).
- **CORS ausente = navegador bloqueado** `(inferencia: sin `CORSMiddleware` —busqueda
  `CORSMiddleware` en el repo sin coincidencias— un origen ajeno no puede leer respuestas, y el
  header custom fuerza un preflight que no recibe `Access-Control-Allow-Origin`)`. Al ser auth
  por header y no por cookie, no hay CSRF `(inferencia)`.
- **Chart**: sin `apiKey` ni `existingSecret` el install falla (`helm/teleflow/templates/secrets.yaml:36-39`);
  `existingSecret` declarado e inexistente tambien (`helm/teleflow/templates/secrets.yaml:31-35`). `TELEFLOW_API_KEY` llega
  por `secretKeyRef` (`helm/teleflow/templates/_helpers.tpl:267-271`). Ingress con TLS
  obligatorio salvo `allowInsecure` explicito, `secretName` y `hosts` validados
  (`helm/teleflow/templates/ingress.yaml:41-57`). El review-ui no se publica fuera del cluster (`helm/teleflow/templates/ingress.yaml:12-14`,
  `helm/teleflow/templates/review-ui.yaml:59`).
- **Readiness real**: `/ready` del gateway hace `db_ping` (`teleflow/gateway/main.py:79-81`).
- **Separacion editar/aprobar borradores**: editar la fuente exige `flows:deploy`, no
  `compose:write` (`teleflow/gateway/main.py:803-816`). Ver hueco alto sobre aprobar.

## Huecos

| Hueco | Severidad | Evidencia |
|---|---|---|
| **Path traversal en los proxies `{rest:path}`: una key con `entities:write` llega a `/execute`, `/internal/execute`, `/instances/{id}/signal` y `/retry` del executor; una con `entities:read` lista instancias y lee su `context` (datos personales).** El gateway autoriza por metodo sobre `/entities/...` y reenvia `f"/entities/{rest}"`; uvicorn decodifica `%2e%2e`/`%2F` antes de rutear, el convertor `path` acepta `..`, y httpx elimina los segmentos `..` de la URL absoluta. `POST /entities/%2e%2e/execute` sale como `POST http://executor:8002/execute`. La auditoria lo registra con scope `entities:write` y subject `../execute`; la variante de lectura no se audita. Direccion: rechazar segmentos `.`/`..` (y `%2F`) en `rest` antes de proxear, o proxear rutas con parametros tipados. | alta | Proxy `teleflow/gateway/main.py:745-746,769-770`; scope por metodo `teleflow/gateway/main.py:729-731`; query reenviada `teleflow/gateway/main.py:424`. Terceros: `.venv/Lib/site-packages/uvicorn/protocols/http/h11_impl.py:200-201` y `.venv/Lib/site-packages/uvicorn/protocols/http/httptools_impl.py:256-259` (`unquote` del path); `.venv/Lib/site-packages/starlette/convertors.py:33-34` (`regex = ".*"`); `.venv/Lib/site-packages/httpx/_urlparse.py:328-329,447-475` (`normalize_path`). Destinos: `teleflow/executor_service/main.py:98-115` (`/execute`, `/internal/execute`), `:118-152` (`context` en `:147`), `:177-187`. Mismo patron en `/drafts/{rest:path}` (`teleflow/gateway/main.py:799-800`) pero el composer no tiene rutas GET/POST de otro scope (`teleflow/composer_service/main.py:60,138,148,163,203`). No se encontro test que lo cubra (busqueda `%2e\|\.\./\|path.?traversal` en `tests/`). `(inferencia)` a traves de ingress-nginx el URI viaja sin normalizar al backend; no verificado. |
| **(frontera: composer) Aprobar un borrador arma la URL con `draft.name` sin validar y la manda con la key de bootstrap (`*`).** `name` es texto libre al componer; con `name = "../keys/<uuid>/rotate"` la aprobacion hace `POST /keys/<uuid>/rotate` como bootstrap y **devuelve el secreto nuevo** en el campo `deploy` de la respuesta. Con cuerpos compatibles alcanza tambien `/instances/{id}/retry` (sin cuerpo) y `/entities/{tipo}` (`fields` default). Todo con `compose:write`. Direccion: validar `name` como identificador del DSL en composer y gateway, y no aprobar con la key de bootstrap. | alta | `ComposeRequest.name: str` sin validacion `teleflow/composer_service/main.py:54-57`; persistido `:97` (`flow_drafts.name String(200)` `alembic/versions/0001_initial.py:117`); URL y key `:173-179`; respuesta devuelta `:187-195`; normalizacion httpx (ver arriba). Rotar no pide cuerpo `teleflow/gateway/main.py:545-576`; retry `teleflow/gateway/main.py:721-726`; `CreateEntityRequest` con defaults `teleflow/executor_service/main.py:193-195`. Scope que se chequea: solo `compose:write` en `teleflow/gateway/main.py:795-798`. `(inferencia)` el `uuid` de una key se obtiene de `/audit` (`actor_key_id`, `teleflow/gateway/main.py:474`) o de `/keys`; el retry necesita un `instance_id`. |
| **(frontera: composer) `compose:write` alcanza para desplegar: el mismo scope genera y aprueba, y el deploy se hace con la identidad de bootstrap, no la del que aprueba.** Con un LLM real, quien describe el pedido controla la fuente generada; con `stub` puede publicar un esqueleto como version nueva de un flow existente (mismo `name`). En `audit_log` el deploy queda a nombre de `bootstrap (env)`. Contradice "una clave de analista [...] no puede reescribir lo que se despliega". Combinado con el hueco de `${env.*}` escala a todos los scopes. Direccion: exigir `flows:deploy` para aprobar o propagar la identidad del aprobador. | alta | `teleflow/gateway/auth.py:38` (`compose:write` = "generar/aprobar"); `teleflow/gateway/main.py:775-781,795-800`; key de servicio `teleflow/composer_service/main.py:176`; nombre de la identidad `teleflow/gateway/auth.py:53`, `teleflow/gateway/main.py:352-354`; docstring `teleflow/gateway/main.py:813-814`. Stub: `teleflow/composer_service/providers.py:385-408`. `(inferencia)` el esqueleto stub parsea y un modelo real obedece un pedido literal; no se ejecuto. |
| **(frontera: executor) `${env.*}` resuelve cualquier variable del executor, incluida `TELEFLOW_API_KEY`**, y la manda al host que elige el flow: `flows:deploy` escala a todos los scopes. Ya documentado; no se re-analiza aca. | alta | `wiki/Knowledge/backlog-hardening.md:147-169` (item 8); `spec/features/base-lenguaje-tflow/seguridad.md:89`. Lo que aporta este modulo: la key de bootstrap con `*` (`teleflow/common/config.py:23`) viaja en el entorno de todos los servicios (`docker-compose.yml:3-8`, `helm/teleflow/templates/_helpers.tpl:267-271`). |
| Key de bootstrap: scopes `*` por default en compose **y en el chart** (el chart no define `TELEFLOW_API_KEY_SCOPES`); no se revoca ni rota por API (rotarla es cambiar el Secret y reiniciar todos los pods); sin chequeo de fuerza (el chart acepta cualquier `apiKey` no vacio). En compose el default es el publico `dev-key-change-me` con el puerto 8000 publicado. | media | `teleflow/common/config.py:18,23`; `docker-compose.yml:7-8,148-149`; `helm/teleflow/templates/_helpers.tpl:243-277` (sin `TELEFLOW_API_KEY_SCOPES`); `helm/teleflow/templates/secrets.yaml:37-39` (solo `not .Values.apiKey`); rutas de keys solo operan filas de DB `teleflow/gateway/main.py:529-531,554-557`. |
| `/metrics` del gateway es publico y el Ingress lo publica con `path: /`: expone volumen por ruta y status, fallas de auditoria y de revocacion a cualquiera en internet. `/ready` publico hace un `db_ping` por request. | media | `teleflow/gateway/main.py:39,149-150`; `teleflow/common/observability.py:14-23,62-64`; contadores `teleflow/gateway/main.py:109-112,168-171,261-268`; `helm/teleflow/templates/ingress.yaml:62-63`; `helm/teleflow/values-production.yaml:42-45`. |
| Requests sin key valida no pasan por rate limit: el limite se aplica despues de autenticar. Cada 401 cuesta una consulta a Postgres (el cache solo guarda keys validas) **y** un `INSERT` en `audit_log`; cada 429 de una key valida tambien inserta. Sin purga de `audit_log`. Relleno de la tabla y carga de DB sin credencial. | media | Orden `teleflow/gateway/main.py:154-160`; sin cache negativo `teleflow/gateway/main.py:376-378`; 401/429 auditados `teleflow/gateway/main.py:203-207`; sin purga `wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:100-102`. |
| El gateway no liga `actor_id` a la key: señales, transiciones y aprobaciones aceptan un `actor_id` libre del cuerpo, y la review-ui lo toma de un campo que escribe el usuario. `(frontera: executor)` la señal tampoco verifica `assignee` del step. `instance_transitions.actor_id` y los comentarios del borrador quedan con la identidad declarada; solo `audit_log` tiene la real. | media | `teleflow/executor_service/main.py:169-181,198-200,260-264`; `teleflow/executor_service/engine.py:676-718` (sin chequeo de actor); `teleflow/dsl/teleflow.lark:141` (`assignee`); `teleflow/composer_service/main.py:157-160,188-191`; `review-ui/src/ops.jsx:38,73`, `review-ui/src/dominio.jsx:74,92`; CLI `teleflow/cli.py:113,142,220`; proxy sin tocar el cuerpo `teleflow/gateway/main.py:416-423`. |
| `keys:admin` puede crear keys con cualquier scope (incluido `keys:admin` y `*`): no se exige que los scopes pedidos esten dentro de los del creador. Las keys no vencen (sin `expires_at`). | media | `teleflow/gateway/main.py:495-502`; `teleflow/gateway/auth.py:68-69`; `alembic/versions/0002_api_keys.py:18-31`. |
| Auditoria best-effort: si la escritura falla (o el proceso muere) la accion ya ocurrio y no queda fila, solo contador y log. Sin IP ni origen del cliente en la tabla (el `X-Real-IP` que pone la review-ui no se lee), asi que un barrido de 401 no se puede atribuir a una fuente. | media | `teleflow/gateway/main.py:241-248`; ADR `wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:88-92`; columnas `alembic/versions/0004_audit_log.py:18-34`; `review-ui/nginx.conf.template:35`; busqueda `X-Real-IP\|client.host` en `teleflow/gateway/`: sin coincidencias en el codigo del gateway `(inferencia: por lectura de main.py completo)`. |
| Sin limite de tamaño de body en el gateway: `_proxy` lee el body entero y `DeployRequest.source`/`version` no tienen `max_length`. En compose el puerto 8000 va directo. | media | `teleflow/gateway/main.py:416,598-601`; `docker-compose.yml:148-149`. `(inferencia)` uvicorn no impone limite de body; ingress-nginx aplica su default de `proxy-body-size` (no configurado en `helm/teleflow/values-production.yaml:46`). |
| Servicios internos sin auth propia y alcanzables directo: un pod comprometido llama executor/composer/registry sin scope, sin rate limit y sin auditoria. Sin NetworkPolicy. | media | `teleflow/executor_service/main.py:77-317`; `teleflow/composer_service/main.py:50-276`; `helm/teleflow/templates/deployments.yaml:76-81`; `helm/teleflow/templates/datos.yaml:14-15` (NetworkPolicies no reescritas; busqueda `NetworkPolicy\|securityContext\|PodDisruptionBudget` en `helm/`: solo ese comentario). |
| Contenedor del gateway como root, sin `securityContext`; recibe todas las credenciales compartidas. | media | `Dockerfile:3-16` sin `USER`; `helm/teleflow/templates/deployments.yaml:39-67`; `helm/teleflow/templates/_helpers.tpl:264-277`. |
| Ventana de revocacion: pub/sub es fire-and-forget; una replica desconectada al momento del `PUBLISH` sigue aceptando la key hasta el TTL. `API_KEY_CACHE_TTL` es configurable sin tope. `(inferencia)` carrera: una replica que lee la fila activa antes del commit de la revocacion y cachea despues de recibir la purga la mantiene hasta el TTL. | baja | `teleflow/gateway/main.py:280-299,302-335,379-380`; `teleflow/common/config.py:26`; `docker-compose.yml:9`. |
| Rate limit degradado: con Redis caido el limite pasa a N× con N replicas (2 en el chart); ventana fija admite hasta 2× en el borde de minuto; con Redis inalcanzable cada request suma hasta el timeout de 5 s del cliente. | baja | `teleflow/gateway/main.py:135-142`, `helm/teleflow/values.yaml:75-77`; `teleflow/gateway/main.py:127-134`; `.venv/Lib/site-packages/redis/_defaults.py:7-8`. `(inferencia)` latencia por request con Redis en blackhole. |
| Un header `X-TeleFlow-API-Key` con bytes no ASCII hace que `compare_digest` levante `TypeError` → 500 (se audita como 500). | baja | `teleflow/gateway/main.py:352`; headers decodificados latin-1 `.venv/Lib/site-packages/starlette/datastructures.py:548`. `(inferencia: documentacion de hmac.compare_digest, str solo ASCII)`. |
| `actor_name` de la auditoria es suplantable por nombre: se puede crear una key de DB llamada `bootstrap (env)` o `key inválida`. Lo distingue `actor_key_id` (nulo para bootstrap), pero el filtro `actor` de `/audit` es por nombre. | baja | `CrearKeyRequest` sin restriccion de nombre `teleflow/gateway/main.py:486-488`; `teleflow/gateway/auth.py:53`; `teleflow/gateway/main.py:231-232,455-456`. |
| `/docs`, `/redoc` y `/openapi.json` publicos (mapa completo de la API) y Swagger UI cargado desde `cdn.jsdelivr.net` con major flotante `@5` y sin SRI, en el mismo origen donde el operador pega la key en "Authorize". | baja | `teleflow/gateway/main.py:39,73-78`; terceros `.venv/Lib/site-packages/fastapi/openapi/docs.py:79,92,236`. |
| review-ui: la key vive en `localStorage` sin vencimiento y el nginx no manda CSP ni headers de seguridad; en compose se publica en 3100 sin TLS. No se encontro sink de XSS (busqueda `dangerouslySetInnerHTML\|innerHTML` en `review-ui/src`: sin coincidencias). | baja | `review-ui/src/api.js:6`; `review-ui/src/App.jsx:25,141`; `review-ui/nginx.conf.template:6-49` (sin `add_header`); `docker-compose.yml:158-159`. |
| Gateway sin headers de seguridad (`X-Content-Type-Options`, `Cache-Control: no-store` en respuestas con secretos de `/keys`). | baja | Busqueda `X-Content-Type\|Strict-Transport\|add_header` en el repo: sin coincidencias; `teleflow/gateway/main.py:513-519,570-576`. |
| `OPTIONS` saltea auth, rate limit y auditoria en cualquier ruta. `(inferencia)` sin handler de OPTIONS termina en 405, sin efecto. | baja | `teleflow/gateway/main.py:149,184`. |
| CLI: default `http://localhost:8000` y `dev-key-change-me`; no advierte si `TELEFLOW_URL` es `http://` remoto (key en claro). | baja | `teleflow/cli.py:3-5,30-37`. |
| Imagen por tag, no por digest. | baja | `helm/teleflow/values.yaml:1-4`; `helm/teleflow/templates/deployments.yaml:41`. |

## Datos personales

- **El gateway no persiste cuerpos**: ni en `audit_log` (`teleflow/common/models.py:257-258`) ni en logs; los
  logs de keys llevan nombre y scopes (`teleflow/gateway/main.py:512,541,569`).
- **Path y subject de `audit_log` pueden llevar un identificador personal.** `entity_id` lo
  elige el cliente (`teleflow/executor_service/entities.py:125`) y el ejemplo del propio
  gateway es `/entities/socio/12345` (`teleflow/gateway/main.py:214`); si el organismo usa la cedula como id
  `(inferencia)`, queda en `audit_log.path`/`subject` (`teleflow/gateway/main.py:235-236`) en toda escritura y
  todo 401/403/429, en `log.error("audit_write_failed", path=...)` (`teleflow/gateway/main.py:247-248`) y es
  legible con `audit:read` (`teleflow/gateway/main.py:471-481`). La query string no se guarda.
- **`audit_log.details`**: hoy solo version y checksum; nada impide meter datos personales
  (anotado en `wiki/Knowledge/backlog-hardening.md:207-209`).
- **Fuga por el path traversal** (hueco alto): `GET /instances/{id}` devuelve `context`
  (`teleflow/executor_service/main.py:147`), que contiene el payload del expediente, a una key de
  `entities:read`; esa lectura no se audita (`teleflow/gateway/main.py:204-205`).
- **A donde viaja**: gateway → servicios internos en claro (`README.md:362-365`); gateway →
  Redis solo el hash de la key (`teleflow/gateway/main.py:128`). No va a RabbitMQ ni a un LLM desde este modulo.
- **Retencion**: `audit_log` crece sin purga automatica, decision del ADR
  (`wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:100-102`).

## Secretos y configuracion

- **Variables del modulo**: `TELEFLOW_API_KEY` (default `dev-key-change-me`, `teleflow/common/config.py:18`),
  `TELEFLOW_API_KEY_SCOPES` (default `*`, `teleflow/common/config.py:23`), `API_KEY_CACHE_TTL` (30,
  `teleflow/common/config.py:26`), `RATE_LIMIT_RPM` (120, `teleflow/common/config.py:93`), `REDIS_URL`, `DATABASE_URL`, las URL
  internas (`teleflow/common/config.py:29-33`) y `COMPOSE_TIMEOUT` (`teleflow/common/config.py:58`).
- **Compose**: todos con default por `${VAR:-...}` (`docker-compose.yml:3-26`), incluida la key
  publica de desarrollo y `teleflow:teleflow` en `DATABASE_URL`/`RABBITMQ_URL`
  (`docker-compose.yml:4,6`). `.env.example:4` repite el default.
- **Chart**: `TELEFLOW_API_KEY` por `secretKeyRef` del Secret propio o de `existingSecret`
  (`helm/teleflow/templates/_helpers.tpl:12-14,267-271`); `helm/teleflow/values-production.yaml:32` espera `existingSecret`. Con
  `apiKey` en values el valor queda en el archivo (`helm/teleflow/templates/secrets.yaml:47-48`, advertido en
  `helm/teleflow/values-production.yaml:30-31`). `TELEFLOW_API_KEY_SCOPES`, `API_KEY_CACHE_TTL` y
  `RATE_LIMIT_RPM` no se setean → defaults de codigo; se pueden agregar por `env`
  (`helm/teleflow/templates/_helpers.tpl:245-248`). Contraseñas de la capa de datos propia en values en texto plano
  (`helm/teleflow/values.yaml:225,271`), limite ya documentado (`helm/teleflow/values-production.yaml:91-94`).
- **Secretos en respuestas**: el secreto de una key nueva o rotada viaja en el cuerpo de la
  respuesta (`teleflow/gateway/main.py:517,574`), y por el hueco del composer puede terminar en la respuesta de
  una aprobacion (`teleflow/composer_service/main.py:195`).
- **Secretos en logs/errores**: no se encontro logueo de la key en el gateway (busqueda de
  llamadas `log.` en `teleflow/gateway/main.py`: `60,140,247,299,313,328,334,373,512,541,569,651`;
  ninguna incluye `api_key` ni `secreto`). El 403 nombra el scope faltante, no la key
  (`teleflow/gateway/auth.py:125-128`). El error del composer al aprobar reenvia el cuerpo del gateway
  (`teleflow/composer_service/main.py:180-185`).
- **Key de servicio compartida**: el composer usa la misma `TELEFLOW_API_KEY` de bootstrap
  (`teleflow/composer_service/main.py:176`); no hay key de servicio propia con scopes acotados.

## Impacto en despliegue

- **As-built, sin cambios**: migraciones `0002` y `0004` son `create_table` aditivas
  (`alembic/versions/0002_api_keys.py:17-31`, `alembic/versions/0004_audit_log.py:17-34`).
- **Replicas**: el gateway corre con 2 (`helm/teleflow/values.yaml:75-77`). Rate limit y revocacion ya no
  asumen proceso unico (Redis, `teleflow/gateway/main.py:115-142,280-335`; ADR
  `wiki/Knowledge/decisions/2026-07-25-estado-compartido-gateway.md:77-80`). Redis es replica
  unica: su caida **degrada** (limite por proceso, revocacion al TTL), decision registrada
  (`helm/teleflow/values.yaml:243-249`).
- **Compose**: gateway publicado en 8000 y review-ui en 3100, sin TLS (`docker-compose.yml:148-149,158-159`).
- **Helm**: Service `ClusterIP` + Ingress opt-in con guarda de TLS (`helm/teleflow/templates/ingress.yaml:16,41-57`),
  que publica todo el gateway incluidas `/metrics` y `/docs` (`helm/teleflow/templates/ingress.yaml:62-63`). Faltan
  NetworkPolicy, PDB y `securityContext` (`helm/teleflow/templates/datos.yaml:14-15`). Limites `256Mi`/`512Mi` sin tope
  de CPU (`helm/teleflow/templates/deployments.yaml:62-67`).
- **TLS interno**: gateway → servicios en claro, limite consciente (`README.md:362-365`); la
  key no viaja hacia adentro (el proxy no la reenvia, `teleflow/gateway/main.py:417-418`), salvo en la llamada
  composer → gateway (`teleflow/composer_service/main.py:173-176`).
- **Instalable por organismo sin overrides**: si, con los inputs que el chart exige a proposito
  (`apiKey` o `existingSecret`, y `tls` o `allowInsecure` si se enciende el Ingress:
  `helm/teleflow/templates/secrets.yaml:36-39`, `helm/teleflow/templates/ingress.yaml:55-57`) (`spec/constitution/mission.md:23-26`). Ningun
  hueco listado exige override para instalar; si exigen trabajo para endurecer.
