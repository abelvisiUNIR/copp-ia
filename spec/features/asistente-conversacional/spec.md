---
project: copp-ia
type: spec
status: borrador
feature: asistente-conversacional
jira_parent: <pendiente>
provenance: copp-ia@devyos@ed672bb
created: 2026-09-14
---

<!-- status: borrador | consolidada | implementada (linea base as-built, sin jira_parent) -->
<!-- Lo escribe el subagente `analista-requisitos` (comando /especificar). -->


# Asistente conversacional con `@capacidades` como interfaz principal

## Problema

Hoy la unica interfaz para quien no arma requests a mano es `review-ui`: una app con tres
secciones fijas (Revision, Operacion, Dominio) que consume una lista cerrada de endpoints
(`spec/features/base-review-ui/spec.md:25-38`, tabla en `spec/features/base-review-ui/spec.md:80-102`).
Cada capacidad nueva exige una pantalla nueva, y la direccion vigente del producto es no
proponer mas pantallas por funcionalidad (`AGENTS.md:15-17`). El owner decidio reemplazar esa
interfaz por un chat con LLM y una barra inferior donde se invocan capacidades con `@`, en la
que las capacidades nuevas se arman a partir de las existentes y los agentes se autocorrigen.

Lo que el codigo ya ofrece como punto de partida (comprobado en `copp-ia@devyos@ed672bb`):

- **Un catalogo estable de operaciones**: toda ruta del gateway declara `operation_id`
  explicito, unico y no autogenerado (`tests/test_openapi_contract.py:26-43`,
  `tests/test_openapi_contract.py::test_toda_ruta_declara_operation_id_explicito`,
  `tests/test_openapi_contract.py::test_los_operation_id_son_unicos`). Son 27 operaciones con su
  scope (`spec/features/base-gateway-y-acceso/spec.md:66-96`).
- **12 scopes** (`teleflow/gateway/auth.py:29-49`) ya clasificados en escritura y lectura
  (`teleflow/gateway/auth.py:155-165`): la separacion "lectura directa / escritura con
  confirmacion" no necesita una segunda taxonomia.
- **Auditoria por identidad de key**: cada escritura deja `actor_name` y `actor_key_id` de la key
  que hizo el request (`teleflow/gateway/main.py:226-239`).
- **Un parser que devuelve el error con linea y columna** (`teleflow/parser_service/main.py:58-65`),
  insumo directo para que un agente corrija un `.tflow`.
- **Widgets reutilizables en la UI actual**: diff por lineas sin dependencias
  (`review-ui/src/diff.js:2`), linea de tiempo, firma y panel de error de una instancia
  (`review-ui/src/ops.jsx:324`, `review-ui/src/ops.jsx:344`, `review-ui/src/ops.jsx:365`), ficha 360,
  vinculos y altas del dominio (`review-ui/src/dominio.jsx:166`, `review-ui/src/dominio.jsx:245`,
  `review-ui/src/dominio.jsx:430`).

Lo que falta o lo impide hoy:

1. **El OpenAPI no dice que scope exige cada operacion.** El scope vive en
   `dependencies=[Depends(auth.require(...))]` (p.ej. `teleflow/gateway/main.py:604-605`,
   `teleflow/gateway/main.py:736-744`) y no hay `openapi_extra` ni `security` por operacion en el
   gateway (busqueda de `openapi_extra|security=` en `teleflow/gateway/`: sin resultados). Un
   cliente no puede filtrar capacidades por scope leyendo el contrato.
2. **Las rutas proxeadas no declaran cuerpos ni respuestas.** Devuelven `Response` crudo
   (`teleflow/gateway/main.py:745`, `teleflow/gateway/main.py:799`) armado por `_proxy` con el
   contenido del upstream (`teleflow/gateway/main.py:432-433`); ademas un mismo `operation_id`
   cubre operaciones distintas: `operar_draft` es aprobar y rechazar
   (`teleflow/gateway/main.py:795-796`) y `consultar_entities` es lista y vista 360
   (`teleflow/gateway/main.py:736-737`). El LLM no tiene esquema para armar parametros.
3. **No existe `GET /me`** ni ninguna ruta que devuelva la identidad y los scopes de la key que
   llama (busqueda de `/me` y `whoami` en `teleflow/`: sin resultados). Sin eso, la barra `@` no
   puede filtrarse por scopes.
4. **La aprobacion de un borrador despliega con una key de servicio, no con la del usuario.** El
   composer llama al deploy con `settings.teleflow_api_key` (`teleflow/composer_service/main.py:173-176`)
   y el gateway solo pide `compose:write` para `POST /drafts/{rest}`
   (`teleflow/gateway/main.py:795-798`), mientras que desplegar exige `flows:deploy`
   (`teleflow/gateway/main.py:604-605`). `(inferencia)`: el `audit_log` del deploy registra la key
   de servicio y no a quien aprobo, y una key con `compose:write` sin `flows:deploy` puede terminar
   desplegando. Un asistente que copie este patron operaria con todos los scopes en nombre de
   cualquiera (`spec/features/base-composer-ia/plan.md:235`).
5. **El proveedor LLM es de un solo turno y sin herramientas**: `generate(prompt) -> str`
   (`teleflow/composer_service/providers.py:177`), fijado por ADR-003
   (`wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:19-21`). Una respuesta que pida
   ejecutar una herramienta sin texto se leeria como fallo `(inferencia)`
   (`spec/features/base-composer-ia/plan.md:232`).
6. **El composer no se autocorrige**: valida el borrador contra el parser y guarda `parses: false`
   con los issues, sin reintentar (`teleflow/composer_service/main.py:95`,
   `teleflow/composer_service/main.py:125-135`).
7. **No hay persistencia de conversaciones.** Ninguna tabla del modelo guarda turnos
   (`teleflow/common/models.py:28-264`: `flow_definitions` ... `audit_log`), y el ADR de fallos
   del composer rechazo mezclar registros de maquina en `comments` del borrador
   (`spec/features/base-composer-ia/plan.md:234`).
8. **Los widgets no son importables**: `ops.jsx` y `dominio.jsx` solo exportan su pantalla por
   default (`review-ui/src/ops.jsx:34`, `review-ui/src/dominio.jsx:14`); los componentes internos
   no se exportan. Solo `lineDiff` es export nombrado (`review-ui/src/diff.js:2`).

## Objetivo

Que una persona del organismo haga desde un chat, invocando `@capacidades` limitadas a sus
scopes, todo lo que hoy hace en las pantallas y lo que se componga a partir de eso, con cada
escritura confirmada por ella y atribuida a su identidad en la auditoria.

## Alcance

**Entra:**

- Chat con LLM y barra inferior con autocompletado `@` sobre el catalogo de operaciones del
  gateway, filtrado por los scopes de la key del usuario.
- Resultados como tarjetas y widgets dentro del hilo (tabla, diff, linea de tiempo, ficha 360,
  error), reutilizando los componentes de `review-ui/src/`.
- Contrato del gateway necesario para el asistente: scope por operacion en el OpenAPI, esquemas
  de cuerpo y respuesta de las rutas proxeadas que el asistente invoque, y una ruta de identidad
  equivalente a `GET /me`.
- Acciones pendientes en el servidor para escrituras: tarjeta de confirmacion ligada a un hash de
  parametros, de un solo uso, compartida entre replicas.
- Ejecucion de toda capacidad con la key del usuario (decision 1 del owner), incluida la
  aprobacion de borradores.
- **Recetas**: composicion guardada y versionada de `@capacidades` existentes, invocable con `@`.
- **Procesos `.tflow`** generados por el composer con autocorreccion contra el parser, con tope
  de intentos, visible en el chat, y el borrador final por el camino normal de revision y deploy
  confirmado.
- Aviso de proveedor LLM externo, segun el proveedor que realmente corre (ADR-003).
- Paridad con los 34 tests Playwright de `review-ui` como condicion para retirar cada pantalla.

**No entra (y por que):**

- **Acceso SQL directo, lectura de tablas o conexion a la base desde el asistente.** Decision 1
  del owner: los datos del organismo pasan solo por la API del gateway, que es donde viven auth,
  scopes, rate limit y auditoria (`spec/features/base-gateway-y-acceso/spec.md:16-23`). Un camino
  por SQL saltearia las cuatro.
- **Autonomia sin confirmacion** (modo "confiar", confirmacion por lote implicita, escrituras que
  el LLM ejecuta por su cuenta). Decision 3 del owner. Tampoco entra que una receta o un turno
  confirme en nombre del usuario.
- **Multi-tenancy**: un asistente, un catalogo y un almacen de recetas por instalacion; nada se
  comparte entre organismos por base de datos. ADR-005
  (`wiki/Knowledge/decisions/2026-06-30-adr-005-aislamiento-instancia.md:19-20`). Compartir recetas
  entre organismos (p.ej. exportarlas por Git) queda para otra feature.
- **Pantallas nuevas por funcionalidad.** `AGENTS.md:17`. Las tarjetas viven dentro del hilo.
- **Recetas con logica propia** (condicionales, bucles, codigo, llamadas HTTP arbitrarias). Una
  composicion con control de flujo es un proceso, y los procesos se expresan en `.tflow`, cuya
  unica fuente de verdad es la gramatica (ADR-001, `AGENTS.md:97`). Una receta con logica seria un
  segundo lenguaje sin gramatica.
- **Cambios al DSL, a la gramatica o al validador.** La autocorreccion corrige el borrador, no las
  reglas contra las que se valida (ver bloque 6). Toda extension del DSL sigue empezando en
  `teleflow/dsl/teleflow.lark` en su propia feature.
- **Verificar que un proceso generado haga lo que se pidio.** El parser valida sintaxis y
  estructura (`teleflow/parser_service/main.py:57-68`), no intencion: un borrador puede compilar y
  hacer lo inverso (`spec/features/base-composer-ia/plan.md:230`). Eso lo sigue decidiendo la
  revision humana, que es obligatoria.
- **Paridad con flujos que hoy no tienen pantalla ni test**: editar campos de una entidad con
  `PATCH` y `api.getEntity` sin uso (`spec/features/base-review-ui/spec.md:148-151`). Las capacidades
  existen en el catalogo, pero no son requisito para retirar pantallas porque no hay flujo actual
  contra el cual medir.
- **Gestion de keys y auditoria como flujo de paridad.** Hoy no tienen pantalla (no figuran en
  `spec/features/base-review-ui/spec.md:80-102`); pueden ofrecerse como capacidades si el scope lo
  permite, pero no bloquean el retiro de pantallas.
- **Publicacion de la UI fuera del cluster.** El chart hoy no la expone y falta su ADR
  (`spec/features/base-review-ui/spec.md:135-140`); el asistente hereda esa situacion y no la decide.
- **Analisis de riesgo del almacenamiento de la key en el navegador, prompt injection y datos
  personales enviados al proveedor.** Se hace en el `seguridad.md` de esta carpeta; aca solo se
  fijan los criterios observables (bloques 3, 4 y 7).

## Criterios de aceptacion

Cada uno tiene que ser verificable por alguien que no escribio el codigo. Estos criterios se
copian **literales** a la descripcion de las cards de Jira.

Convenciones de los criterios: "capacidad" es una operacion del gateway identificada por su
`operation_id`, o una receta. "Escritura" es una capacidad cuyo scope esta en
`SCOPES_DE_ESCRITURA` (`teleflow/gateway/auth.py:155-158`); "lectura", una cuyo scope esta en
`SCOPES_DE_LECTURA` (`teleflow/gateway/auth.py:163-165`). La clasificacion es por scope y no por
metodo HTTP: `validar_flow` es `POST` y es lectura; `listar_keys` es `GET` y es escritura.

### 1. Chat y barra `@` filtrada por scopes

- [ ] Dado una key valida, cuando se consulta la ruta de identidad del gateway, entonces responde
  `200` con el nombre de la key y su lista de scopes (o `*`), y la respuesta no contiene el hash
  ni el secreto de la key.
- [ ] Dado una key invalida o revocada, cuando se consulta la ruta de identidad, entonces responde
  `401` y queda una fila en `audit_log` con `status_code = 401`.
- [ ] Dado el OpenAPI del gateway, cuando se lo descarga de `/openapi.json`, entonces cada
  operacion con `operation_id` declara el scope que exige, y un test falla si una ruta con
  `auth.require` o `auth.require_por_metodo` no lo declara o declara uno distinto.
- [ ] Dado una key con solo `flows:read`, cuando el usuario escribe `@` en la barra inferior,
  entonces la lista muestra solo capacidades cuyo scope es `flows:read` (`listar_flows`,
  `listar_versiones_flow`, `obtener_version_flow`, `validar_flow`) y no muestra `desplegar_flow`,
  `crear_key` ni ninguna otra.
- [ ] Dado una key con scope `*`, cuando el usuario escribe `@`, entonces la lista muestra las 27
  operaciones del catalogo mas las recetas que puede invocar.
- [ ] Dado una key sin un scope, cuando se fuerza la invocacion de una capacidad que lo exige (por
  texto libre o request directo), entonces el gateway responde `403`, el chat muestra una tarjeta
  de error que nombra el scope faltante y no hay reintento con otra credencial.
- [ ] Dado un pedido en lenguaje natural sin `@`, cuando el LLM elige una capacidad, entonces solo
  puede elegir entre las del catalogo filtrado para esa key; si ninguna aplica, el chat responde
  que no hay capacidad para eso y no muestra un resultado que no provenga de una respuesta del
  gateway.

### 2. Resultados como tarjetas y widgets, no pantallas

- [ ] Dado `@listar_instancias`, cuando se ejecuta, entonces el resultado aparece como tarjeta
  dentro del hilo con una fila por instancia (id, flow, estado, fecha) y la ruta del navegador no
  cambia a otra seccion.
- [ ] Dado `@obtener_draft` de un borrador de un flow ya desplegado, cuando se ejecuta, entonces la
  tarjeta muestra el diff por lineas contra la version `latest` con el mismo resultado que
  `lineDiff` (`review-ui/src/diff.js:2`) y el estado de validacion en tres valores distinguibles:
  compila (`parses: true`), no compila (`parses: false`) y no verificado (`parses: null`).
- [ ] Dado `@obtener_instancia`, cuando se ejecuta, entonces la tarjeta muestra la linea de tiempo
  de transiciones y, si la instancia espera una firma, las acciones de firma de esa tarea.
- [ ] Dado la vista 360 de una entidad, cuando se ejecuta, entonces la tarjeta muestra campos,
  estado actual, transiciones validas desde ese estado y vinculos.
- [ ] Dado una capacidad cuya respuesta del gateway es `401`, `403`, `404`, `422`, `429` o `502`,
  cuando se ejecuta, entonces la tarjeta muestra el codigo y el `detail` recibido, y nunca se
  presenta como lista vacia, "archivo nuevo" o exito (a diferencia de
  `spec/features/base-review-ui/spec.md:141-144`).
- [ ] Dado una capacidad sin widget especifico, cuando se ejecuta, entonces el resultado aparece
  como tarjeta generica con el cuerpo de la respuesta legible, dentro del hilo.

### 3. Lecturas directas, escrituras con tarjeta de confirmacion

- [ ] Dado una capacidad de lectura (incluida `validar_flow`), cuando se invoca, entonces se
  ejecuta sin tarjeta de confirmacion y el resultado aparece en el hilo.
- [ ] Dado una capacidad de escritura (incluida `listar_keys`, cuyo scope `keys:admin` es de
  escritura), cuando se invoca o el LLM la propone, entonces el chat muestra una tarjeta con el
  `operation_id`, metodo y ruta, los parametros completos y el efecto, y el gateway no recibe
  ningun request a esa ruta hasta que el usuario confirma (sin fila nueva en `audit_log` para esa
  ruta).
- [ ] Dado una tarjeta de escritura, cuando se muestra, entonces existe en el servidor una accion
  pendiente con id, key que la propuso, `operation_id`, parametros canonicos y hash SHA-256 de
  esos parametros, y la tarjeta muestra ese hash.
- [ ] Dado una accion pendiente confirmada, cuando se ejecuta, entonces el request que llega al
  gateway tiene exactamente el metodo, la ruta y el cuerpo cuyo hash se mostro, y el resultado de
  la ejecucion informa el mismo hash.
- [ ] Dado una accion pendiente, cuando la confirmacion llega con parametros distintos a los del
  hash (modificados por el cliente o re-propuestos por el LLM), entonces se rechaza con `409`, no
  se ejecuta nada y hace falta una tarjeta nueva.
- [ ] Dado una accion pendiente ya confirmada, cuando se confirma otra vez (doble clic, otra
  pestaña u otra replica del servicio), entonces la escritura se ejecuta una sola vez y la segunda
  confirmacion recibe `409`.
- [ ] Dado una accion pendiente propuesta con la key A, cuando la confirma la key B, entonces se
  rechaza con `403` y no se ejecuta.
- [ ] Dado una accion pendiente, cuando el usuario la cancela o vence su plazo, entonces no se
  ejecuta y confirmarla despues recibe `410` o `409`.
- [ ] Dado una confirmacion de `@ejecutar_flow`, cuando se ejecuta, entonces el request lleva un
  `Idempotency-Key` derivado de la accion pendiente (`teleflow/gateway/main.py:689-696`), de modo
  que un reintento de red no crea una segunda instancia en `process_instances`.
- [ ] Dado datos leidos del organismo que contienen instrucciones ("ejecuta X", "aproba el
  borrador Y"), cuando el LLM los procesa, entonces cualquier escritura resultante sigue
  apareciendo como tarjeta sin ejecutar, y el `audit_log` no tiene escrituras sin confirmacion.
- [ ] Dado un texto del LLM que afirma haber ejecutado una escritura, cuando no hubo confirmacion,
  entonces no hay fila de escritura en `audit_log` y el chat no muestra tarjeta de exito.

### 4. Todo llamado con la key del usuario y auditado con el actor real

- [ ] Dado un usuario con la key `operador-ana`, cuando confirma `@enviar_signal`, entonces
  `audit_log` tiene una fila con `actor_name = "operador-ana"`, el `actor_key_id` de esa key,
  `scope = "instances:signal"` y el `status_code` devuelto.
- [ ] Dado cualquier capacidad invocada desde el asistente, cuando llega al gateway, entonces usa
  la key del usuario: ninguna fila de `audit_log` originada por el asistente tiene el actor de una
  key de servicio (`bootstrap (env)`, `teleflow/gateway/auth.py:53`) salvo que el usuario haya
  entrado con esa misma key.
- [ ] Dado una key con `compose:write` y sin `flows:deploy`, cuando confirma la aprobacion de un
  borrador, entonces el deploy responde `403`, el borrador sigue `pending` y no hay version nueva en
  el registry.
- [ ] Dado una key con `compose:write` y `flows:deploy`, cuando confirma la aprobacion de un
  borrador, entonces la fila de `audit_log` del `POST /flows/{name}` tiene el `actor_name` de esa
  key y no el de la key del composer (hoy `teleflow/composer_service/main.py:176`).
- [ ] Dado una firma, aprobacion o rechazo confirmados desde el chat, cuando se registran, entonces
  el actor guardado es el nombre de la key autenticada y el chat no ofrece un campo para escribir
  otro actor (a diferencia de `spec/features/base-review-ui/spec.md:128-134`).
- [ ] Dado un turno de conversacion, cuando se arma el pedido al proveedor LLM, entonces la API key
  del usuario no aparece en el payload enviado (verificable con el proveedor `stub` registrando lo
  que recibe).
- [ ] Dado una key que supera su rate limit durante un turno con varias lecturas, cuando el gateway
  responde `429`, entonces el chat muestra una tarjeta de error con ese codigo y no reintenta con
  otra key.

### 5. Recetas

- [ ] Dado una secuencia de capacidades invocadas en una conversacion, cuando el usuario la guarda
  como receta con un nombre, entonces queda persistida como version `1` con sus pasos
  (`operation_id` y parametros o plantillas de parametros) y aparece en la barra `@` como
  `@<nombre>`.
- [ ] Dado una receta con un paso cuyo `operation_id` no existe en el catalogo del gateway, cuando
  se intenta guardar, entonces se rechaza con `422` nombrando el paso invalido y no se crea
  version.
- [ ] Dado una receta con un paso que no es un `operation_id` (SQL, URL arbitraria, codigo), cuando
  se intenta guardar, entonces se rechaza con `422` y no se crea version.
- [ ] Dado una receta en version `1`, cuando se edita, entonces se crea la version `2`, la version
  `1` sigue consultable sin cambios y se puede invocar una version concreta ademas de la ultima.
- [ ] Dado una receta cuyo paso exige un scope que la key del invocador no tiene, cuando el
  invocador escribe `@`, entonces la receta no aparece; y si la fuerza, entonces no se ejecuta
  ningun paso y el chat nombra el scope faltante.
- [ ] Dado una receta creada por la key A, cuando la invoca la key B, entonces cada paso llega al
  gateway con la key B y las filas de `audit_log` tienen el actor de B.
- [ ] Dado una receta con pasos de lectura y de escritura, cuando se invoca, entonces las lecturas
  se ejecutan directo y cada escritura muestra su tarjeta de confirmacion con los parametros ya
  resueltos, segun el bloque 3.
- [ ] Dado un paso de receta que falla (respuesta `>= 400` o escritura cancelada), cuando ocurre,
  entonces la receta se detiene en ese paso, la tarjeta muestra el numero de paso y el error, y
  ningun paso posterior llega al gateway.
- [ ] Dado que se guarda o edita una receta, cuando se persiste, entonces queda registrado quien la
  creo o edito (nombre de la key) y la fecha de cada version.

### 6. Procesos `.tflow` con autocorreccion visible

- [ ] Dado un pedido de proceso nuevo, cuando el composer genera un borrador que el parser marca
  `valid: false`, entonces genera un nuevo intento pasando al LLM los issues con linea y columna
  (`teleflow/parser_service/main.py:63-64`), y el chat muestra una tarjeta por intento con su
  numero, los errores con `linea:columna` y el diff contra el intento anterior.
- [ ] Dado un tope de intentos configurado en N, cuando el intento N sigue sin compilar, entonces
  no hay intento N+1, el borrador queda `pending` con `validation.parses = false` y los issues del
  ultimo intento, y el chat dice que no compila.
- [ ] Dado un intento que el parser marca `valid: true`, cuando ocurre, entonces la autocorreccion
  se detiene y el borrador queda `pending` con `validation.parses = true`.
- [ ] Dado un intento que no se pudo verificar (parser caido, `parses: null`), cuando ocurre,
  entonces no cuenta como compilado ni se reintenta a ciegas: la autocorreccion se detiene y el
  chat informa "no se pudo verificar".
- [ ] Dado el borrador final de una autocorreccion, cuando se vuelve a validar su fuente con
  `@validar_flow`, entonces el resultado `valid` coincide con el `validation.parses` guardado.
- [ ] Dado una autocorreccion en curso, cuando se revisan los cambios que produjo, entonces lo
  unico modificado es la fuente del borrador: `teleflow/dsl/teleflow.lark`,
  `teleflow/dsl/validator.py`, las reglas desplegadas y los flows del registry no cambian, y el
  catalogo de capacidades del asistente no incluye ninguna operacion que los modifique.
- [ ] Dado un borrador que compila tras la autocorreccion, cuando termina, entonces no se aprueba ni
  se despliega solo: sigue `pending` hasta que una persona lo apruebe por tarjeta de confirmacion
  con una key que tenga `flows:deploy` (bloques 3 y 4).
- [ ] Dado un pedido de modificar un flow existente, cuando se genera, entonces el borrador parte de
  la version `latest` y la tarjeta muestra el diff contra esa version.

### 7. Aviso de proveedor LLM externo

- [ ] Dado una instalacion cuyo proveedor que realmente corre es `anthropic` u `openai`, cuando el
  usuario abre el chat, entonces ve un aviso de que los datos de la conversacion salen de la
  instalacion hacia ese proveedor, antes de poder enviar el primer mensaje, y el aviso sigue
  visible durante la conversacion.
- [ ] Dado una instalacion con proveedor `stub`, cuando el usuario abre el chat, entonces no ve el
  aviso de salida de datos.
- [ ] Dado que el proveedor pedido en la configuracion y el que realmente corre difieren, cuando se
  decide el aviso, entonces se usa el que realmente corre (el `provider.name` que el composer ya
  distingue, `teleflow/composer_service/main.py:102`).
- [ ] Dado un cambio de proveedor en la configuracion y un reinicio del servicio, cuando el usuario
  abre una conversacion nueva, entonces el aviso refleja el proveedor nuevo.

### 8. Paridad con las pruebas de `review-ui` antes de retirar pantallas

- [ ] Dado cada uno de los 34 tests Playwright de `review-ui` (18 en
  `review-ui/tests/revision.spec.js`, 9 en `review-ui/tests/operacion.spec.js`, 7 en
  `review-ui/tests/dominio.spec.js`), cuando se propone retirar la pantalla que cubre, entonces
  existe un test e2e del asistente que ejecuta el mismo flujo contra el mismo endpoint del gateway
  y verifica el mismo resultado observable, y la correspondencia test a test esta escrita.
- [ ] Dado una seccion de `review-ui` con al menos un flujo sin equivalente en verde, cuando corre
  el job e2e de CI, entonces la seccion sigue montada y sus tests siguen corriendo.
- [ ] Dado el retiro de una pantalla, cuando se hace el commit, entonces los tests Playwright de esa
  pantalla solo se retiran en el mismo commit que cita sus equivalentes conversacionales en verde.
- [ ] Dado el job e2e de CI, cuando corren los tests del asistente, entonces corren con el proveedor
  `stub` y sin llamadas a un proveedor externo.

## Impacto en lo existente

- **Contrato del gateway**: operaciones nuevas (identidad, acciones pendientes, recetas y
  posiblemente conversaciones), scope declarado por operacion en el OpenAPI y esquemas para las
  rutas proxeadas que hoy devuelven `Response` crudo. `tests/test_openapi_contract.py` se extiende
  (scope por operacion) y `docs/openapi.json` se regenera. Operaciones de grano grueso
  (`operar_draft`, `consultar_entities`) probablemente se desdoblen `(inferencia)`: cambia el
  cliente generado.
- **Aprobacion de borradores**: el deploy tiene que hacerse con la identidad de quien aprueba y no
  con `settings.teleflow_api_key` (`teleflow/composer_service/main.py:173-176`). Cambia el
  comportamiento de `POST /drafts/{id}/approve` para todo cliente, incluidos `review-ui` y
  `tflow approve` `(inferencia: el CLI usa esa misma ruta)`: una key sin `flows:deploy` deja de
  poder aprobar.
- **Proveedores LLM**: pasar de `generate(prompt) -> str` a conversacion con herramientas en
  `anthropic`, `openai`, `ollama` y `stub` exige enmendar ADR-003. Agregar un SDK de proveedor
  seria dependencia nueva y pide ADR (`AGENTS.md:113`); `httpx` ya esta en el stack
  (`spec/constitution/tech_stack.md:25`).
- **Composer**: `POST /compose` gana un modo con reintentos; la cadena de timeouts
  (`compose_timeout`) se alarga en proporcion al tope de intentos `(inferencia)`.
- **Migraciones**: tablas nuevas (acciones pendientes si van en Postgres, recetas y versiones,
  conversaciones) en `0008` o siguientes, compatibles con pods viejos durante un upgrade
  (`spec/constitution/tech_stack.md:57-58`).
- **Multiples replicas**: las acciones pendientes y su consumo unico no pueden vivir en memoria de
  un proceso (`AGENTS.md:114`).
- **Auditoria**: los scopes nuevos que se agreguen tienen que clasificarse en escritura o lectura;
  el test de exhaustividad obliga a decidir (`teleflow/gateway/auth.py:160-162`).
- **Rate limit**: un turno puede encadenar varias lecturas con la misma key y consumir su cuota
  mas rapido que una pantalla `(inferencia)`.
- **`review-ui`**: los componentes reutilizables tienen que exportarse
  (`review-ui/src/ops.jsx:34`, `review-ui/src/dominio.jsx:14`); las secciones se retiran de a una
  segun el bloque 8.
- **Chart y compose**: si el asistente es un servicio nuevo, suma Deployment, Service, variables y
  alertas en `helm/teleflow/` y en `docker-compose.yml`, y tiene que seguir instalable sin
  overrides (`spec/constitution/mission.md:39-40`).
- **DSL**: sin cambios.

## Preguntas abiertas para diseño

1. **Servicio nuevo o extension de `composer-service`.** El composer ya tiene proveedor LLM,
   borradores y validacion; un servicio nuevo separa conversacion de generacion pero suma imagen
   de deploy, config y superficie de red.
2. **Persistencia de conversaciones y datos personales.** ¿Se guardan los turnos? ¿Con que
   retencion, quien los puede leer y como se borran? Los resultados de lecturas (vista 360,
   instancias) pueden contener datos personales, y con proveedor externo esos datos ademas salen
   de la instalacion.
3. **Tool-use en los tres proveedores y el stub.** ¿Contrato comun de mensajes y herramientas, o
   el LLM devuelve una propuesta estructurada en texto que el servidor valida? ¿Como se comporta
   `ollama` segun el modelo? ¿El `stub` necesita guion determinista para los tests e2e?
4. **Migracion `0008`.** Que tablas (conversaciones, turnos, acciones pendientes, recetas,
   versiones de receta, intentos de autocorreccion) y si las acciones pendientes van en Postgres o
   en Redis con TTL.
5. **Scopes nuevos.** ¿Guardar recetas y leer conversaciones necesitan scopes propios (p.ej.
   `recipes:write`, `assistant:use`)? ¿Una receta es personal o de la instalacion? Cualquier scope
   nuevo entra en `ALL_SCOPES` y en la clasificacion de auditoria.
6. **Aviso con `ollama`.** Puede apuntar a un host de la instalacion o a uno externo
   (`LLM_BASE_URL`, `teleflow/common/config.py:39`): ¿se avisa siempre, nunca o segun una
   configuracion explicita?
7. **Tope de intentos y plazo de las acciones pendientes**: valores por defecto y si son
   configurables por organismo.
8. **Escrituras en lote dentro de una receta**: ¿una tarjeta por escritura o una tarjeta que liste
   todas con un hash por paso?
9. **Streaming de respuestas**: hoy todo es bloqueante y `_proxy` devuelve el cuerpo completo
   (`teleflow/gateway/main.py:432-433`).

**Candidato a ADR**: interfaz conversacional con `@capacidades` como UI principal (reemplazo de
pantallas por funcionalidad, criterio de paridad para retirarlas y regla de confirmacion de
escrituras). Relacionados, ya propuestos en `spec/features/base-composer-ia/plan.md:240-247`:
enmienda de ADR-003 para conversacion y tool-use, identidad delegada entre servicios, scope de la
aprobacion y persistencia de conversaciones.

## Fuentes

- `AGENTS.md:15-17` — direccion de producto: asistente con `@capacidades`, sin pantallas nuevas.
- `tests/test_openapi_contract.py:26-43` — `operation_id` explicitos, unicos y no autogenerados.
- `teleflow/gateway/auth.py:29-49` — los 12 scopes; `teleflow/gateway/auth.py:53` — nombre de la
  key de bootstrap; `teleflow/gateway/auth.py:155-170` — escritura, lectura y auditados.
- `teleflow/gateway/main.py:226-239` — fila de `audit_log` con `actor_name` y `actor_key_id`.
- `teleflow/gateway/main.py:409-433` — `_proxy`: headers desde cero, cuerpo crudo del upstream.
- `teleflow/gateway/main.py:604-652` — deploy con `flows:deploy`, parse y registro.
- `teleflow/gateway/main.py:686-696` — `ejecutar_flow` propaga `Idempotency-Key`.
- `teleflow/gateway/main.py:736-800` — rutas proxeadas con `operation_id` por metodo;
  `teleflow/gateway/main.py:795-798` — `operar_draft` solo con `compose:write`.
- `teleflow/parser_service/main.py:58-68` — error de sintaxis con linea y columna, luego validacion.
- `teleflow/composer_service/main.py:95`, `teleflow/composer_service/main.py:125-135` — validacion
  del borrador sin reintento, `parses: null` si el parser no responde.
- `teleflow/composer_service/main.py:102` — el proveedor que corrio, no el pedido.
- `teleflow/composer_service/main.py:173-176` — aprobacion que despliega con la key de servicio.
- `teleflow/composer_service/providers.py:177` — `generate(prompt) -> str`.
- `teleflow/common/config.py:36-39` — `llm_provider` y `llm_base_url`.
- `teleflow/common/models.py:28-264` — tablas existentes, ninguna de conversaciones.
- `review-ui/src/diff.js:2`, `review-ui/src/ops.jsx:34`, `review-ui/src/ops.jsx:324-365`,
  `review-ui/src/dominio.jsx:14`, `review-ui/src/dominio.jsx:166-430` — widgets y sus exports.
- `review-ui/tests/revision.spec.js`, `review-ui/tests/operacion.spec.js`,
  `review-ui/tests/dominio.spec.js` — 18, 9 y 7 tests (conteo de `test(` en cada archivo).
- `spec/features/base-gateway-y-acceso/spec.md:56-100` — catalogo de 27 operaciones con scope.
- `spec/features/base-review-ui/spec.md:43-49`, `spec/features/base-review-ui/spec.md:57-178` —
  inventario de paridad y huecos de la UI actual.
- `spec/features/base-composer-ia/plan.md:231-236` — riesgos de la interfaz conversacional.
- `wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:19-21` — contrato del proveedor.
- `wiki/Knowledge/decisions/2026-06-30-adr-005-aislamiento-instancia.md:19-20` — una instancia por
  organismo.

## Discrepancias doc ↔ codigo

- **ADR-003 describe un fallback al `stub`** si falta `LLM_API_KEY`
  (`wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:29-30`); la linea base del
  composer lo registra como retirado (`spec/features/base-composer-ia/plan.md:223`). No se verifico
  `get_provider` en este commit. Importa para el bloque 7: el aviso se decide por el proveedor que
  corre, no por lo que dice el ADR.
- **Las lineas base dicen que esta carpeta no existe** (`spec/features/base-review-ui/spec.md:48-49`,
  `spec/features/base-gateway-y-acceso/spec.md:60-61`, `AGENTS.md:16` "cuando exista"). Quedan
  desactualizadas al crear este archivo; no se corrigen desde aca.
- **La linea base del gateway dice que las capacidades "se generan del OpenAPI"**
  (`spec/features/base-gateway-y-acceso/spec.md:59-60`), pero el OpenAPI de hoy no trae scopes ni
  esquemas de las rutas proxeadas (Problema, puntos 1 y 2): generarlas requiere el cambio de
  contrato de esta feature.
