---
project: copp-ia
type: seguridad
status: implementada
feature: base-review-ui
provenance: copp-ia@devyos@ffd585d
reviewed: 2026-09-14
---

# Seguridad e infraestructura — Base de la review-ui

> Linea base as-built. Provenance: `copp-ia@devyos@ffd585d`. Alcance: `review-ui/src/*.jsx`,
> `review-ui/src/api.js`, `review-ui/src/diff.js`, `review-ui/nginx.conf.template`,
> `review-ui/Dockerfile`, `review-ui/vite.config.js`, `review-ui/index.html`,
> `review-ui/package.json` y `review-ui/package-lock.json` (solo versiones; `node_modules` no se
> leyo), servicio `review-ui` de `docker-compose.yml`, `helm/teleflow/templates/review-ui.yaml`,
> `helm/teleflow/templates/ingress.yaml` y `helm/teleflow/values.yaml`. Los dos huecos altos caen
> en el composer y el gateway, pero los habilita el boton "Aprobar y desplegar" de esta UI: se
> citan y se marcan `(frontera: ...)`. La cita a httpx apunta a la libreria instalada
> `.venv/Lib/site-packages/httpx/` (codigo de terceros, version 0.28.1 segun
> `httpx-0.28.1.dist-info`).

## Superficie expuesta

La UI no tiene backend propio: sirve estaticos y reenvia `/api/*` al gateway con la key que
escribio el usuario. Toda autorizacion la hace el gateway.

| Superficie | Quien puede llegar | Control | Fuente |
|---|---|---|---|
| `GET /` y estaticos (nginx :80) | quien alcance el puerto: host `:3100` en compose; `ClusterIP` o port-forward en Helm | ninguno (bundle publico) | `review-ui/nginx.conf.template:6-15`; `docker-compose.yml:156-161`; `helm/teleflow/templates/review-ui.yaml:58-64` |
| `/api/*` → gateway (proxy nginx) | quien alcance el puerto de la UI | **ninguno propio**: reescribe `/api/x` a `/x` y reenvia; el header `X-TeleFlow-API-Key` del cliente viaja tal cual `(inferencia: default de nginx de pasar los headers del request)` | `review-ui/nginx.conf.template:30-35`; `review-ui/src/api.js:3-8` |
| `/api/health`, `/api/ready`, `/api/metrics`, `/api/docs`, `/api/openapi.json`, `/api/redoc` | quien alcance el puerto de la UI | ninguno (publicos en el gateway) | `teleflow/gateway/main.py:39,149-150` |
| `GET /drafts`, `GET /drafts/{id}` | usuario de la UI con key | `compose:read` | `review-ui/src/api.js:27-28`; `teleflow/gateway/main.py:784-800` |
| `POST /compose` | usuario con key | `compose:write`; timeout extendido | `review-ui/src/api.js:29-30`; `teleflow/gateway/main.py:775-781` |
| `POST /drafts/{id}/approve` (**despliega**) y `/reject` | usuario con key | `compose:write` (no `flows:deploy`) | `review-ui/src/api.js:31-34`; `teleflow/gateway/main.py:795-800` |
| `PATCH /drafts/{id}/source` | usuario con key | `flows:deploy` | `review-ui/src/api.js:39-40`; `teleflow/gateway/main.py:803-816` |
| `GET /flows`, `GET /flows/{name}/latest` | usuario con key | `flows:read` (`latest` entra por `/flows/{name}/{version}`) | `review-ui/src/api.js:41-48,63-64`; `teleflow/gateway/main.py:664-678` |
| `POST /execute` | usuario con key | `instances:trigger` | `review-ui/src/api.js:72-73`; `teleflow/gateway/main.py:686-687` |
| `GET /instances[/{id}]`, `POST .../signal`, `POST .../retry` | usuario con key | `instances:read` / `:signal` / `:retry` | `review-ui/src/api.js:95-100`; `teleflow/gateway/main.py:699-726` |
| `GET /domain`, `/entities/*`, `/relations/*` (incluye vista 360) | usuario con key | `entities:read` (GET) / `entities:write` (POST, PATCH) | `review-ui/src/api.js:68,80-93`; `teleflow/gateway/main.py:729-770` |
| `localStorage` del navegador: `tflow_api_key`, `tflow_actor` | cualquier script que corra en el origen de la UI | ninguno | `review-ui/src/App.jsx:25,139-142`; `review-ui/src/ops.jsx:38,71-74`; `review-ui/src/dominio.jsx:74,92` |
| Servidor de desarrollo `vite` :3100 → `http://localhost:8000` | quien lo levante en su maquina | solo dev, no va en la imagen | `review-ui/vite.config.js:7-15`; `review-ui/Dockerfile:22` (solo copia `dist`) |

Exposicion: compose publica la UI en todas las interfaces del host, en HTTP
(`docker-compose.yml:158-159`). El chart la crea habilitada por default (`helm/teleflow/values.yaml:166-169`)
como `ClusterIP` (`helm/teleflow/templates/review-ui.yaml:58-59`) y **sin Ingress**: el unico Ingress es el del gateway
(`helm/teleflow/templates/ingress.yaml:16-69`), y el comentario del chart dice que la UI "no se publica: se accede por
port-forward o se agrega otro Ingress cuando haya una decision de dominio" (`helm/teleflow/templates/ingress.yaml:12-14`).
El codigo deja la decision abierta a proposito: "hoy `review-ui` no se expone justamente porque
desde aca se despliega codigo, y la seccion operativa es la que necesitaria ser alcanzable. Esa
decision es de exposicion, no de codigo, y va con su ADR" (`review-ui/src/App.jsx:14-16`). No se
encontro ese ADR (busqueda `review-ui|compose:write` en `wiki/Knowledge/decisions/`: solo una
mencion de `compose:write` en `wiki/Knowledge/decisions/2026-07-25-auditoria-persistida.md:37`, que no trata la exposicion).

## Controles existentes

- **No hay render de HTML desde datos** (confirmado). No se encontraron `dangerouslySetInnerHTML`,
  `innerHTML`, `eval(`, `new Function`, `document.write`, `href=` dinamicos, `window.open` ni
  librerias de markdown en `review-ui/src`, `review-ui/index.html`, `review-ui/vite.config.js` ni la plantilla de
  nginx (busqueda:
  `dangerouslySetInnerHTML|innerHTML|eval\(|new Function|document\.write|href=|window\.open|marked|markdown`).
  `package.json` solo declara `react` y `react-dom` como dependencias de runtime
  (`review-ui/package.json:13-16`).
- **Todo dato del backend se pinta como texto JSX**, que React escapa: la fuente `.tflow` en el
  diff (`review-ui/src/App.jsx:499-507`), los mensajes del parser con fragmentos de fuente en `<pre>`
  (`review-ui/src/App.jsx:332-335`), nombre, estado y descripcion del borrador (`review-ui/src/App.jsx:236-242,253-265`), el
  error del parser (`review-ui/src/App.jsx:365-368`), los banners de error del backend (`review-ui/src/App.jsx:213-214`,
  armados como string en `review-ui/src/api.js:16-22`), el error y la linea de tiempo de una instancia con su
  `actor_id` (`review-ui/src/ops.jsx:344-362,371-378`), los campos de la ficha 360 via `String(v)`
  (`review-ui/src/dominio.jsx:400-412`), alertas e historia (`review-ui/src/dominio.jsx:213-233`). Los formularios generados
  desde el AST usan nombres de campo y `enum_values` como texto y `value` de `<option>`
  (`review-ui/src/ops.jsx:282-321`, `review-ui/src/dominio.jsx:461-491`). Los `className` interpolados con estado
  (`review-ui/src/App.jsx:237`, `review-ui/src/ops.jsx:143`) son atributos que React asigna como propiedad, no HTML.
  Los comentarios de los borradores (`draft.comments`) no se muestran en la UI (busqueda
  `comments` en `review-ui/src`: sin coincidencias).
- **El corte de permisos lo hace el gateway, no la pantalla**: cada llamada viaja con la key del
  usuario (`review-ui/src/api.js:3-8`) y cada ruta exige su scope (ver tabla de superficie). La UI no lleva
  ninguna key horneada (`review-ui/src/api.js:1-8`; unica lectura de credencial en `src` es `localStorage`,
  busqueda `localStorage` en `review-ui/src`).
- **El gateway reenvia a los servicios internos armando los headers desde cero**, asi que nada
  que el navegador agregue a un request de la UI llega a los servicios core
  (`teleflow/gateway/main.py:409-418`).
- **Toda escritura hecha desde la UI queda en `audit_log` con la identidad de la key** (nombre e
  id), no con el `actor_id` que escribe el usuario (`teleflow/gateway/main.py:226-239`;
  `teleflow/gateway/auth.py:155-158,170`).
- **Campo de key enmascarado**: `type="password"` (`review-ui/src/App.jsx:204-210`).
- **Aprobar un borrador sin guardar o que no compila exige confirmacion** explicita
  (`review-ui/src/App.jsx:148-159`), y el deploy igual lo revalida el gateway contra el parser antes de
  registrar (frontera: `teleflow/gateway/main.py:604-605`, detalle en
  `spec/features/base-lenguaje-tflow/seguridad.md:68-69`). Editar la fuente exige `flows:deploy`
  (`teleflow/gateway/main.py:803-815`).
- **Build reproducible**: `npm ci` sobre `review-ui/package-lock.json` versionado
  (`review-ui/Dockerfile:3-9`); `node_modules` y `dist` fuera del contexto
  (`review-ui/.dockerignore:4-5`). Versiones resueltas en el lock: `react` y `react-dom` 18.3.1
  (`review-ui/package-lock.json:1523-1524,1536-1537`), `vite` 5.4.21 (`:1664-1665`),
  `@vitejs/plugin-react` 4.7.0 (`:1169-1170`), `esbuild` 0.21.5 (`:1291-1292`), `rollup` 4.62.2
  (`:1559-1560`), `@playwright/test` 1.62.0 (`:744-745`).
- **Imagen final multi-stage**: solo `dist` llega a la imagen nginx; tests, `demo/`, lockfile y
  toolchain de Node quedan en la etapa de build (`review-ui/Dockerfile:1-11,13,22`).
- **Sin source maps en el build de produccion** `(inferencia: default de Vite 5,
  `build.sourcemap: false`)`: `review-ui/vite.config.js:5-17` no declara bloque `build`. No se verifico
  contra un `dist` generado.
- **Un gateway caido no tumba la UI**: upstream por variable con `resolver`, se resuelve por
  request y devuelve 502 (`review-ui/nginx.conf.template:19-33`).
- **Ningun dato de negocio se persiste en el navegador**: solo la key y el actor van a
  `localStorage` (busqueda `localStorage|sessionStorage` en `review-ui/src`); entidades,
  instancias y borradores viven en el estado de React.
- **Tests de UI en CI** sobre el camino critico (aprobar despliega, rechazar no), contra el stack
  real (`.github/workflows/ci.yml:101-119`).

## Huecos

| Hueco | Severidad | Evidencia |
|---|---|---|
| **Aprobar un borrador exige solo `compose:write`, pero el deploy lo hace el composer con la key de bootstrap (scopes `*` por default).** Una key que puede "generar/aprobar borradores" despliega codigo sin tener `flows:deploy`, y el deploy queda en `audit_log` a nombre de la key de servicio, no de quien aprobo; el `actor_id` del borrador es texto libre. Quien compone controla la descripcion que va al LLM, asi que tambien influye en la fuente que se despliega. Contradice el criterio que el propio gateway aplica a la edicion ("aprobar despliega `draft.source`, asi que quien puede reescribir esa columna [...] es la misma responsabilidad que desplegar") y encadena con el hueco alto de `${env.*}`. Direccion: exigir `flows:deploy` en `/drafts/{id}/approve` y desplegar con la identidad del que aprueba. (frontera: composer, gateway) | alta | Ruta POST `/drafts/{rest:path}` con `compose:write` `teleflow/gateway/main.py:795-800`; `COMPOSE_WRITE` = "generar/aprobar borradores" `teleflow/gateway/auth.py:38`; `FLOWS_DEPLOY` = "ejecutar codigo nuevo" `teleflow/gateway/auth.py:30`; el composer despliega con `settings.teleflow_api_key` `teleflow/composer_service/main.py:173-179`; default `"dev-key-change-me"` y scopes `"*"` `teleflow/common/config.py:18,23`; actor libre `teleflow/composer_service/main.py:157-160,188-191`; descripcion al LLM `teleflow/composer_service/main.py:65-72`; edicion con `flows:deploy` y su justificacion `teleflow/gateway/main.py:803-815`; la UI llama approve `review-ui/src/api.js:31-32`, `review-ui/src/App.jsx:160-164`; el comentario de la UI da el corte por hecho `review-ui/src/App.jsx:10-12`, `review-ui/src/api.js:37-38`; `${env.*}` `spec/features/base-lenguaje-tflow/seguridad.md:89`. |
| **El nombre del borrador entra sin validar a la URL con la que el composer llama al gateway usando la key de bootstrap.** `ComposeRequest.name` es `str` libre y se persiste tal cual; al aprobar se arma `f"{gateway_url}/flows/{draft.name}"` y httpx normaliza los segmentos `..` de la ruta. Un nombre como `../keys/<uuid>/rotate` convierte la aprobacion en `POST /keys/<uuid>/rotate` con scopes `*`: esa ruta no lee body, rota la key y devuelve el secreto nuevo, y el composer lo devuelve al que aprobo dentro de `deploy`. Mismo patron sirve para `POST /instances/<id>/retry`. Requiere `compose:write` y conocer un id (`GET /audit` expone `actor_key_id`). Direccion: validar `name` con la gramatica de nombres del DSL en `/compose` y codificar el segmento al armar la URL. `(inferencia: la cadena no se ejecuto; cada eslabon esta citado)` (frontera: composer) | alta | UI envia el nombre libre `review-ui/src/App.jsx:481-482`, `review-ui/src/api.js:29-30`; `name: str` `teleflow/composer_service/main.py:54-57`; persistido sin validar `teleflow/composer_service/main.py:97-101`, columna `String(200)` `teleflow/common/models.py:180`; URL interpolada `teleflow/composer_service/main.py:175-176`; normalizacion de ruta `.venv/Lib/site-packages/httpx/_urlparse.py:328-329,447` (httpx 0.28.1); approve no bloquea por `validation` `teleflow/composer_service/main.py:163-179`; respuesta upstream devuelta `teleflow/composer_service/main.py:195`; rotacion sin body y con secreto en la respuesta `teleflow/gateway/main.py:545-576`; retry `teleflow/gateway/main.py:721-726`; `actor_key_id` en `/audit` `teleflow/gateway/main.py:474`. |
| **La API key vive en `localStorage` sin expiracion ni forma de cerrar sesion, en un origen sin CSP.** Cualquier script que llegue a correr en el origen (dependencia comprometida del bundle, un XSS futuro) la lee; tambien queda para el siguiente usuario del mismo perfil de navegador. Se escribe en cada tecla. No se encontro un vector XSS en el codigo actual (ver controles), por eso no es alta; la key tipica de la UI es de alto privilegio (los tests y la demo usan la de bootstrap). Direccion: `sessionStorage` o memoria + CSP estricta; a mediano plazo sesion con cookie `HttpOnly`. | media | `review-ui/src/api.js:6`; `review-ui/src/App.jsx:25,139-142,204-210`; unico `removeItem` en tests `review-ui/tests/revision.spec.js:210` (busqueda `localStorage` en `review-ui/`); sin CSP: `review-ui/index.html:3-7`, `review-ui/nginx.conf.template:6-49` sin `add_header`; ya anotado sin severidad en `wiki/Knowledge/backlog-hardening.md:108-109`. |
| **El actor de firmas, transiciones y aprobaciones es texto libre y el backend no lo liga a la key.** En operacion se escribe en un input y se guarda en `localStorage`; en dominio se lee de ahi y si falta va `null`; en revision sale de un `prompt()` con default `'dev'`, y el rechazo manda `'dev'` fijo. El gateway reenvia el body sin tocarlo y el executor persiste `actor_id` en `instance_transitions`, que la UI muestra como "por <actor>". Una key compartida (el modelo de la UI es una key por navegador) permite firmar a nombre de otro; `audit_log` solo distingue keys. Direccion: derivar el actor de la identidad de la key en el gateway e ignorar el del body. | media | `review-ui/src/ops.jsx:38,71-74,76-82,178-185,378`; `review-ui/src/dominio.jsx:74-76,92-94`; `review-ui/src/App.jsx:118-124,160-164,177`; body reenviado `teleflow/gateway/main.py:416,420-425`; persistencia `teleflow/executor_service/main.py:172,181,200,264`, `teleflow/common/models.py:104`; identidad solo por key en auditoria `teleflow/gateway/main.py:231-232`. |
| **nginx no manda headers de seguridad**: sin `Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options`, `Referrer-Policy` ni `Strict-Transport-Security` (este ultimo solo tendria sentido con TLS delante). La UI desde la que se despliega codigo puede embeberse en un iframe ajeno `(inferencia: el particionado de storage de navegadores actuales y el bloqueo de `prompt()`/`confirm()` en iframes cross-origin limitan el clickjacking, no lo anulan)`. `server_tokens` queda en su default (version de nginx en `Server` y paginas de error). Direccion: bloque `add_header ... always` en la plantilla. | media | `review-ui/nginx.conf.template:6-49` (busqueda `add_header|server_tokens` en la plantilla y en `helm/`: sin coincidencias); `review-ui/index.html:3-7` sin `<meta http-equiv>`. |
| **La exposicion de la UI no esta decidida y lo que existe no protege el camino.** En compose se publica en `0.0.0.0:3100` en HTTP, asi que la key viaja en claro a cualquier maquina de la red. En Helm no hay Ingress, pero el dia que se agregue uno a mano no hereda la validacion de TLS que el chart impone al Ingress del gateway, y ademas publica el gateway entero por `/api/*` aunque `gateway.ingress.enabled` siga en `false`. Direccion: ADR de exposicion (`review-ui/src/App.jsx:14-16`) y, si se publica, Ingress del chart con la misma validacion de TLS. | media | `docker-compose.yml:158-159`; `review-ui/nginx.conf.template:7` (`listen 80`); `helm/teleflow/templates/review-ui.yaml:58-59`; `helm/teleflow/templates/ingress.yaml:12-14,16,41-57` (la validacion de TLS solo cubre `gateway.ingress`); `helm/teleflow/values.yaml:145-169`; `review-ui/src/App.jsx:14-16`. `(inferencia: efecto de un Ingress ad-hoc)` |
| **Identificadores de negocio (una cedula) viajan en la ruta**: quedan en el access log de nginx y en `audit_log.subject`. La UI invita a usar el identificador propio como `entity_id` ("una cedula, un numero de cliente") y lo pone en la URL de la ficha 360 y de las transiciones. El gateway guarda el path completo y el subject (`socio/12345`) en cada escritura auditada, que es la tabla que mas se conserva. Direccion: `entity_id` opaco (uuid) y la cedula como campo; o enmascarar el path en logs. | media | `review-ui/src/dominio.jsx:427-429,457-459`; rutas `review-ui/src/api.js:82,85-87`; `audit_log.path` y `subject` `teleflow/gateway/main.py:211-223,235-236`; `review-ui/nginx.conf.template` sin `access_log` propio `(inferencia: la imagen oficial loguea cada request con su URI a stdout)`; campo `ci` en `examples/ceibal.tflow:7-11`. |
| **Contenedor como root y sin endurecer en k8s**: la etapa final no declara `USER` y escucha en el puerto 80; el Deployment no tiene `securityContext`, ni `readOnlyRootFilesystem`, ni NetworkPolicy ni PDB (2 replicas). El pod solo necesita hablar con el gateway, pero nada lo restringe. Direccion: imagen `nginx-unprivileged` en 8080 + `securityContext` restrictivo. | media | `review-ui/Dockerfile:13-23`; `helm/teleflow/templates/review-ui.yaml:21-49`; busqueda `securityContext|runAsNonRoot|NetworkPolicy|PodDisruptionBudget` en `helm/`: solo el comentario `helm/teleflow/templates/datos.yaml:15`. `(inferencia: la imagen oficial `nginx` arranca el master como root)` |
| **Parametros de ruta sin codificar** en todas las llamadas (`/drafts/${id}`, `/flows/${name}/latest`, `/entities/${tipo}/${id}/...`, `/relations/${tipo}/${id}/transition`). El `entity_id` es texto libre hasta 100 caracteres, asi que un id con `/`, `..` o `?` cargado por alguien con `entities:write` hace que el navegador de otro usuario, con su key, pida otra ruta del gateway al abrir la ficha. `(inferencia: el `fetch` resuelve los `..`; con los sufijos fijos `/360` y `/transition` el desvio util queda limitado a GET sin efectos)` Direccion: `encodeURIComponent` en `review-ui/src/api.js` y formato de `entity_id` en el executor. | baja | `review-ui/src/api.js:28,39-40,43,64,81-87,92-93,97-100`; `review-ui/src/dominio.jsx:137-140,56-58`; `entity_id: str \| None` `teleflow/executor_service/main.py:194`; `eid = entity_id or ...` sin validar `teleflow/executor_service/entities.py:125`; `String(100)` `teleflow/common/models.py:118`. |
| **Timeouts de 720 s en todo `/api/`**, no solo en `/compose`, y sin `limit_req`/`limit_conn`: un cliente puede sostener conexiones de nginx hasta 12 minutos. Para las rutas que no son `/compose` el techo efectivo lo pone el gateway (60 s). Direccion: `location /api/compose` con 720 s y el resto con el default. | baja | `review-ui/nginx.conf.template:37-47`; timeout del gateway `teleflow/gateway/main.py:51,426-428`; `compose_timeout = 660.0` `teleflow/common/config.py:58`; contrato de la cadena `tests/test_composer.py:639-648`. Busqueda `limit_req|limit_conn|client_max_body_size` en la plantilla: sin coincidencias. |
| **El proxy publica las rutas publicas del gateway** (`/api/metrics`, `/api/docs`, `/api/openapi.json`, `/api/redoc`) a quien llegue a la UI, aunque el gateway no tenga Ingress. | baja | `review-ui/nginx.conf.template:30-33`; `PUBLIC_PATHS` `teleflow/gateway/main.py:39,149-150`. |
| **Datos personales sin minimizacion en pantalla**: la ficha 360 pinta todos los campos de la entidad y el listado trae hasta 100 entidades con su `nombre`, para cualquier key con `entities:read`. | baja | `review-ui/src/dominio.jsx:141,400-412`; `review-ui/src/api.js:80-81`; `_ENTITY_SCOPES` `teleflow/gateway/main.py:729-731`. |
| **Imagenes por tag, no por digest**: `node:20-alpine` y `nginx:1.27-alpine` (tags flotantes de parche) en el Dockerfile; `uiImage.tag: "1.0.0"` en el chart. | baja | `review-ui/Dockerfile:1,13`; `helm/teleflow/values.yaml:6-8`; `helm/teleflow/templates/review-ui.yaml:23`. |
| **Dependencias sin auditoria automatica**: no hay `npm audit` en CI ni Dependabot/Renovate. `esbuild` 0.21.5 `(inferencia, no verificado con `npm audit`)` cae en el rango del advisory GHSA-67mh-4wv8-2f99, que afecta solo al servidor de desarrollo. | baja | `.github/workflows/ci.yml:104-119` (solo `npm ci` y tests); `.github/` contiene solo `workflows/ci.yml` y `workflows/imagenes.yml` (busqueda `audit\|dependabot\|renovate\|trivy\|snyk\|osv` en `.github/`: sin coincidencias); `review-ui/package-lock.json:1291-1292`. |
| **`X-Real-IP` se manda pero nadie lo consume**: `audit_log` no guarda IP de origen, y detras del proxy el gateway solo ve la IP del pod de nginx. | baja | `review-ui/nginx.conf.template:35`; busqueda `X-Real-IP\|forwarded\|client.host` en `teleflow/`: sin coincidencias; campos de `AuditLog` `teleflow/gateway/main.py:230-239`. |

## Datos personales

- **Que muestra**: la seccion Dominio lista entidades y abre su ficha 360 con todos los campos
  (`review-ui/src/dominio.jsx:137-145,400-412`). En el dominio de ejemplo eso es `ci`, `nombre`, `fecha_nac`,
  `departamento` y `tutor_email` de un menor (`examples/ceibal.tflow:7-17`). La seccion Operacion
  muestra errores de instancia y actores (`review-ui/src/ops.jsx:344-362,371-378`); el alta de expediente y de
  entidad envia payloads con los campos que declara el flow (`review-ui/src/ops.jsx:243-254`,
  `review-ui/src/dominio.jsx:436-447`).
- **Donde se persiste del lado del navegador**: en ningun lado mas que la memoria de React; solo
  la key y el actor van a `localStorage` (ver controles). No hay cache de service worker (busqueda
  en `review-ui/src` e `review-ui/index.html`: no se registra ninguno).
- **A donde viaja**: al gateway por el proxy, en HTTP dentro de la instalacion
  (`review-ui/nginx.conf.template:30-35`; sin TLS interno, limite consciente `README.md:362-365`). En
  compose, tambien en HTTP entre el navegador y el host (hueco media). No viaja a RabbitMQ ni a un
  LLM desde la UI; la descripcion de `/compose` si va al LLM configurado
  (`teleflow/composer_service/main.py:65-72`) y es texto libre donde alguien podria escribir un dato
  personal (frontera: composer; ADR-003 proveedor configurable).
- **Logs y `audit_log`**: el `entity_id` y el tipo quedan en `audit_log.path` y `subject` en cada
  escritura (`teleflow/gateway/main.py:211-223,235-236`) y en el access log de nginx `(inferencia)`; si el
  id es una cedula, la cedula queda ahi (hueco media). Los valores de los campos no van a
  `audit_log` desde estas rutas (`teleflow/gateway/main.py:238`, `details` solo si la ruta lo setea).

## Secretos y configuracion

- **La UI no lee variables ni secretos propios.** Su unica configuracion es `GATEWAY_ORIGIN`
  (default `http://api-gateway:8000`, `review-ui/Dockerfile:17`; en Helm, FQDN derivado del
  release, `helm/teleflow/templates/review-ui.yaml:34-35`, `helm/teleflow/values.yaml:18-20`) y `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`
  (`review-ui/Dockerfile:21`). Ninguno es secreto.
- **La credencial la trae el usuario** y queda en `localStorage` (hueco media). No se encontro
  ninguna key literal en `review-ui/src` ni en la plantilla de nginx (busqueda `localStorage` y
  `X-TeleFlow-API-Key`: solo `review-ui/src/api.js:6` lee de storage).
- **Key de servicio usada por la accion principal de la UI**: aprobar se ejecuta con
  `TELEFLOW_API_KEY` del composer, con default de desarrollo `dev-key-change-me` y scopes `*`
  (`teleflow/common/config.py:18,23`; `docker-compose.yml:7-8`). En el chart llega por Secret y el
  install falla si no se define `apiKey` ni `existingSecret` (`helm/teleflow/values.yaml:10-16`). El problema
  no es como llega sino que la UI dispare un deploy con ella (huecos altos).
- **Errores**: la UI muestra el `detail` del backend tal cual (`review-ui/src/api.js:16-22`); en un approve
  fallido incluye la respuesta completa del gateway (`teleflow/composer_service/main.py:180-185`). No se
  encontro que el gateway incluya secretos en esos `detail` en las rutas del alcance (busqueda no
  exhaustiva; el caso de `rotate` via nombre inyectado es exito, no error — hueco alta).

## Impacto en despliegue

- **As-built, sin cambios**: la UI no tiene migraciones ni estado; 2 replicas stateless
  (`helm/teleflow/values.yaml:166-169`, `helm/teleflow/templates/review-ui.yaml:11`) sin asumir proceso unico.
- **Compose**: se construye desde `./review-ui` y publica `3100:80` en todas las interfaces,
  dependiendo del gateway (`docker-compose.yml:156-161`).
- **Helm**: Deployment + Service `ClusterIP` detras de `reviewUi.enabled: true`
  (`helm/teleflow/templates/review-ui.yaml:1-65`, `helm/teleflow/values.yaml:166-169`). Solo `readinessProbe`, sin `livenessProbe`
  (`helm/teleflow/templates/review-ui.yaml:38-43`); limite de memoria 128Mi y sin limite de CPU (`helm/teleflow/templates/review-ui.yaml:44-49`).
  Sin Ingress, sin `securityContext`, sin NetworkPolicy, sin PDB (ver huecos). `imagePullPolicy`
  toma el de la imagen Python (`helm/teleflow/templates/review-ui.yaml:24`, `helm/teleflow/values.yaml:4`).
- **Imagen**: `nginx:1.27-alpine` como root en el puerto 80 (`review-ui/Dockerfile:13-23`), build con
  `node:20-alpine` y `npm ci` (`review-ui/Dockerfile:1-11`).
- **CI**: la imagen se buildea dentro del `docker compose up` del job e2e y los tests de
  Playwright corren contra ella (`.github/workflows/ci.yml:101-119`). Sin auditoria de
  dependencias.
- **Instalable por organismo sin overrides**: si (`spec/constitution/mission.md:23-26`). Para
  usarla fuera del cluster hoy hace falta port-forward (`helm/teleflow/templates/ingress.yaml:12-14`); publicarla es una
  decision pendiente con ADR (`review-ui/src/App.jsx:14-16`), no un override.
