---
project: copp-ia
type: spec
status: implementada
feature: base-review-ui
provenance: copp-ia@devyos@ffd585d
created: 2026-09-14
---

<!-- Linea base as-built: documenta lo que el codigo hace hoy. Nunca se sincroniza con Jira. -->
<!-- Lo escribe el subagente `analista-requisitos` (modo as-built). Ante conflicto, manda el codigo. -->


# Linea base — `review-ui` (acceso, revision de borradores, operacion, dominio, proxy nginx)

## Que resuelve

Una persona que no arma requests a mano necesita, desde un navegador: revisar, corregir, aprobar
o rechazar los borradores `.tflow` que genera el composer; atender los expedientes que esperan
su firma o que fallaron; iniciar un expediente nuevo; y consultar y mover las entidades y
vinculos del dominio. Todo pasando por el gateway, que es quien autoriza.

Lo resuelve hoy asi (comprobado leyendo el codigo en `copp-ia@devyos@ffd585d`):

- **Una sola app con tres secciones** para tres publicos (operacion, dominio, revision) que
  comparten build; el corte de permisos lo hacen los scopes del gateway, no la pantalla
  (`review-ui/src/App.jsx:7-12`). Solo se monta la seccion activa (`review-ui/src/App.jsx:216-222`).
- **Un unico punto de consumo de la API**: `review-ui/src/api.js:26-101`, que manda cada request a
  `/api` con el header `X-TeleFlow-API-Key` leido de `localStorage` (`review-ui/src/api.js:1-8`).
- **Revision PR-style** con diff por LCS sin dependencias (`review-ui/src/diff.js:1-31`), badge de
  validacion de tres estados (`review-ui/src/App.jsx:295-303`) y un editor minimo con columna de
  numeros e "ir a la linea" (`review-ui/src/App.jsx:384-436`, `review-ui/src/App.jsx:55-72`).
- **Bandeja operativa** por estado, ficha con linea de tiempo, firma atribuida a un actor y
  reintento (`review-ui/src/ops.jsx:4-13`, `review-ui/src/ops.jsx:34-199`), con un formulario de
  alta de expediente **generado desde el AST** del flow desplegado (`review-ui/src/ops.jsx:201-206`).
- **Dominio**: tipos desde `GET /domain`, lista, ficha 360, transiciones validas desde el estado
  actual y alta de entidades y vinculos con campos que salen del DSL
  (`review-ui/src/dominio.jsx:4-12`, `review-ui/src/dominio.jsx:166-172`).
- **Imagen nginx** que sirve el bundle y proxea `/api/` al gateway con upstream resuelto por
  request y techos de timeout mayores que los del gateway (`review-ui/nginx.conf.template:17-48`,
  `review-ui/Dockerfile:1-23`).

**Esta linea base es el insumo de paridad para retirar pantallas.** La direccion de producto
vigente reemplaza la interfaz de pantallas por un asistente conversacional con `@capacidades`
(`AGENTS.md:15-17`). Cada criterio de aceptacion de abajo es un flujo que hoy existe y nombra el
endpoint del gateway que consume (tal como lo llama `review-ui/src/api.js`) y el scope que ese
endpoint exige: antes de retirar una pantalla, cada criterio tiene que tener un equivalente
conversacional que consuma el mismo endpoint con el mismo resultado observable. La spec del
asistente no existe en este commit (no hay `spec/features/asistente-conversacional/`).

## Objetivo

Que un revisor, un operador y quien consulta el dominio puedan hacer desde el navegador cada una
de las operaciones listadas abajo contra el gateway, sin que la pantalla afirme un veredicto de
validacion que el servidor no dio ni ofrezca una accion que el estado actual no permite.

## Alcance

**Entra:**

- `review-ui/src/App.jsx` — layout, campo de API key, seccion Revision (lista, panel de
  validacion, editor, diff, aprobar, rechazar, componer).
- `review-ui/src/api.js` — cliente HTTP y superficie de endpoints consumidos.
- `review-ui/src/diff.js` — `lineDiff` (LCS por lineas).
- `review-ui/src/ops.jsx` — seccion Operacion (bandeja, ficha, firma, reintento, nuevo expediente).
- `review-ui/src/dominio.jsx` — seccion Dominio (tipos, lista, ficha 360, transiciones, altas,
  vinculos).
- `review-ui/src/main.jsx` — montaje de `App` (`review-ui/src/main.jsx:1-6`).
- `review-ui/nginx.conf.template`, `review-ui/Dockerfile` — imagen servida en el compose
  (`docker-compose.yml:156-161`, `3100:80`) y en el chart (`helm/teleflow/templates/review-ui.yaml:1-65`).
- `review-ui/vite.config.js` — dev server y proxy local; `review-ui/playwright.config.js` — suite
  de UI.
- Tests ancla: `review-ui/tests/revision.spec.js` (18 tests), `review-ui/tests/operacion.spec.js`
  (9) y `review-ui/tests/dominio.spec.js` (7): 34 tests de Playwright que corren contra el stack
  levantado en `:3100` (`review-ui/playwright.config.js:3-6`), en el job e2e de CI
  (`.github/workflows/ci.yml:101-119`).

Superficie de API que consume la UI (todas pasan por `/api` → gateway):

| Metodo `api.js` | Endpoint del gateway | Scope (`teleflow/gateway/main.py`) | Usado en |
|---|---|---|---|
| `listDrafts` | `GET /drafts` | `compose:read` (`:784-788`) | Revision |
| `getDraft` | `GET /drafts/{id}` | `compose:read` (`:791-794`) | Revision |
| `compose` | `POST /compose` | `compose:write`, timeout `compose_timeout` (`:775-781`) | Revision |
| `approve` | `POST /drafts/{id}/approve` | `compose:write` (`:795-798`) | Revision |
| `reject` | `POST /drafts/{id}/reject` | `compose:write` (`:795-798`) | Revision |
| `editDraftSource` | `PATCH /drafts/{id}/source` | `flows:deploy` (`:803-804`) | Revision |
| `getLatestSource`, `getFlow` | `GET /flows/{name}/latest` | `flows:read` (`:676-678`) | Revision, Operacion |
| `listFlows` | `GET /flows` | `flows:read` (`:664-665`) | Operacion |
| `execute` | `POST /execute` | `instances:trigger` (`:686-687`) | Operacion |
| `listInstances` | `GET /instances?limit=50[&status=]` | `instances:read` (`:699-700`) | Operacion |
| `getInstance` | `GET /instances/{id}` | `instances:read` (`:705-707`) | Operacion |
| `signal` | `POST /instances/{id}/signal` | `instances:signal` (`:713-715`) | Operacion |
| `retry` | `POST /instances/{id}/retry` | `instances:retry` (`:721-723`) | Operacion |
| `getDomain` | `GET /domain` | `entities:read` (`:749-750`) | Dominio |
| `listEntities` | `GET /entities/{tipo}?limit=100[&estado=]` | `entities:read` (`:729-738`) | Dominio |
| `vista360` | `GET /entities/{tipo}/{id}/360` | `entities:read` (`:729-738`) | Dominio |
| `createEntity` | `POST /entities/{tipo}` | `entities:write` (`:729-741`) | Dominio |
| `transitionEntity` | `POST /entities/{tipo}/{id}/transition` | `entities:write` (`:729-741`) | Dominio |
| `createRelation` | `POST /relations/{tipo}` | `entities:write` (`:760-765`) | Dominio |
| `transitionRelation` | `POST /relations/{tipo}/{id}/transition` | `entities:write` (`:760-765`) | Dominio |
| `getEntity` | `GET /entities/{tipo}/{id}` | `entities:read` | **Ninguna pantalla** (ver "No entra") |

Los nombres de scope estan en `teleflow/gateway/auth.py:29-40`. Que `GET /flows/{name}/latest`
lo sirva la ruta `/flows/{name}/{version}` con `version = "latest"` sale de la forma de la ruta;
que el registry resuelva `latest` lo prueba indirectamente `review-ui/tests/dominio.spec.js:74`.

**No entra (y por que):**

- **Tests unitarios del front y lint.** `package.json` solo tiene los scripts `dev`, `build`,
  `preview`, `test` y `test:install` (`review-ui/package.json:6-12`) y ninguna devDependency de lint
  (`review-ui/package.json:17-21`). `lineDiff` es logica pura y no tiene un test propio. Motivo
  escrito: la UI se prueba contra el stack para probar el artefacto que se despliega
  (`review-ui/playwright.config.js:3-5`). Consecuencia: toda la red de seguridad de la UI requiere
  Docker y solo corre en el job e2e (`.github/workflows/ci.yml:101-119`), no en el gate rapido.
  En CI cada test tiene 1 reintento (`review-ui/playwright.config.js:15`), asi que un test
  intermitente pasa en verde.
- **API key fuera de `localStorage`.** Se guarda en `localStorage['tflow_api_key']` en cada tecla
  (`review-ui/src/App.jsx:139-142`) y se lee en cada request (`review-ui/src/api.js:6`). No hay
  cierre de sesion ni expiracion en la UI. Que cualquier script del mismo origen pueda leerla es
  `(inferencia)` del mecanismo; el analisis de riesgo no se hace aca. Motivo: no documentado.
- **Refresco al cargar la key.** La lista de borradores se pide una sola vez al montar `App`
  (`review-ui/src/App.jsx:83`), `saveKey` no la vuelve a pedir (`review-ui/src/App.jsx:139-142`) y la
  seccion Revision no tiene boton "Actualizar" (`review-ui/src/App.jsx:225-228`). Quien escribe la
  key despues de abrir la UI sigue viendo el `401` hasta recargar o hacer una accion que llame a
  `refresh`. Comprobado leyendo el codigo, no ejecutado. Sin test (los tests escriben la key en
  `localStorage` y recargan, `review-ui/tests/revision.spec.js:58-62`).
- **Actor ligado a la identidad.** El actor es texto que declara quien usa la pantalla: prompt con
  default `dev` al guardar y al aprobar (`review-ui/src/App.jsx:120`, `review-ui/src/App.jsx:162`),
  `dev` fijo al rechazar (`review-ui/src/App.jsx:177`), campo libre en Operacion
  (`review-ui/src/ops.jsx:178-183`) y en Dominio el valor de `localStorage['tflow_actor']` o `null`
  sin campo propio (`review-ui/src/dominio.jsx:74-76`, `review-ui/src/dominio.jsx:92-94`). Cancelar
  el prompt de actor al aprobar **no cancela el deploy**: sigue con `dev`
  (`review-ui/src/App.jsx:162-164`). Motivo: no documentado. Sin test.
- **Exposicion de la UI.** El chart crea un Service `ClusterIP` (`helm/teleflow/templates/review-ui.yaml:59`)
  y el Ingress solo publica el gateway (`helm/teleflow/templates/ingress.yaml:12-14`); la UI se
  alcanza por port-forward. `review-ui/src/App.jsx:14-16` deja pendiente decidir la exposicion
  "con su ADR", y no hay ese ADR en `wiki/Knowledge/decisions/`. Decision consciente de no
  publicarla (`wiki/Knowledge/roadmap.md:182-185`), sin decision sobre como publicar solo la parte
  operativa.
- **Errores al pedir la version desplegada.** `getLatestSource` devuelve `''` ante **cualquier**
  error (`review-ui/src/api.js:41-48`): un `401`, `403` o `5xx` en `GET /flows/{name}/latest` se ve
  como "Archivo nuevo" en el diff (`review-ui/src/App.jsx:493-497`) y el formulario de componer
  manda `base_source: null` (`review-ui/src/App.jsx:466-468`). Motivo: no documentado. Sin test.
- **Rotulo del diff contra el modelo.** El encabezado dice "Diff contra la versión latest
  registrada" tambien cuando el selector esta en "contra lo que generó el modelo"
  (`review-ui/src/App.jsx:279-281`, `review-ui/src/App.jsx:497`). Sin test.
- **Editar campos de una entidad.** El gateway enruta `PATCH /entities/...` y `PATCH /relations/...`
  (`teleflow/gateway/main.py:742-744`, `teleflow/gateway/main.py:766-768`) y la UI no lo usa; `api.getEntity`
  esta definido (`review-ui/src/api.js:82`) y ninguna pantalla lo llama. Que el executor implemente
  el `PATCH` no se verifico. Motivo: no documentado.
- **Paginacion.** Las listas se cortan sin paginar: 100 borradores (`teleflow/composer_service/main.py:144`),
  50 instancias (`review-ui/src/api.js:95-96`) y 100 entidades (`review-ui/src/api.js:80-81`). Sin test.
- **`Idempotency-Key` al iniciar un expediente.** Los headers son solo `Content-Type` y la key
  (`review-ui/src/api.js:3-8`); lo unico que evita el doble alta es deshabilitar el boton mientras
  se envia (`review-ui/src/ops.jsx:295-297`). Que un reintento de red o dos pestañas creen dos
  instancias es `(inferencia)`. Sin test.
- **Validacion de formularios en el cliente.** Solo se exige que los `required` no esten vacios
  (`review-ui/src/ops.jsx:296-297`, `review-ui/src/dominio.jsx:392-393`, `review-ui/src/dominio.jsx:469-470`);
  tipos, rangos y unicidad los decide el servidor. Decision coherente con que "la pantalla nunca
  decide si algo compila" (`review-ui/src/api.js:35-36`).
- **Limite de tamaño del body en el proxy.** `review-ui/nginx.conf.template` no declara
  `client_max_body_size`; que rija el default de nginx (1 MB) y un borrador mas grande reciba `413`
  al guardar es `(inferencia)`, no verificado contra la imagen.
- **Dev server en `:3100` con el compose levantado.** `vite.config.js` fija `port: 3100`
  (`review-ui/vite.config.js:8`), el mismo puerto que publica el compose (`docker-compose.yml:159`).
  `(inferencia)`: Vite 5 sin `strictPort` salta al siguiente puerto libre en vez de fallar, asi que
  `npm run dev` no "choca" sino que queda en otro puerto, y `npm test` (default `REVIEW_UI_URL`
  `http://localhost:3100`, `review-ui/playwright.config.js:6`) sigue probando el bundle de nginx y
  no el dev server. No verificado ejecutando.
- **El recorrido de demo.** `review-ui/demo/recorrido.spec.js` usa su propio config con
  `testDir: './demo'` (`review-ui/playwright.demo.config.js:5-8`, `review-ui/playwright.demo.config.js:22`)
  y no entra a CI: no es criterio de aceptacion.
- **Seguridad del borde (cabeceras, CSP, almacenamiento de credenciales).** Se analiza en el
  `seguridad.md` hermano, no aca.
- **La paridad conversacional misma.** Esta spec inventaria lo que existe; como se cubre cada flujo
  en el asistente se define en su propia feature.

## Criterios de aceptacion

Cada criterio nombra el test que lo comprueba. `(sin test)` = el codigo lo hace y ningun test lo
prueba. `(indirecto)` = lo prueba un test de otro modulo o de otro flujo. Los tests de Playwright
se citan `review-ui/tests/<archivo>.spec.js::<nombre del test>`. Cada criterio indica el endpoint
del gateway que consume: es la linea de paridad.

### Acceso con API key

- [ ] Dado un navegador sin `tflow_api_key` en `localStorage`, cuando se abre la UI, entonces la
  seccion Revision pide `GET /drafts` sin key y muestra `.banner.error` con `401` —
  `GET /drafts` — `review-ui/tests/revision.spec.js::sin API key la UI avisa en vez de romperse`
- [ ] Dada una key en `localStorage['tflow_api_key']`, cuando la UI hace cualquier request, entonces
  lo manda a `/api<ruta>` con el header `X-TeleFlow-API-Key` (`review-ui/src/api.js:1-15`) — todos
  los endpoints — `(indirecto)`: los 34 tests cargan la key asi y operan
  (`review-ui/tests/revision.spec.js:58-62`, `review-ui/tests/operacion.spec.js:39-44`,
  `review-ui/tests/dominio.spec.js:34-38`)
- [ ] Dado el campo `X-TeleFlow-API-Key` del encabezado (`type="password"`), cuando se escribe,
  entonces el valor se guarda en `localStorage['tflow_api_key']` en cada cambio
  (`review-ui/src/App.jsx:139-142`, `review-ui/src/App.jsx:204-210`) — sin endpoint — `(sin test)`
- [ ] Dada una respuesta no 2xx del gateway, cuando el cliente la procesa, entonces lanza un error
  `<status>: <detail>` (string tal cual, o JSON del `detail` o del cuerpo) que la seccion muestra
  en `.banner.error`; un cuerpo no JSON queda como `{}` (`review-ui/src/api.js:16-22`) — todos —
  el prefijo de status lo cubre `review-ui/tests/revision.spec.js::sin API key la UI avisa en vez de romperse`;
  el cuerpo no JSON `(sin test)`
- [ ] Dadas las tres pestañas Operacion, Dominio y Revision de flows, cuando se cambia de seccion,
  entonces se limpian los banners y solo la seccion activa queda montada en el DOM
  (`review-ui/src/App.jsx:190-203`, `review-ui/src/App.jsx:216-222`); la seccion inicial es Revision
  (`review-ui/src/App.jsx:19`) — sin endpoint — `(indirecto)`: `operacion.spec.js` y `dominio.spec.js`
  navegan con esos botones (`review-ui/tests/operacion.spec.js:43`, `review-ui/tests/dominio.spec.js:38`);
  el desmontaje `(sin test)`

### Revision: lista y estado de validacion

- [ ] Dados tres borradores con `validation.parses` `true`, `false` y `null`, cuando se lista,
  entonces sus badges dicen `compila`, `no compila` y `sin verificar` con clases `ok`, `bad` y
  `unknown` — `GET /drafts` — `review-ui/tests/revision.spec.js::los tres estados de validación se distinguen`
- [ ] Dado un borrador `flow_sin_verificar` sin validacion, cuando se lista, entonces su badge
  `sin verificar` se renderiza como una sola caja (`getClientRects().length == 1`) — `GET /drafts` —
  `review-ui/tests/revision.spec.js::el badge de estado no se parte en dos líneas`
- [ ] Dado un borrador corregido a mano (`editado: true`, `teleflow/composer_service/main.py:294`),
  cuando se lista, entonces su fila lleva el badge `.badge.editado` con texto `corregido`, y antes de
  corregirlo no lo lleva — `GET /drafts` —
  `review-ui/tests/revision.spec.js::un borrador corregido queda marcado en la lista`
- [ ] Dado un borrador generado por el proveedor `stub`, cuando se abre, entonces el panel
  `.validation.ok` muestra `generado por` y `esqueleto para editar a mano` — `GET /drafts/{id}` —
  `review-ui/tests/revision.spec.js::el borrador muestra su estado de validación y quién lo generó`
- [ ] Dado un borrador abierto, cuando se renderiza el panel, entonces:
  - con `validation.error`, muestra `No se pudo consultar al parser: <error>`
    (`review-ui/src/App.jsx:365-369`) — `(sin test)`
  - con `parses: true` y sin issues, muestra `Sin observaciones del parser.`
    (`review-ui/src/App.jsx:377-379`) — `(sin test)`
  - los botones Corregir, Aprobar y desplegar y Rechazar aparecen solo si `status == "pending"`
    (`review-ui/src/App.jsx:255-263`) — `(sin test)`
  - sin borradores, la lista dice `Sin borradores aún` (`review-ui/src/App.jsx:245`) — `(sin test)`

### Revision: diff

- [ ] Dado un borrador de un flow que no esta desplegado, cuando se abre, entonces se ve `.diff`
  con al menos una `.line.add` — `GET /drafts/{id}` y `GET /flows/{name}/latest` —
  `review-ui/tests/revision.spec.js::el diff aparece al abrir un borrador`
- [ ] Dado un borrador sin editar, cuando se abre, entonces no existe `.selector-diff`; despues de
  guardar una linea agregada y cerrar el editor, el selector aparece y "contra lo que generó el
  modelo" muestra esa linea como `.line.add` — `GET /drafts/{id}` (campo `source_generado`) —
  `review-ui/tests/revision.spec.js::el diff contra el modelo aparece recién cuando alguien editó`
- [ ] Dado un borrador de un flow ya desplegado, cuando se abre, entonces el diff compara contra
  `base_source` o, si falta, contra el `source` de la version `latest`, marcando `del`/`add`/`same`
  por LCS de lineas (`review-ui/src/App.jsx:89`, `review-ui/src/diff.js:2-31`) —
  `GET /flows/{name}/latest` — `(sin test)`: todos los tests usan nombres nuevos

### Revision: corregir el borrador

- [ ] Dado un borrador que compila, cuando se agrega texto invalido y se guarda, entonces el badge
  pasa a `no compila` con un issue que contiene `sintaxis`; y cuando se restaura la fuente y se
  guarda, vuelve a `compila` — `PATCH /drafts/{id}/source` (`flows:deploy`) —
  `review-ui/tests/revision.spec.js::guardar revalida contra el parser, en los dos sentidos`
- [ ] Dado el editor con cambios sin guardar, cuando se mira el panel, entonces el badge dice
  `sin validar` y el texto `el veredicto anterior ya no habla`, y la columna de numeros no marca
  ninguna linea de error (`review-ui/src/App.jsx:40-42`) — sin endpoint —
  `review-ui/tests/revision.spec.js::con cambios sin guardar el veredicto anterior no se muestra`;
  la no-marca de linea `(sin test)`
- [ ] Dado el editor, cuando se pulsa Validar y guardar, entonces:
  - pide comentario y actor por `prompt`; cancelar cualquiera de los dos no manda nada
    (`review-ui/src/App.jsx:117-121`) — `(sin test)`
  - el boton esta deshabilitado sin cambios o mientras guarda, y dice `Validando…`
    (`review-ui/src/App.jsx:408-410`) — `(sin test)`
  - al volver muestra `✓ Guardado y compila` o `Guardado — el parser todavía tiene observaciones`
    y deja el editor abierto (`review-ui/src/App.jsx:124-131`) — `(sin test)`
- [ ] Dado un error de sintaxis con fragmento, cuando se muestra el issue, entonces el contexto va
  en `.issue-ctx` con mas de una linea, contiene `^` y tiene `white-space: pre` —
  `PATCH /drafts/{id}/source` —
  `review-ui/tests/revision.spec.js::el fragmento con el apuntador se muestra preformateado`
- [ ] Dado un issue con `line` en un borrador `pending`, cuando se pulsa `ir a la línea N`, entonces
  el editor queda con la linea entera seleccionada y esa seleccion contiene el identificador
  erroneo — sin endpoint — `review-ui/tests/revision.spec.js::el error lleva al editor hasta la línea`;
  que el boton no aparezca en borradores no `pending` (`review-ui/src/App.jsx:269`,
  `review-ui/src/App.jsx:320`) `(sin test)`
- [ ] Dada una fuente guardada con error, cuando se abre el editor, entonces la columna tiene un
  numero por linea y `.linea-error` marca el mismo numero que el boton `ir a la línea` — sin
  endpoint — `review-ui/tests/revision.spec.js::hay un número por línea y la del error queda marcada`
- [ ] Dado el editor abierto, cuando se comparan columna y textarea, entonces tienen la misma
  `fontFamily`, `fontSize`, `lineHeight` y `paddingTop`, y el textarea tiene `wrap="off"` — sin
  endpoint — `review-ui/tests/revision.spec.js::los números no se corren respecto del código`
- [ ] Dado un texto de mas de 200 lineas, cuando el textarea se scrollea a `scrollTop = 900`,
  entonces la columna de numeros queda en `scrollTop = 900` — sin endpoint —
  `review-ui/tests/revision.spec.js::la columna sigue al código cuando se scrollea`
- [ ] Dado el editor con cambios sin guardar, cuando se pulsa Cerrar editor, entonces pide
  confirmacion y cancelar lo deja abierto (`review-ui/src/App.jsx:108-112`); y cuando se abre otro
  borrador, el editor se cierra y descarta el texto (`review-ui/src/App.jsx:90-94`) — sin endpoint —
  `(sin test)`

### Revision: aprobar, rechazar y componer

- [ ] Dado un borrador `pending` que compila, cuando se pulsa Aprobar y desplegar y se contestan
  version `1.0.0` y actor, entonces aparece `Aprobado y desplegado` y el flow figura en
  `GET /flows` — `POST /drafts/{id}/approve` (`compose:write`) —
  `review-ui/tests/revision.spec.js::aprobar despliega ese borrador`
- [ ] Dado un borrador con `parses: false`, cuando se pulsa Aprobar y desplegar y se cancela el
  dialogo, entonces el dialogo contiene `NO compila` y no se llama a `approve` —
  `POST /drafts/{id}/approve` —
  `review-ui/tests/revision.spec.js::aprobar algo que no compila pide confirmación, y cancelar no despliega`;
  con `parses` nulo el texto es `no se pudo verificar contra el parser`
  (`review-ui/src/App.jsx:154-158`) `(sin test)`
- [ ] Dado el editor con cambios sin guardar, cuando se pulsa Aprobar y desplegar y se cancela,
  entonces el dialogo contiene `sin guardar` y el flow no figura en `GET /flows` —
  `POST /drafts/{id}/approve` —
  `review-ui/tests/revision.spec.js::aprobar con cambios sin guardar avisa que se despliega lo guardado`
- [ ] Dado el prompt de version al aprobar, cuando se cancela o se deja vacio, entonces no se
  despliega (`review-ui/src/App.jsx:160-161`); cuando se cancela el prompt de actor, se despliega
  igual con actor `dev` (`review-ui/src/App.jsx:162-164`) — `POST /drafts/{id}/approve` — `(sin test)`
- [ ] Dado un borrador `pending`, cuando se pulsa Rechazar y se escribe un comentario, entonces
  aparece `rechazado` y el flow no figura en `GET /flows` — `POST /drafts/{id}/reject`
  (`compose:write`) — `review-ui/tests/revision.spec.js::rechazar no despliega nada`; cancelar el
  prompt no rechaza y el actor enviado es siempre `dev` (`review-ui/src/App.jsx:174-177`) `(sin test)`
- [ ] Dado el formulario `+ Nuevo` con nombre y descripcion (ambos `required`), cuando se pulsa
  Generar borrador, entonces si existe un flow desplegado con ese nombre se manda su fuente como
  `base_source` (si no, `null`), el boton dice `Generando…` mientras espera, y al terminar se
  cierra el formulario y se refresca la lista (`review-ui/src/App.jsx:457-489`,
  `review-ui/src/App.jsx:229-230`) — `GET /flows/{name}/latest` y `POST /compose` (`compose:write`) —
  `(sin test)` desde el formulario; `POST /compose` con proveedor `stub` responde `201`
  `(indirecto)` en el helper `crearBorrador` de `review-ui/tests/revision.spec.js:14-21`

### Operacion: bandeja y ficha

- [ ] Dada una venta de `venta_internet_hogar` esperando firma, cuando se abre Operacion, entonces
  el primer item de la bandeja (filtro por defecto `WAITING_SIGNAL`) muestra `venta_internet_hogar`,
  status `WAITING_SIGNAL` y el paso `aprobacion_gerencia` —
  `GET /instances?limit=50&status=WAITING_SIGNAL` (`instances:read`) —
  `review-ui/tests/operacion.spec.js::la bandeja muestra lo que espera firma y dice en qué paso está`
- [ ] Dados los filtros de la bandeja, cuando se elige uno, entonces se pide la lista con ese
  `status` y se cierra la ficha abierta (`review-ui/src/ops.jsx:18-23`, `review-ui/src/ops.jsx:127-135`):
  - `Fallados` (`FAILED`) — `(indirecto)` `review-ui/tests/operacion.spec.js::un fallado dice en qué paso falló y ofrece reintentar`
  - `En curso` (`IN_PROGRESS`) — `(sin test)`
  - `Todos` (sin `status`) — `(sin test)`
  - lista vacia muestra `Nada en este estado` (`review-ui/src/ops.jsx:147-149`) — `(sin test)`
- [ ] Dado un expediente esperando firma, cuando se abre su ficha, entonces la linea de tiempo
  contiene `TRIGGERED` e `IN_PROGRESS` y un renglon `li.esperando` con `esperando firma` —
  `GET /instances/{id}` (`instances:read`) —
  `review-ui/tests/operacion.spec.js::la línea de tiempo cuenta lo que ya pasó y lo que se está esperando`;
  version, antigüedad y `origen <correlation_id>` en la cabecera (`review-ui/src/ops.jsx:169-176`) y
  actor por transicion (`review-ui/src/ops.jsx:378`) `(sin test)`
- [ ] Dado un expediente esperando firma y el campo Tu usuario con `gerente.test`, cuando se pulsa
  Aprobar, entonces aparece un aviso con `approve` y la instancia llega a `COMPLETED` en menos de
  15 s — `POST /instances/{id}/signal` con `{step_name: current_step, signal: "approve", actor_id}`
  (`instances:signal`) — `review-ui/tests/operacion.spec.js::aprobar desde la ficha resuelve el expediente de verdad`
- [ ] Dado un expediente esperando firma y el campo Tu usuario vacio, cuando se pulsa Aprobar,
  entonces aparece un error con `usuario`, no se manda la señal y la instancia sigue
  `WAITING_SIGNAL` — sin endpoint (corte en cliente, `review-ui/src/ops.jsx:77-80`) —
  `review-ui/tests/operacion.spec.js::sin usuario no se firma: la firma tiene que quedar atribuida`
- [ ] Dado un expediente esperando firma, cuando se firma, entonces:
  - `Rechazar` manda `signal: "reject"` (`review-ui/src/ops.jsx:29-32`) — `POST /instances/{id}/signal` — `(sin test)`
  - el campo `otra señal` manda el texto escrito y su boton esta deshabilitado vacio
    (`review-ui/src/ops.jsx:333-335`) — `POST /instances/{id}/signal` — `(sin test)`
  - el usuario queda en `localStorage['tflow_actor']` para la proxima vez (`review-ui/src/ops.jsx:38`,
    `review-ui/src/ops.jsx:71-74`) — sin endpoint — `(sin test)`
  - tras la firma se recarga la lista y la ficha abierta (`review-ui/src/ops.jsx:42-57`) — `(sin test)`
- [ ] Dado un expediente `FAILED`, cuando se abre, entonces `.panel-error` muestra `Falló en <step>`
  y hay un boton Reintentar — `GET /instances/{id}` —
  `review-ui/tests/operacion.spec.js::un fallado dice en qué paso falló y ofrece reintentar`
  (se saltea si el stack no tiene fallados, `review-ui/tests/operacion.spec.js:230-235`)
- [ ] Dado un expediente `FAILED`, cuando se muestra y se opera, entonces:
  - el badge dice `error permanente` si el mensaje contiene `permanente`, y si no
    `error transitorio` (`review-ui/src/ops.jsx:344-352`) — `(sin test)`
  - pulsar Reintentar muestra `Reintento disparado.` y recarga — `POST /instances/{id}/retry`
    (`instances:retry`) (`review-ui/src/ops.jsx:90-98`) — `(sin test)`

### Operacion: nuevo expediente

- [ ] Dado `venta_internet_hogar` desplegado, cuando se abre `+ Nuevo expediente` y se elige ese
  flow, entonces el formulario pide `cliente_id`, `producto` y `direccion`, con `.req` en
  `cliente_id` y sin `.req` en `direccion` — `GET /flows` y `GET /flows/{name}/latest` (`flows:read`) —
  `review-ui/tests/operacion.spec.js::el formulario sale del flow: pide los campos que el proceso declara`
- [ ] Dado ese formulario, cuando faltan obligatorios, entonces Iniciar expediente esta
  deshabilitado, y se habilita al completar `cliente_id` y `producto` — sin endpoint —
  `review-ui/tests/operacion.spec.js::no se puede iniciar sin los campos obligatorios`
- [ ] Dado un flow nuevo desplegado con `numero_reclamo`, `severidad: enum["baja","media","alta"]` y
  `contacto` opcional, cuando se elige en el formulario, entonces pide esos campos y `severidad` es
  un `select` con opciones `—`, `baja`, `media`, `alta` — `GET /flows/{name}/latest` —
  `review-ui/tests/operacion.spec.js::un flow nuevo trae su propio formulario, sin tocar la UI`
- [ ] Dado el formulario completo, cuando se pulsa Iniciar expediente, entonces aparece `iniciado`,
  la ficha del expediente nuevo queda abierta y la instancia existe con el `payload.cliente_id`
  tipeado — `POST /execute` con `{flow_name: <nombre del proceso>, payload}` (`instances:trigger`) —
  `review-ui/tests/operacion.spec.js::iniciar crea el expediente y lo deja abierto`
- [ ] Dado el formulario de nuevo expediente, cuando se arma y envia, entonces:
  - un flow con un solo proceso lo preselecciona; con mas de uno aparece el selector Proceso
    (`review-ui/src/ops.jsx:232-235`, `review-ui/src/ops.jsx:272-280`) — `(sin test)`
  - un proceso sin `input` muestra `Este proceso no declara entradas.` (`review-ui/src/ops.jsx:291-293`) — `(sin test)`
  - los campos `number` viajan como numero, los vacios no viajan, `date`/`datetime` usan inputs de
    fecha (`review-ui/src/ops.jsx:247-252`, `review-ui/src/ops.jsx:315-320`) — `(sin test)`
  - al iniciar, el filtro pasa a `Todos` para que el expediente en `TRIGGERED` se vea
    (`review-ui/src/ops.jsx:119-121`) — `(sin test)`

### Dominio

- [ ] Dado el dominio desplegado, cuando se abre la seccion Dominio, entonces el selector Tipo se
  llena con las entidades de `GET /domain` y se preselecciona la primera
  (`review-ui/src/dominio.jsx:27-38`) — `GET /domain` (`entities:read`) — `(indirecto)`: los 7 tests
  de `dominio.spec.js` eligen el tipo en ese selector (`review-ui/tests/dominio.spec.js:39-41`); la
  preseleccion `(sin test)` (los tests la evitan a proposito, `review-ui/tests/dominio.spec.js:30-33`)
- [ ] Dado un `nino` recien creado, cuando se abre su ficha desde la lista, entonces el estado es
  `REGISTRADO`, `.campos` contiene `Montevideo` y la historia contiene `nino.registrado` —
  `GET /entities/nino?limit=100` y `GET /entities/nino/{id}/360` (`entities:read`) —
  `review-ui/tests/dominio.spec.js::la ficha muestra datos, historia y el estado actual`
- [ ] Dado un `nino` en `REGISTRADO`, cuando se abre la ficha, entonces las acciones contienen cada
  `via` del lifecycle desplegado que sale de `REGISTRADO` y ninguna que solo salga de otro estado —
  `GET /entities/nino/{id}/360` —
  `review-ui/tests/dominio.spec.js::solo se ofrecen las transiciones válidas desde el estado actual`;
  sin salidas muestra `estado final` (`review-ui/src/dominio.jsx:185`) `(sin test)`
- [ ] Dado un `nino` en `REGISTRADO`, cuando se pulsa `activar → …`, entonces aparece un aviso con
  `ACTIVO`, la entidad queda `ACTIVO` del lado del servidor, desaparece `activar → ` y aparece
  `desactivar → ` — `POST /entities/nino/{id}/transition` con `{via, actor_id}` (`entities:write`) —
  `review-ui/tests/dominio.spec.js::transicionar cambia el estado y lo que se puede hacer después`;
  que `actor_id` sea `localStorage['tflow_actor']` o `null` `(sin test)`
- [ ] Dado el tipo `nino`, cuando se pulsa `+ Nueva`, entonces el formulario pide `ci` y `fecha_nac`
  y `nivel` es un `select` con `—`, `primaria`, `secundaria`, `utu` — sin endpoint (campos de
  `GET /domain`) — `review-ui/tests/dominio.spec.js::crear una entidad usa los campos que declara el DSL`
- [ ] Dado el formulario de nueva entidad con identificador y obligatorios, cuando se pulsa Crear,
  entonces se manda `{entity_id, fields}`, aparece `<tipo> <id> creado en estado inicial.` y queda
  abierta su ficha (`review-ui/src/dominio.jsx:127-132`, `review-ui/src/dominio.jsx:436-453`) —
  `POST /entities/{tipo}` (`entities:write`) — `(sin test)`: el test solo inspecciona el formulario
- [ ] Dados un `nino` y un `curso`, cuando desde la ficha del niño se pulsa `+ Vincular`, se elige el
  curso en el `select` de destino, se completa `fecha_inscripcion` y se pulsa Vincular, entonces
  aparece un aviso con `PENDIENTE` y el vinculo `inscripcion` figura en la lista — `GET /entities/curso`
  y `POST /relations/inscripcion` con `{from_id, to_id, fields}` (`entities:write`) —
  `review-ui/tests/dominio.spec.js::vincular desde la ficha crea la relación en su estado inicial`
- [ ] Dada una `inscripcion` en `PENDIENTE`, cuando se abre la ficha del niño, entonces el vinculo
  ofrece cada `via` que sale de `PENDIENTE` y no ofrece `completar → ` — `GET /entities/nino/{id}/360` —
  `review-ui/tests/dominio.spec.js::el vínculo ofrece solo las transiciones válidas desde su estado`
- [ ] Dado un vinculo con transiciones disponibles, cuando se opera desde la ficha, entonces:
  - pulsar una transicion manda `{via, actor_id}` y muestra `El vínculo <tipo> pasó a <estado>`
    (`review-ui/src/dominio.jsx:91-100`) — `POST /relations/{tipo}/{id}/transition` (`entities:write`) — `(sin test)`
  - `+ Vincular` solo aparece si hay relaciones cuyo `from_ref` es el tipo abierto
    (`review-ui/src/dominio.jsx:89`, `review-ui/src/dominio.jsx:254-256`) — `(sin test)`
  - sin entidades destino, el formulario dice `No hay <tipo> para vincular. Creá uno primero.`
    (`review-ui/src/dominio.jsx:379-381`) — `(sin test)`
- [ ] Dada una `inscripcion` activada por la API, cuando se abre la ficha del niño, entonces la
  ficha contiene `inscripcion` y la historia contiene `inscripcion.activada` —
  `GET /entities/nino/{id}/360` —
  `review-ui/tests/dominio.spec.js::activar una inscripción hace aparecer un proceso que nadie pidió`
- [ ] Dada la ficha 360, cuando la respuesta trae `procesos_activos` y `alertas`, entonces el bloque
  Procesos en curso muestra status, nombre (`flow` o `flow_name`) y paso, y el bloque Alertas
  muestra severidad, regla y mensaje (`review-ui/src/dominio.jsx:200-220`) —
  `GET /entities/{tipo}/{id}/360` — `(sin test)`

### Proxy nginx, imagen y dev server

- [ ] Dada la cadena de timeouts, cuando se comparan, entonces el del proveedor LLM es menor que
  `compose_timeout` del gateway (660 s, `teleflow/common/config.py:58`) y este menor que
  `proxy_read_timeout` de nginx (720 s, `review-ui/nginx.conf.template:45-47`) — aplica a
  `POST /compose` — `(indirecto)` `tests/test_composer.py::test_la_cadena_de_timeouts_es_estrictamente_creciente`;
  `proxy_send_timeout 720s` y `proxy_connect_timeout 10s` `(sin test)`
- [ ] Dada una peticion a `/api/<ruta>` en `:3100`, cuando pasa por nginx, entonces llega al
  gateway como `/<ruta>` (`review-ui/nginx.conf.template:30-33`) — todos — `(indirecto)`: todos los
  tests de Playwright usan `/api/...` contra el bundle servido
  (`review-ui/tests/revision.spec.js:15`, `.github/workflows/ci.yml:101-119`)
- [ ] Dado el contenedor de la UI, cuando se sirve, entonces:
  - una ruta que no es archivo devuelve `index.html` (`review-ui/nginx.conf.template:13-15`) — `(sin test)`
  - con el gateway caido el contenedor arranca igual y `/api/` responde `502`, porque el upstream va
    en variable y se resuelve por request con `NGINX_LOCAL_RESOLVERS`
    (`review-ui/nginx.conf.template:19-33`, `review-ui/Dockerfile:18-21`) — `(sin test)`
  - el upstream es `GATEWAY_ORIGIN`, por default `http://api-gateway:8000` (`review-ui/Dockerfile:17`) y
    en el chart el FQDN `http://<release>-api-gateway.<namespace>.svc.<clusterDomain>:8000`
    (`helm/teleflow/templates/review-ui.yaml:34-35`) — compose `(indirecto)` por el job e2e;
    chart `(sin test)`
- [ ] Dado el build de la imagen, cuando corre, entonces instala con `npm ci` sobre
  `package-lock.json` sin bajar navegadores de Playwright y copia `dist` a nginx
  (`review-ui/Dockerfile:1-11`, `review-ui/Dockerfile:22`) — sin endpoint — `(indirecto)`: el job e2e
  levanta el compose con esta imagen antes de `npm test` (`.github/workflows/ci.yml:101-119`)
- [ ] Dado `npm run dev` con el gateway en `localhost:8000`, cuando la UI pide `/api/<ruta>`,
  entonces Vite la proxya a `http://localhost:8000/<ruta>` (`review-ui/vite.config.js:7-15`) —
  todos — `(sin test)`: la suite no prueba el dev server a proposito
  (`review-ui/playwright.config.js:3-5`)

## Impacto en lo existente

Esta carpeta no cambia codigo. Lo que depende del modulo, y por lo tanto se rompe si cambia:

- **Contrato de respuestas que la UI lee por nombre de campo.** Borradores: `draft_id`, `name`,
  `status`, `validation.parses/issues/error`, `provider`, `editado`, `source`, `base_source`,
  `source_generado` (`teleflow/composer_service/main.py:279-301`). Instancias: `instance_id`,
  `flow_name`, `status`, `current_step`, `updated_at`, `created_at`, `flow_version`,
  `correlation_id`, `error.step/message`, `transitions[].to/step_name/actor_id/occurred_at`
  (`review-ui/src/ops.jsx:138-191`, `review-ui/src/ops.jsx:344-393`). Dominio: `entities[]`,
  `relations[]` con `fields`, `lifecycle.transitions[].from_state/to_state/via`, `from_ref.parts`,
  `to_ref.parts` (`review-ui/src/dominio.jsx:15-16`, `review-ui/src/dominio.jsx:86-89`). Ficha 360:
  `id`, `entity`, `estado_actual`, `campos`, `relaciones_activas`, `procesos_activos`, `alertas`,
  `timeline` (`review-ui/src/dominio.jsx:166-235`). Renombrar un campo en el composer o el
  executor rompe la pantalla sin error de compilacion: solo lo detecta Playwright, en el job e2e.
  Ya paso una vez con `flow` vs `flow_name` (`review-ui/src/dominio.jsx:204-207`).
- **AST del flow desplegado.** El alta de expedientes lee `ast.processes[*].name/input[]` con
  `name`, `type`, `required`, `optional`, `enum_values` (`review-ui/src/ops.jsx:231-241`,
  `review-ui/src/ops.jsx:306-321`): cambiar `to_jsonable` o los nombres de `FieldDef` cambia el
  formulario.
- **Scopes.** Si cambia el scope de un endpoint de la tabla de Alcance, cambia que clave puede usar
  cada seccion; la UI no chequea permisos.
- **Timeouts.** Subir `compose_timeout` por encima de 720 s exige subir `proxy_read_timeout` en
  `review-ui/nginx.conf.template` en el mismo cambio, o `tests/test_composer.py` falla.
- **Retiro de pantallas.** Cada criterio de arriba es una fila del checklist de paridad del
  asistente. `review-ui/src/api.js` es el unico lugar donde la UI toca la API, asi que la lista de
  endpoints de Alcance es completa para la UI en este commit.
- **Chart.** El Deployment depende de `uiImage`, `reviewUi.enabled/replicas/port` y
  `clusterDomain` (`helm/teleflow/values.yaml:6-8`, `helm/teleflow/values.yaml:18-20`,
  `helm/teleflow/values.yaml:166-169`).

## Fuentes

- `review-ui/src/App.jsx:1-511` — secciones, key, revision, editor, diff, componer; `:7-16` corte
  por scopes y exposicion pendiente.
- `review-ui/src/api.js:1-101` — cliente y endpoints; `:35-38` razon del scope de la edicion.
- `review-ui/src/diff.js:1-31` — `lineDiff`.
- `review-ui/src/ops.jsx:1-411` — bandeja, ficha, firma, reintento, nuevo expediente.
- `review-ui/src/dominio.jsx:1-499` — tipos, ficha 360, transiciones, altas, vinculos.
- `review-ui/src/main.jsx:1-6` — montaje.
- `review-ui/nginx.conf.template:1-49` — SPA, proxy `/api/`, resolver, timeouts.
- `review-ui/Dockerfile:1-23` — build `npm ci` y nginx.
- `review-ui/vite.config.js:1-17` — dev server `:3100` y proxy.
- `review-ui/playwright.config.js:1-24`, `review-ui/playwright.demo.config.js:1-42`.
- `review-ui/package.json:1-22` — scripts y dependencias.
- `review-ui/tests/revision.spec.js`, `review-ui/tests/operacion.spec.js`,
  `review-ui/tests/dominio.spec.js` — 34 tests.
- `teleflow/gateway/main.py:664-816` — rutas y scopes; `teleflow/gateway/auth.py:29-40` — scopes.
- `teleflow/composer_service/main.py:138-301` — listado, approve, reject, edicion, `_draft_out`.
- `tests/test_composer.py:622-648` — cadena de timeouts.
- `docker-compose.yml:156-161`, `helm/teleflow/templates/review-ui.yaml:1-65`,
  `helm/teleflow/templates/ingress.yaml:1-15`, `helm/teleflow/values.yaml:166-169`.
- `.github/workflows/ci.yml:101-128` — Playwright en el job e2e.
- [[2026-08-27-correccion-del-borrador-en-la-revision]] — edicion en pantalla, validacion en servidor,
  badge invalidado, diff contra el modelo, scope `flows:deploy`.
- [[2026-07-25-composer-llm-fallos-explicitos]] — `provider` y `validation` en el borrador para que la
  UI muestre "esto lo escribió el stub" (`:58-67`).

## Discrepancias doc ↔ codigo

Comprobadas, sin corregir:

- `wiki/Knowledge/backlog-hardening.md:103` dice "8 tests de Playwright"; hoy hay 34 (18 + 9 + 7).
  El mismo item dice "266 líneas en 4 archivos" y "Cero tests, sin lint" (`:106-107`): hoy `src/`
  tiene 6 modulos (`App.jsx` solo tiene 511 lineas) y sigue sin lint. Lo de la key en
  `localStorage` (`:108-109`) sigue vigente. Nota: el archivo tiene cambios sin commitear en el
  working tree; las lineas se leyeron de ahi, no de `ffd585d`.
- `review-ui/tests/revision.spec.js:3` dice "La UI es chica (266 líneas)" y
  `review-ui/playwright.config.js:10-11` habla de "una suite de 6 tests".
- El ADR de correccion del borrador cita `App.jsx:57-64` (confirmacion al aprobar algo roto) y
  `App.jsx:265` (`lineDiff`) (`wiki/Knowledge/decisions/2026-08-27-correccion-del-borrador-en-la-revision.md:57-58`, `:73-74`,
  `:170-171`); hoy estan en `review-ui/src/App.jsx:154-159` y `review-ui/src/App.jsx:492`.
- El mismo ADR dice que `base_source` "ningún formulario lo envía" y deja exponerlo fuera de alcance
  (`:59-63`, `:83-84`, `:173`); hoy el formulario de componer lo manda cuando existe un flow con ese
  nombre (`review-ui/src/App.jsx:466-468`). No se encontro un ADR que registre ese cambio.
- El ADR decide que lo editado se valide "vía `POST /parse`" (`:68-69`); la implementacion valida
  del lado del composer dentro de `PATCH /drafts/{id}/source`
  (`teleflow/composer_service/main.py:269`), sin pasar por `POST /parse` del gateway. El principio
  (validar en servidor, nunca en el navegador) se cumple.
- `review-ui/src/api.js:37-38` justifica `flows:deploy` para editar porque "aprobar despliega esta
  columna"; pero aprobar exige solo `compose:write` en el gateway (`teleflow/gateway/main.py:795-798`,
  documentado asi en `teleflow/gateway/auth.py:38`) y el deploy lo hace el composer con su propia key
  (`teleflow/composer_service/main.py:173-179`). Una clave con `compose:write` y sin `flows:deploy`
  no puede corregir un borrador pero si aprobarlo y desplegarlo. No es un error de la UI; se anota
  porque el razonamiento del comentario no coincide con el corte real.
- `review-ui/tests/dominio.spec.js::activar una inscripción hace aparecer un proceso que nadie pidió`
  no comprueba ningun proceso: sus asserts son `inscripcion` en la ficha e `inscripcion.activada` en
  la historia (`review-ui/tests/dominio.spec.js:228-231`).
- `abrirExpediente(page, id)` no usa `id`: abre el primer expediente `WAITING_SIGNAL` de la bandeja
  (`review-ui/tests/operacion.spec.js:46-65`). La prueba de `aprobar desde la ficha…` depende de que
  el expediente recien creado quede primero.
- `wiki/Knowledge/guides/flujos-negocio.md:123` dice "Sin UI operativa: … la review-ui solo cubre
  borradores IA"; `review-ui/src/ops.jsx` y `review-ui/src/dominio.jsx` existen. En la misma linea
  van `docs/teleflow-arquitectura.typ:163`, `README.md:18` y `spec/constitution/tech_stack.md:48`,
  que describen la UI solo como revision PR-style.
- `AGENTS.md:15-17` remite a `spec/features/asistente-conversacional/` "cuando exista"; no existe
  en este commit.
