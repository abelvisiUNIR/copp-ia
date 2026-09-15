---
project: copp-ia
type: seguridad
status: implementada
feature: base-composer-ia
provenance: copp-ia@devyos@ffd585d
reviewed: 2026-09-14
---

# Seguridad e infraestructura — Base del composer IA

> Linea base as-built. Provenance: `copp-ia@devyos@ffd585d`. Alcance:
> `teleflow/composer_service/main.py`, `teleflow/composer_service/providers.py`, las rutas del
> gateway hacia `/compose` y `/drafts` con sus scopes (`teleflow/gateway/main.py`,
> `teleflow/gateway/auth.py`), la tabla `flow_drafts` (`teleflow/common/models.py`, migraciones
> `alembic/versions/0001`, `0003`, `0007`) y la configuracion LLM (`teleflow/common/config.py`,
> `.env.example`, `docker-compose.yml`, `helm/teleflow/`). Donde un hallazgo depende de un
> consumidor fuera de ese alcance (executor, review-ui, CLI) se cita igual y se marca como
> frontera. Las citas a httpx apuntan a la libreria instalada en `.venv/Lib/site-packages/httpx/`
> (codigo de terceros, version 0.28.1 segun `httpx-0.28.1.dist-info`).

## Superficie expuesta

| Superficie | Quien puede llegar | Control | Fuente |
|---|---|---|---|
| `POST /compose` (gateway :8000) | cliente con key valida | scope `compose:write` + rate limit por key; timeout hacia el composer 660 s | `teleflow/gateway/main.py:775-781`, `teleflow/gateway/main.py:145-163`, `teleflow/common/config.py:58` |
| `GET /drafts` (gateway) | cliente con key valida | scope `compose:read` | `teleflow/gateway/main.py:784-788` |
| `GET /drafts/{rest:path}` (gateway) | cliente con key valida | scope `compose:read` | `teleflow/gateway/main.py:791-800` |
| `POST /drafts/{id}/approve` y `/reject` (gateway, via `/drafts/{rest:path}`) | cliente con key valida | scope `compose:write` (**no** `flows:deploy`) | `teleflow/gateway/main.py:795-800`; `teleflow/composer_service/main.py:163-217` |
| `PATCH /drafts/{id}/source` (gateway) | cliente con key valida | scope `flows:deploy` | `teleflow/gateway/main.py:803-816` |
| Todas las rutas del composer-service :8004 (`/compose`, `/drafts`, `/drafts/{id}`, `/approve`, `/reject`, `PATCH /source`) | cualquier pod/contenedor de la red interna | **ninguno** (sin auth, sin rate limit, sin auditoria) | `teleflow/composer_service/main.py:60,138,148,163,203,226` |
| `GET /health`, `/ready`, `/metrics` (composer) | red interna | ninguno (publicos por diseño) | `teleflow/common/observability.py:46-64` |
| `GET /docs`, `/openapi.json` (composer) | red interna | ninguno: `FastAPI(...)` sin `docs_url=None` `(inferencia: defaults de FastAPI)` | `teleflow/composer_service/main.py:50` |
| composer → proveedor LLM (`api.anthropic.com`, `api.openai.com` o `LLM_BASE_URL`) | salida del composer | `LLM_API_KEY` en header | `teleflow/composer_service/providers.py:276,281,311,316,345` |
| composer → parser-service `POST /parse` | interno | ninguno | `teleflow/composer_service/main.py:118-122` |
| composer → gateway `POST /flows/{draft.name}` al aprobar | interno | **key de bootstrap** (`TELEFLOW_API_KEY`) | `teleflow/composer_service/main.py:173-179` |
| review-ui (nginx `/api/`) → gateway | navegador del revisor | key del usuario leida de `localStorage`; timeouts 720 s (frontera: review-ui) | `review-ui/nginx.conf.template:30-47`; `review-ui/src/api.js:6,31-40` |
| CLI `tflow compose` / `drafts` / `approve` → gateway | operador con key | scopes del gateway (frontera: CLI) | `teleflow/cli.py:119-146` |
| Tabla `flow_drafts` | composer-service (y quien tenga `DATABASE_URL`) | — | `teleflow/common/models.py:174-207`; `alembic/versions/0001_initial.py:114-126`, `0003_draft_validation.py:17-27`, `0007_fuente_generada_del_borrador.py:16-27` |

Puerto del composer en despliegue: compose no publica puertos al host
(`docker-compose.yml:117-125`, sin `ports:`); Helm lo expone como `ClusterIP` con 1 replica
(`helm/teleflow/templates/deployments.yaml:77-81`, `helm/teleflow/values.yaml:92-95` sin
`external`).

## Controles existentes

- **Por default no sale nada hacia un LLM**: `llm_provider = "stub"` en la configuracion
  (`teleflow/common/config.py:36`), en compose (`docker-compose.yml:15`), en `.env.example:26`,
  en el chart (`helm/teleflow/values.yaml:27`) y en la plantilla de produccion
  (`helm/teleflow/values-production.yaml:35`). El stub no llama a nadie
  (`teleflow/composer_service/providers.py:375-408`).
- **Un proveedor real sin credencial no arranca** en vez de caer al stub: `get_provider` levanta
  `LLMConfigurationError` (`providers.py:418-447`) y se invoca en el `lifespan`
  (`teleflow/composer_service/main.py:38-46`). El mensaje nombra la variable, no su valor
  (`providers.py:434-438`).
- **`LLM_API_KEY` viaja solo en header**, nunca en URL ni en payload (`providers.py:281`,
  `providers.py:316`). Los unicos usos de `llm_api_key` en el codigo son esas asignaciones y el
  chequeo de vacia (busqueda `LLM_API_KEY|llm_api_key` fuera de `.venv`:
  `providers.py:274,309,434`, `config.py:37`, tests). El log de arranque registra el nombre del
  proveedor, no la credencial (`teleflow/composer_service/main.py:44`).
- **Separacion estructural del prompt**: las instrucciones van en el campo `system` (Anthropic)
  o en un mensaje con `role: system` (OpenAI, Ollama); el texto del analista va solo como
  mensaje `user` (`providers.py:285-286`, `providers.py:320-322`, `providers.py:355-357`). El
  system prompt pide explicitamente no escribir tokens, claves ni passwords en el `.tflow`
  (`providers.py:145-146`).
- **El cuerpo de error del proveedor se trunca a 500 caracteres** antes de usarlo en mensajes
  (`providers.py:232`).
- **Reintentos acotados**: solo 5xx/408/429 y red; los 4xx permanentes fallan en el primer
  intento (`providers.py:233-243`); el `ReadTimeout` no se reintenta (`providers.py:208-221`);
  espera topeada a `llm_retry_max_delay` (`providers.py:245-252`, `config.py:46-48`).
- **Techo de tokens de salida**: `llm_max_tokens` = 4096 (`config.py:43`), enviado en los tres
  proveedores reales (`providers.py:284,319,354`). Una respuesta truncada o vacia se rechaza en
  vez de guardarse (`providers.py:257-266`); el rechazo por politicas se distingue
  (`providers.py:295-297`).
- **La salida del modelo pasa por el parser antes de guardarse** y el veredicto queda en el
  borrador, incluido "no se pudo verificar" (`parses: None`) (`teleflow/composer_service/main.py:95`, `teleflow/composer_service/main.py:108-135`).
  No condiciona el guardado (`teleflow/composer_service/main.py:91-94`), pero **el deploy re-valida en el gateway** y un
  flow invalido corta con 422 antes del registry (`teleflow/gateway/main.py:613-629`); el
  borrador sigue `pending` (`teleflow/composer_service/main.py:180-185`).
- **El codigo generado no ejecuta Python**: lo que el modelo pueda escribir queda confinado a la
  gramatica y al evaluador de lista blanca del DSL (ver
  `spec/features/base-lenguaje-tflow/seguridad.md:39-48`).
- **Maquina de estados del borrador**: aprobar, rechazar y editar solo sobre `pending`
  (`teleflow/composer_service/main.py:169-170`, `teleflow/composer_service/main.py:209-210`, `teleflow/composer_service/main.py:253-254`); `draft_id` tipado `uuid.UUID` en
  todas las rutas (`teleflow/composer_service/main.py:149,164,204,227`).
- **Editar exige `flows:deploy`** en el gateway (`teleflow/gateway/main.py:803-816`, decision 5
  de `wiki/Knowledge/decisions/2026-08-27-correccion-del-borrador-en-la-revision.md:77-78`),
  revalida del lado del servidor y conserva lo que escribio el modelo en `source_generado`
  (`teleflow/composer_service/main.py:265-269`).
- **Auditoria**: `compose:write` y `flows:deploy` son scopes de escritura y se auditan siempre
  (`teleflow/gateway/auth.py:155-158,170`; `teleflow/gateway/main.py:199-207`). El proxy arma
  los headers desde cero: un cliente no puede colar headers hacia el composer
  (`teleflow/gateway/main.py:412-418`).
- **Cadena de timeouts ordenada** para que el error real no quede tapado: composer→LLM 600 s
  (Ollama) / 120 s (Anthropic, OpenAI) < gateway 660 s < nginx 720 s (`providers.py:288,326,366`;
  `config.py:49-58`; `review-ui/nginx.conf.template:37-47`).
- **El listado no devuelve fuentes** y esta topeado a 100 filas (`teleflow/composer_service/main.py:144-145`).
- **Migraciones aditivas**: `0003` y `0007` solo agregan columnas nullable, sin backfill
  (`0003_draft_validation.py:17-27`, `0007_fuente_generada_del_borrador.py:16-27`).

## Huecos

| Hueco | Severidad | Evidencia |
|---|---|---|
| **Aprobar despliega con `compose:write` y con la key de bootstrap: `flows:deploy` queda salteado.** La ruta `POST /drafts/{rest:path}` exige solo `compose:write`, y el composer despliega llamando al gateway con `TELEFLOW_API_KEY` (scopes `*` por default). Quien pide el borrador controla su contenido: manda un `base_source` arbitrario y una descripcion del tipo "no cambies nada" `(inferencia: depende de que el modelo obedezca, no se ejecuto)`. Una key de analista puede asi componer **y** aprobar codigo ejecutable sin `flows:deploy`. Contradice la decision que puso `flows:deploy` en la edicion "porque aprobar despliega" y el docstring que dice que una clave de analista "no puede reescribir lo que se despliega". Con el hueco de `${env.*}` (fila siguiente) escala a todos los scopes. Direccion: exigir `flows:deploy` en `approve` en el gateway y desplegar con la identidad del revisor, no con la key del servicio. | alta | Scope de approve `teleflow/gateway/main.py:795-800`; `COMPOSE_WRITE` descrito como "generar/aprobar borradores" `teleflow/gateway/auth.py:38`; deploy con key de bootstrap `teleflow/composer_service/main.py:173-179`; bootstrap con `*` `teleflow/common/config.py:23`, `teleflow/gateway/main.py:352-354`; `base_source` concatenado al prompt `teleflow/composer_service/main.py:65-68`; docstring `teleflow/gateway/main.py:808-814`; decision `wiki/Knowledge/decisions/2026-08-27-correccion-del-borrador-en-la-revision.md:77-78`. |
| **Prompt injection → flow valido que exfiltra secretos via `${env.*}` (frontera: executor).** La descripcion y el `base_source` van directo al mensaje `user`; el borrador resultante puede declarar una `integration` con `base_url` propio y `auth_header: "${env.TELEFLOW_API_KEY}"`, `${env.LLM_API_KEY}` o `${env.DATABASE_URL}`. El parser lo acepta (el `validator` no mira `IntegrationDef.config`) y el executor lo resuelve. Lo que **mitigan** parser + revision humana: salida sintacticamente invalida, texto que no es DSL, ejecucion de codigo arbitrario. Lo que **no** mitigan: un flow semanticamente malicioso y valido. El propio system prompt normaliza el patron `${env.VAR}` para credenciales, asi que esa linea se ve legitima en la revision; y el revisor puede ser la misma key que compuso (fila de arriba). El composer no inspecciona la salida (busqueda `env\.` en `composer_service/`: solo el system prompt). Ver `wiki/Knowledge/backlog-hardening.md` item 8 y `spec/features/base-lenguaje-tflow/seguridad.md:89`. Direccion: la restriccion va en el validator (`spec/features/restringir-env-en-integraciones/`); el composer puede marcar en la revision todo `${env.*}` generado. | alta | Prompt `teleflow/composer_service/main.py:65-68`, `providers.py:286,322,357`; patron sugerido `providers.py:145-146`; guardado sin filtro `teleflow/composer_service/main.py:97-101`; `teleflow/dsl/validator.py:128-136`; resolucion sin lista blanca `teleflow/executor_service/adapters.py:31,72,121-139`; `LLM_API_KEY` en el entorno de todos los servicios `docker-compose.yml:3,16,103-107`, `helm/teleflow/templates/_helpers.tpl:243-277`. |
| Datos personales hacia un proveedor externo sin ningun control. Con `LLM_PROVIDER=anthropic|openai`, la descripcion del analista y el `base_source` salen tal cual del organismo; no hay deteccion ni redaccion, ni aviso en la respuesta o en la UI de que el pedido viaja a un tercero. Ollama "deja los datos en la instalacion" solo si `LLM_BASE_URL` apunta a un host propio: el codigo no lo verifica y ni compose ni el chart traen un servicio Ollama. `(inferencia)` un analista describiendo un caso real puede pegar nombre, cedula o email. Direccion: advertencia explicita y/o filtro de patrones de identificadores antes de enviar a un proveedor no local. | media | Envio `providers.py:279-290`, `providers.py:314-327`; `base_url` libre `providers.py:276,311,345`; busqueda `ollama` en `*.yml/*.yaml`: solo comentarios (`helm/teleflow/values-production.yaml:35`); ADR-003 `wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:15-21`. |
| Se pierde el actor real del deploy. En `audit_log` el deploy queda a nombre de `bootstrap (env)`; la fila de la aprobacion (actor real, `compose:write`) no lleva flow, version ni checksum y nada la vincula con la del deploy. `actor_id` es texto libre sin verificar (la UI propone `dev`, el CLI `cli`) y solo va a `flow_drafts.comments` y al log. `FlowDraft` no guarda quien compuso: no hay forma de impedir que la misma key componga y apruebe. `POST /compose` se audita sin subject ni detalles (`/compose` tiene un solo segmento). Direccion: propagar la identidad de la key del revisor al deploy y enriquecer la auditoria con `draft_id` y version. | media | Key de servicio `teleflow/composer_service/main.py:176`; identidad de bootstrap `teleflow/gateway/main.py:352-354`, `teleflow/gateway/auth.py:53`; fila de auditoria `teleflow/gateway/main.py:226-239`; subject `teleflow/gateway/main.py:211-223`; `actor_id` libre `teleflow/composer_service/main.py:157-160,188-194`; default UI `review-ui/src/App.jsx:162-164` (frontera: review-ui); default CLI `teleflow/cli.py:220` (frontera: CLI); sin columna de autor `teleflow/common/models.py:174-207`; el vinculo solo queda en la descripcion del registry `teleflow/composer_service/main.py:178`. |
| `draft.name` sin validar se interpola en la URL del deploy que se hace con la key de bootstrap. httpx normaliza los segmentos `..`, asi que un borrador llamado `../instances/<uuid>/retry` convierte la aprobacion en un `POST` a otra ruta del gateway con scopes `*`. `/instances/{id}/retry` no lee body, por lo que el cuerpo fijo del deploy no lo frena. `(inferencia: camino leido en el codigo, no ejecutado)` Direccion: validar `name` como identificador del DSL en `ComposeRequest` y codificar el segmento. | media | `name: str` libre `teleflow/composer_service/main.py:55`; interpolacion `teleflow/composer_service/main.py:175`; normalizacion `.venv/Lib/site-packages/httpx/_urlparse.py:327-329,447-470` (terceros, httpx 0.28.1); ruta destino `teleflow/gateway/main.py:721-726`, `teleflow/executor_service/main.py:184-187`; `POST /keys` exige `name` y `scopes` y rechazaria el body `teleflow/gateway/main.py:486-493`. |
| composer-service sin auth propia y alcanzable directo desde la red interna: cualquier contenedor puede listar borradores (descripciones con posibles datos personales), editarlos sin `flows:deploy` y aprobarlos, y la aprobacion despliega con la key de bootstrap. No hay NetworkPolicy en el chart. | media | Rutas sin dependencia de auth `teleflow/composer_service/main.py:60-61,138-140,163-165,226-228`; `ClusterIP` `deployments.yaml:77-81`; busqueda `NetworkPolicy` en `helm/`: solo el comentario `helm/teleflow/templates/datos.yaml:15`; compose sin `ports:` `docker-compose.yml:117-125` `(inferencia: red default de compose, visible para todo contenedor del stack)`. |
| Sin limite de tamaño en ninguna entrada. `name`, `description`, `base_source` (compose) y `source` (edicion) sin `max_length`; el gateway lee el body entero. El prompt no tiene tope, asi que el costo de tokens de entrada lo decide el cliente. `name` es `String(200)` en la base: uno mas largo falla en el `commit`, **despues** de pagar la generacion, y termina en 500. | media | `teleflow/composer_service/main.py:54-57`, `teleflow/composer_service/main.py:220-223`; body completo `teleflow/gateway/main.py:416`; columna `models.py:180`, `0001_initial.py:117`; orden generar→guardar `teleflow/composer_service/main.py:72,97-101`; busqueda `max_length|Field\(` en `composer_service/`: sin coincidencias; limite de memoria 512Mi `deployments.yaml:66-67`. |
| DoS economico del LLM: el unico freno es el rate limit generico por key (120 rpm, igual para todas las rutas). No hay cuota ni presupuesto por `/compose`, ni tope de concurrencia en el composer, y cada pedido puede hacer hasta 3 intentos contra el proveedor. `.env.example` sube el limite a 1200 rpm y compose lo toma de ahi. Varias keys con `compose:write` multiplican el limite. Direccion: limite propio y mas bajo para `/compose` y semaforo de concurrencia en el composer. | media | `teleflow/gateway/main.py:115-142`; `config.py:93`; `.env.example:61`, `docker-compose.yml:26`; reintentos `config.py:46`, `providers.py:200-254`; busqueda `Semaphore|Limits` en `composer_service/`: sin coincidencias. |
| Agotamiento del pool del gateway: todas las rutas proxean por un unico `httpx.AsyncClient` con el limite default de 100 conexiones, y `/compose` retiene la suya hasta 660 s. Con ~100 composiciones lentas en curso (alcanzable con una key a 120 rpm) el resto de las rutas espera pool y cae en 502 `(inferencia: no se ejecuto)`. Direccion: cliente separado con limite propio para el composer. | media | Cliente unico `teleflow/gateway/main.py:51`; uso compartido `teleflow/gateway/main.py:404,420-429`; `compose_timeout` `config.py:58`; defaults de httpx `.venv/Lib/site-packages/httpx/_config.py:247`, `.venv/Lib/site-packages/httpx/_client.py:1368` (terceros, httpx 0.28.1). |
| `LLM_API_KEY` llega al entorno de los seis servicios Python aunque solo la usa el composer, y con el hueco de `${env.*}` es exfiltrable desde el executor (frontera: executor). En Helm, `llmApiKey` puede ir en `values.yaml` en texto plano. | media | `docker-compose.yml:3,16` (ancla compartida) y `:86-88,96-98,106-107,120-122,135-137,145-147`; `_helpers.tpl:272-277` dentro de `teleflow.env` usado por todos `deployments.yaml:46-47`; `values.yaml:15`, `secrets.yaml:49-51`. |
| Borradores sin retencion ni borrado: `description`, `source`, `base_source` y `comments` quedan indefinidamente en `flow_drafts` (no hay ruta `DELETE` ni tarea de purga). `GET /drafts` es lectura y no se audita, asi que no queda registro de quien leyo descripciones. | media | Rutas del composer `teleflow/composer_service/main.py:60,138,148,163,203,226` (ninguna borra); lecturas no auditadas `teleflow/gateway/main.py:204-205`, `auth.py:163-165`; `description` en el listado `teleflow/composer_service/main.py:283`. |
| El cuerpo de error del proveedor (hasta 500 caracteres) vuelve al cliente en el `detail` del 422/500/502 y se loguea, incluido en cada reintento. `(inferencia: comportamiento de terceros)` algunos proveedores devuelven en el 401 un fragmento enmascarado de la key, o repiten parte del pedido en el error. Tambien expone al analista detalles de la instalacion (modelo, ruta). | baja | `providers.py:232-242`; log de reintento `providers.py:250-251`; `teleflow/composer_service/main.py:73-83`; el gateway reenvia el cuerpo tal cual `teleflow/gateway/main.py:432-433`. |
| Sin validacion de esquema de `LLM_BASE_URL`: un `http://` manda `LLM_API_KEY` y el prompt en claro. El default de Ollama es `http://ollama:11434`. | baja | `providers.py:276,311,345`; TLS interno como limite consciente `README.md:362-365`. |
| Con Ollama, el peor caso del composer (3 intentos de hasta 600 s + esperas) supera los 660 s del gateway y los 720 s de nginx: el cliente recibe 502/504 mientras el composer sigue y guarda el borrador igual `(inferencia: Starlette no cancela el handler al cortarse el cliente; no se ejecuto)`. Con Anthropic/OpenAI el peor caso (3 × 120 s + 2 × 20 s = 400 s) queda dentro. | baja | `providers.py:200-254,366`; `config.py:46-48,58`; `review-ui/nginx.conf.template:45-47`. |
| Aprobaciones y ediciones concurrentes sin bloqueo de fila: dos `approve` simultaneos pasan el chequeo de `pending` y despliegan los dos; un `approve` y un `PATCH` concurrentes se pisan `comments` (se pierde una entrada del historial). | baja | Chequeo sin lock `teleflow/composer_service/main.py:166-170,250-254`; reescritura de la lista completa `teleflow/composer_service/main.py:188-191,270-272`; busqueda `with_for_update` en `teleflow/`: solo `executor_service/entities.py`, `engine.py`. |
| El stub copia la descripcion del analista como comentarios en la fuente: si ese borrador se aprueba, la descripcion (con lo que contenga) queda persistida en `flow_definitions` a traves del deploy. | baja | `providers.py:385-389`; deploy de `draft.source` `teleflow/composer_service/main.py:177`; persistencia de la fuente `teleflow/gateway/main.py:632-641`. |
| Contenedor como root y sin `securityContext`; composer con 1 replica y sin PDB; `/docs` y `/openapi.json` habilitados; imagen por tag. | baja | `Dockerfile:3-16` sin `USER`; `deployments.yaml:36-67` (busqueda `securityContext|runAsNonRoot|PodDisruptionBudget` en `helm/`: solo el comentario de `datos.yaml:15`); `values.yaml:92-95`; `teleflow/composer_service/main.py:50`; `values.yaml:2-4`. |
| Downgrade con perdida: `0007` borra `source_generado` y `0003` borra `validation`/`provider`, sin respaldo previo. | baja | `0007_fuente_generada_del_borrador.py:30-31`; `0003_draft_validation.py:30-32`. |

## Datos personales

- **Que entra**: texto libre del analista (`description`) y un `.tflow` de base (`base_source`)
  (`teleflow/composer_service/main.py:54-57`). El modulo no clasifica ni filtra ese texto (busqueda: no hay validacion de
  contenido en `teleflow/composer_service/main.py`). `(inferencia)` en govtech es esperable que una descripcion traiga un
  caso concreto (nombre, cedula, email); un `.tflow` declara esquema, no valores
  (`spec/features/base-lenguaje-tflow/seguridad.md:105-111`).
- **Donde se persiste**: tabla `flow_drafts` — `description`, `source`, `base_source`,
  `source_generado` como `Text`, y `comments` (JSONB) con `actor_id` y comentario libres
  (`models.py:180-194`; `0001_initial.py:114-126`; `0007_fuente_generada_del_borrador.py:24-27`).
  Sin retencion ni borrado (ver huecos). Al aprobar, `draft.source` pasa al registry
  (`teleflow/composer_service/main.py:177`); con el stub eso incluye la descripcion (`providers.py:385-389`).
- **A donde viaja**:
  - **LLM externo**, si `LLM_PROVIDER` es `anthropic` u `openai`: `description` + `base_source`
    completos (`teleflow/composer_service/main.py:65-68`; `providers.py:279-290,314-327`). Con `ollama` va a
    `LLM_BASE_URL`, que el codigo no obliga a ser local (`providers.py:345`). Con `stub` (el
    default) no sale (`providers.py:385-408`).
  - **parser-service**: la fuente generada o editada, en claro por la red interna
    (`teleflow/composer_service/main.py:118-122`; `README.md:362-365`).
  - **Respuestas HTTP**: `GET /drafts` devuelve `description` de hasta 100 borradores a toda key
    con `compose:read` (`teleflow/composer_service/main.py:144-145,283`).
  - **Logs**: los eventos exitosos registran `flow_name`, `draft_id`, `provider`, `version` y
    `actor_id`, no la descripcion ni la fuente (`teleflow/composer_service/main.py:103-104,193-194,216,274-275`). En error
    se loguea el cuerpo de respuesta del proveedor truncado a 500 caracteres
    (`providers.py:232,250-251`; `teleflow/composer_service/main.py:74,79,82`) `(inferencia: puede incluir fragmentos del
    pedido si el proveedor los repite)`. Un fallo del parser loguea `str(exc)` de httpx
    (`teleflow/composer_service/main.py:128`), sin la fuente.
  - **RabbitMQ**: no; el modulo no publica eventos (busqueda: sin import de bus en
    `composer_service/`).
- **`audit_log`**: registra metodo, path, subject, scope y status de `POST /compose`,
  `/approve`, `/reject` y `PATCH /source` (`teleflow/gateway/main.py:226-239`); `details` solo lo
  llena el deploy con version y checksum (`teleflow/gateway/main.py:612,624`). No guarda la
  descripcion ni la fuente.

## Secretos y configuracion

- **`LLM_API_KEY`**: sale de la variable de entorno leida por `pydantic-settings`
  (`config.py:8,37`). En compose, `${LLM_API_KEY:-}` dentro del ancla comun a todos los servicios
  (`docker-compose.yml:3,16`); en `.env.example` vacia (`.env.example:27`). En Helm,
  `secretKeyRef` opcional al Secret de la instancia (`_helpers.tpl:272-277`), que viene de
  `existingSecret` o lo crea el chart desde `llmApiKey` (`values.yaml:15-16`,
  `secrets.yaml:47-51`); la plantilla de produccion pide `existingSecret`
  (`values-production.yaml:23-32`). No se encontro logueo de la credencial (busqueda
  `llm_api_key` en `teleflow/`: solo `providers.py:274,309,434` y `config.py:37`); los mensajes
  de error nombran la variable, no el valor (`providers.py:234-235,436-438`). Riesgos: llega al
  entorno de todos los servicios y un 401 del proveedor puede reflejar un fragmento (huecos).
- **`TELEFLOW_API_KEY`** (usada por el composer para desplegar): default de desarrollo
  `dev-key-change-me` en `config.py:18`, `docker-compose.yml:7` y `.env.example:4`, con scopes
  `*` (`config.py:23`, `docker-compose.yml:8`, `.env.example:9`). El chart falla si no se define
  `apiKey` ni `existingSecret` (`secrets.yaml:36-39`). El CLI tambien cae a `dev-key-change-me`
  (`teleflow/cli.py:32`, frontera: CLI).
- **Otras variables LLM**: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL` pasan por compose
  (`docker-compose.yml:15-18`). `LLM_MAX_TOKENS`, `LLM_RETRY_*` y `COMPOSE_TIMEOUT` **no**
  figuran en el bloque de compose, y el `Dockerfile` no copia `.env`
  (`Dockerfile:7-10`): `(inferencia)` en el stack de compose rigen los defaults de `config.py`
  aunque se editen en `.env`. El chart solo trae `LLM_PROVIDER` en `env` (`values.yaml:26-28`).
- **Errores**: el `detail` de 422/500/502 del composer incluye el mensaje del proveedor
  (`teleflow/composer_service/main.py:75,80,83`); el de configuracion menciona `LLM_MODEL`/`LLM_BASE_URL`
  (`providers.py:237-239`), no valores secretos.
- **Documentacion desactualizada**: `docs/teleflow-adr.typ:137` y
  `wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:29-30` dicen que sin
  `LLM_API_KEY` el servicio cae al stub; el codigo ya no lo hace (`providers.py:418-439`). Manda
  el codigo.

## Impacto en despliegue

- **As-built, sin cambios**: el estado del composer es la tabla `flow_drafts` (migraciones
  `0001`, `0003`, `0007`, todas aditivas hacia adelante). No hay estado en memoria compartido
  entre requests: el proveedor se construye por request (`teleflow/composer_service/main.py:64`) `(inferencia: escalar a
  mas replicas no rompe nada, pero agrava la carrera de aprobaciones concurrentes)`.
- **Compose**: `composer-service` sin puertos publicados, depende solo de `migrate`
  (`docker-compose.yml:117-125`); el gateway depende de el (`docker-compose.yml:150-154`). No
  hay servicio Ollama.
- **Helm**: Deployment + Service `ClusterIP` genericos con 1 replica (`values.yaml:92-95`,
  `deployments.yaml:1-89`), limites `256Mi`/`512Mi` sin limite de CPU
  (`deployments.yaml:62-67`). Faltan NetworkPolicy, PDB y `securityContext` (ver huecos).
- **Egress**: con proveedor externo el pod necesita salida a Internet hacia la API del
  proveedor; el chart no declara nada sobre egress (busqueda `NetworkPolicy|egress` en `helm/`:
  sin coincidencias salvo el comentario de `datos.yaml:15`).
- **Timeouts de borde**: la cadena 600/660/720 s vive en el codigo y en la imagen del review-ui
  (`review-ui/nginx.conf.template:45-47`). `(inferencia)` un Ingress o balanceador del organismo
  delante con timeout menor corta `/compose` antes; el chart no lo documenta en `values.yaml`.
- **TLS interno**: composer → parser y composer → gateway en claro, limite consciente
  (`README.md:362-365`); por ahi viajan la fuente y la key de bootstrap.
- **Instalable por organismo sin overrides**: si (`spec/constitution/mission.md:23-26`). El
  default `stub` no requiere credenciales ni egress; elegir proveedor real u Ollama es
  configuracion por organismo (ADR-003). Ningun hueco listado exige override para instalar; si
  exigen trabajo para endurecer.
