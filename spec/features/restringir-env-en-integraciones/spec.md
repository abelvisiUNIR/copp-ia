---
project: copp-ia
type: spec
status: borrador
feature: restringir-env-en-integraciones
jira_parent: <pendiente>
provenance: copp-ia@devyos@ffd585d
created: 2026-09-14
---

<!-- status: borrador | consolidada | implementada (linea base as-built, sin jira_parent) -->
<!-- Lo escribe el subagente `analista-requisitos` (comando /especificar). -->


# Restringir `${env.*}` en integraciones a un prefijo dedicado

## Problema

Un flow puede leer **cualquier** variable del entorno del executor y mandarla a un host que elige
el autor del flow. Es una clase de problema, no un bug puntual: el mecanismo que existe para *no*
escribir credenciales en el `.tflow` es el mismo que permite sacarlas de la plataforma.

Hechos comprobados (`copp-ia@devyos@ffd585d`):

- **El nombre no tiene restriccion.** La referencia se reconoce con
  `\$\{env\.([A-Za-z_][A-Za-z0-9_]*)\}` (`teleflow/executor_service/adapters.py:31`) y se
  resuelve con `os.environ.get(nombre)` sin filtrar el nombre
  (`teleflow/executor_service/adapters.py:72`). Hoy solo se chequea que la variable exista y no
  este vacia (`teleflow/executor_service/adapters.py:73-83`).
- **El valor resuelto sale del proceso.** En una integracion REST se resuelven `base_url`,
  `auth_header` (va como `Authorization`) y `api_key` (va en un header cuyo nombre elige el autor
  con `api_key_header`) (`teleflow/executor_service/adapters.py:121-131`), y el request sale hacia
  esa `base_url` (`teleflow/executor_service/adapters.py:135-139`). El `path` del step tambien se
  resuelve (`teleflow/executor_service/adapters.py:122`). Los otros puntos de resolucion son la
  `url` de AMQP (`teleflow/executor_service/adapters.py:168-169`), `host`, `from_address`,
  `username`, `password` y `subject` de SMTP (`teleflow/executor_service/adapters.py:224-229`) y
  `base_url` y `token` de SMS (`teleflow/executor_service/adapters.py:259-260`).
- **El entorno del executor tiene credenciales de plataforma.** En compose todos los servicios
  Python heredan el mismo bloque, que incluye `DATABASE_URL`, `RABBITMQ_URL`, `TELEFLOW_API_KEY` y
  `TELEFLOW_API_KEY_SCOPES` (`docker-compose.yml:3-8`, aplicado al executor en
  `docker-compose.yml:103-107`). En el chart, todos los Deployments usan la misma plantilla de env
  (`helm/teleflow/templates/deployments.yaml:46-47`), que inyecta `DATABASE_URL`, `RABBITMQ_URL`,
  `TELEFLOW_API_KEY` y `LLM_API_KEY` (`helm/teleflow/templates/_helpers.tpl:243-277`).
- **La key de bootstrap tiene todos los scopes por default**: `teleflow_api_key_scopes = "*"`
  (`teleflow/common/config.py:23`; `docker-compose.yml:8`). Entre esos scopes esta `keys:admin`,
  que "reparte permisos" (`teleflow/gateway/auth.py:39`).
- **El validator no mira `${env.*}`.** Para integraciones solo verifica que la referencia del step
  apunte a una integracion existente (`teleflow/dsl/validator.py:128-136`); el transformer guarda
  el config como un `dict` de literales sin inspeccionar (`teleflow/dsl/transformer.py:429-430`;
  gramatica `teleflow/dsl/teleflow.lark:156`). Un flow con una referencia a una variable de
  plataforma pasa `POST /parse` y se registra con `POST /flows/{name}`
  (`teleflow/gateway/main.py:604-652`).
- **El validator no es la unica puerta.** El registry-service registra lo que le mandan sin
  re-parsear ni validar (`teleflow/registry_service/main.py:74-97`) y es alcanzable desde la red
  interna sin auth (`spec/features/base-lenguaje-tflow/seguridad.md:93`). Ademas una version vieja
  sigue siendo ejecutable pidiendola explicitamente (`teleflow/executor_service/engine.py:431-442`).

Consecuencia: quien tenga `flows:deploy` ("registrar una version nueva = ejecutar codigo nuevo",
`teleflow/gateway/auth.py:30`) puede hacer salir una credencial de plataforma. Con la key de
bootstrap eso equivale a todos los scopes; con las URLs de datos, a la base y al broker. Severidad
alta en `spec/features/base-lenguaje-tflow/seguridad.md:89` y en
`wiki/Knowledge/backlog-hardening.md:147-169` (item 8).

`(inferencia)` En `audit_log` el deploy de un flow asi no se distingue de uno legitimo: se guardan
version y checksum, no la fuente (`spec/features/base-lenguaje-tflow/seguridad.md:70-72`).

## Objetivo

Que un flow solo pueda referenciar variables de entorno destinadas a integraciones, y que un
intento de referenciar cualquier otra se corte en el deploy y, si igual llega a ejecutarse, falle
sin resolver el valor.

## Alcance

**Entra:**
- Un **prefijo dedicado** para las variables que un flow puede referenciar. Propuesta:
  `TFLOW_INTEG_` (la misma direccion que anota `spec/features/base-lenguaje-tflow/seguridad.md:89`).
  **El nombre lo decide una persona** (pregunta abierta 2). En esta spec, "el prefijo" refiere al
  que se decida; los ejemplos usan la propuesta.
- **Chequeo en el validator**: toda referencia `${env.X}` en el config de un bloque `integration`
  y en el `path` de un step cuya `X` no empiece con el prefijo es un issue de nivel `error`. Como el
  deploy bloquea con errores (`teleflow/gateway/main.py:625-629`), el flow no se registra.
- **Chequeo en runtime** (defensa en profundidad para flows ya registrados, versiones viejas
  ejecutadas por version explicita y registros que no pasaron por el validator): una referencia
  fuera del prefijo es error permanente, sin leer el valor, en todos los puntos de resolucion
  listados en el Problema.
- **Una sola definicion de la regla**: el validator y el runtime aceptan exactamente el mismo
  conjunto de nombres.
- **Alineacion de ejemplos y documentacion**: `examples/ceibal.tflow:377-391`,
  `docs/teleflow-dsl-reference.typ:32`, `docs/teleflow-deployment.typ:290`,
  `.env.example:63-89`, `README.md:75-81`, el prompt del composer
  (`teleflow/composer_service/providers.py:145-146`) y el docstring de
  `teleflow/executor_service/adapters.py:3-4`.
- **Compose y chart**: un camino documentado para darle al executor las variables de integracion
  del organismo con el prefijo. En el chart, desde un Secret que administra el organismo, sin
  valores en claro.
- **Checklist de instalacion**: un paso para las variables de integracion en
  `docs/checklist-instalacion.md`.
- Actualizar la linea base `spec/features/base-lenguaje-tflow/` (el validator cambia de
  comportamiento; `AGENTS.md:98-99` pide hacerlo en el mismo commit).

**No entra (y por que):**
- **Allowlist de hosts de salida** (a que dominios puede llamar una integracion). Es otra
  feature: el prefijo corta la fuga de *credenciales de plataforma*, pero un flow sigue pudiendo
  mandar datos del expediente (payload) a un host arbitrario. Eso se resuelve con politica de red
  o una lista de destinos por instalacion, que es otra decision; hoy el chart no tiene
  NetworkPolicy (`spec/features/base-lenguaje-tflow/seguridad.md:93`).
- **Separar el entorno por servicio** (que cada servicio reciba solo las variables que usa). Es
  otra feature, complementaria: hoy hasta el parser-service recibe todas las credenciales sin
  usarlas (`spec/features/base-lenguaje-tflow/seguridad.md:95`). Aun separado, el executor
  necesita `DATABASE_URL` y `RABBITMQ_URL`, asi que separar no reemplaza al prefijo; y el prefijo
  no reduce lo que expone un compromiso de otro servicio.
- **Rotacion de la key de bootstrap y default de scopes `*`.** Es un problema de operacion
  distinto (el default esta a proposito para no romper instalaciones, `teleflow/common/config.py:19-23`)
  y el checklist ya pide acordar la rotacion (`docs/checklist-instalacion.md:165-166`). Si una
  instalacion sospecha que el hueco se uso, rotar es una accion operativa, no algo que entregue
  esta feature.
- **Integracion AMQP sin `url`**: cae a `RABBITMQ_URL` del proceso
  (`teleflow/executor_service/adapters.py:168-169`) y publica con el exchange y la routing key que
  declara el flow (`teleflow/executor_service/adapters.py:170-188`). No es una referencia
  `${env.*}` y el valor no viaja a un host externo, asi que el prefijo no lo cubre. `(inferencia)`
  permite publicar en colas internas de la plataforma; se deriva a `seguridad-infra` / backlog.
- **Redactar valores resueltos en mensajes de error.** El mensaje de un fallo REST incluye la
  `base_url` ya resuelta (`teleflow/executor_service/adapters.py:144`, `:150-151`) y termina en
  `process_instances.error` y en `instance_transitions` (`teleflow/executor_service/engine.py:897-902`).
  Es un secreto *legitimo* que queda en logs y base, no una fuga hacia afuera: otro problema.
- **Validar el resto de las claves de `integration`** (claves desconocidas, tipos). Hueco ya
  documentado en `spec/features/base-lenguaje-tflow/spec.md:113-117`; esta feature solo mira
  las referencias `${env.*}`.
- **Decidir que pasa con los flows ya desplegados** que usan otros nombres: queda como pregunta
  abierta 1, porque es cambio de contrato y lo decide una persona.

## Criterios de aceptacion

Los ejemplos usan el prefijo propuesto `TFLOW_INTEG_`; si se decide otro, se reemplaza en todos.

**Validacion en el deploy**

- [ ] Dado un flow con `integration "lms" { base_url: "${env.LMS_URL}" }`, cuando se envia a
  `POST /parse` del gateway, entonces la respuesta es 200 con `valid: false` y un issue con
  `level: "error"`, `block: "integration.lms"` y un `message` que nombra `LMS_URL`, la clave
  `base_url` y el prefijo requerido.
- [ ] Dado el mismo flow, cuando se envia a `POST /flows/{name}`, entonces la respuesta es 422
  con ese issue en `issues`, y `GET /flows/{name}` no lista la version enviada.
- [ ] Dado un flow con un step `automated` cuyo `path` contiene `${env.X}` con `X` fuera del
  prefijo, cuando se envia a `POST /parse`, entonces hay un issue `error` con
  `block: "step.<nombre>"` que nombra `X`.
- [ ] Dado un bloque `integration` con dos o mas referencias fuera del prefijo (en la misma clave
  o en claves distintas), cuando se valida, entonces cada variable aparece nombrada en los issues
  del bloque.
- [ ] Dado un flow cuyas referencias `${env.*}` empiezan todas con `TFLOW_INTEG_`, cuando se
  envia a `POST /parse`, entonces este chequeo no agrega ningun issue (el flow queda `valid: true`
  si no tiene otros errores), sin que las variables tengan que existir en el entorno del
  parser-service.

**Defensa en runtime**

- [ ] Dado un flow registrado sin pasar por el validator (registro directo al registry o version
  anterior al cambio) cuya integracion REST referencia `${env.X}` con `X` fuera del prefijo, y `X`
  **definida** en el entorno del executor, cuando una instancia llega al step, entonces:
  la instancia queda `FAILED` en el primer intento aunque el step declare `retries` mayor a 0;
  `error.message` nombra `X` y dice que esta fuera del prefijo permitido; el valor de `X` no
  aparece en `error`, en `instance_transitions.step_output` ni en los logs del executor; y no sale
  ningun request hacia la `base_url` (verificable con un transporte HTTP de prueba que registra
  cero llamadas).
- [ ] Dado el caso anterior, cuando se repite para cada punto de resolucion, entonces el
  resultado es el mismo en todos:
  - REST: `base_url`, `auth_header`, `api_key` y el `path` del step
    (`teleflow/executor_service/adapters.py:121-131`)
  - AMQP: `url` (`teleflow/executor_service/adapters.py:168`), sin abrir conexion al broker
  - SMTP: `host`, `from_address`, `username`, `password`, `subject`
    (`teleflow/executor_service/adapters.py:224-229`), sin abrir conexion SMTP
  - SMS: `base_url`, `token` (`teleflow/executor_service/adapters.py:259-260`)
- [ ] Dado `${env.TFLOW_INTEG_LMS_URL}` con la variable definida, cuando se resuelve, entonces se
  reemplaza por su valor como hoy (comportamiento de
  `tests/test_adapters.py::test_resolve_env`, con el nombre migrado).
- [ ] Dado `${env.TFLOW_INTEG_X}` con la variable faltante o vacia, cuando se resuelve, entonces
  falla como hoy: error permanente que nombra la variable
  (`tests/test_adapters.py::test_una_variable_de_entorno_faltante_falla_y_dice_cual`,
  `tests/test_adapters.py::test_una_variable_vacia_cuenta_como_faltante`,
  `tests/test_adapters.py::test_falta_de_config_no_es_transitoria`, con los nombres migrados).

**Una sola regla**

- [ ] Dado cualquiera de estos valores, cuando se pasan por el validator y por la resolucion de
  runtime, entonces los dos dan el mismo veredicto:
  - `${env.TFLOW_INTEG_LMS_URL}` → aceptado
  - `${env.LMS_URL}` → rechazado
  - `${env.DATABASE_URL}` → rechazado
  - `${env.TELEFLOW_API_KEY}` → rechazado
  - `Bearer ${env.TFLOW_INTEG_TOKEN}/${env.RABBITMQ_URL}` → rechazado (una referencia valida no
    habilita a las demas del mismo valor)
- [ ] Dado el prefijo decidido, cuando se compara con los nombres de variable que lee la
  plataforma (los campos de `teleflow/common/config.py:7-93` en mayusculas y las claves de
  `docker-compose.yml:3-26`), entonces ninguno empieza con el prefijo.

**Ejemplos y documentacion**

- [ ] Dado `examples/ceibal.tflow` migrado al prefijo, cuando corre
  `tests/test_validator.py::test_los_ejemplos_del_repositorio_quedan_limpios`, entonces pasa sin
  issues.
- [ ] Dado el repo, cuando se buscan ocurrencias de `${env.` en `examples/`, `docs/`, `README.md`,
  `.env.example` y `teleflow/composer_service/`, entonces toda ocurrencia usa el prefijo o explica
  la regla; y `docs/teleflow-dsl-reference.typ` dice que solo se resuelven variables con el prefijo
  y que el deploy rechaza las demas.
- [ ] Dado el prompt del composer, cuando se lee la instruccion sobre `integration`
  (`teleflow/composer_service/providers.py:145-146` hoy), entonces pide `${env.<prefijo>...}` y no
  `${env.VAR}` libre.

**Compose, chart e instalacion**

- [ ] Dado `docker-compose.yml` y un `.env` que define `TFLOW_INTEG_LMS_URL`, cuando se levanta
  el stack, entonces el executor-service ve esa variable en su entorno (hoy el bloque
  `x-python-env` es una lista cerrada, `docker-compose.yml:3-26`, y no hay `env_file:`).
- [ ] Dado un Secret del organismo con claves que empiezan con el prefijo, cuando se hace
  `helm template` referenciandolo por el value que defina el plan, entonces el Deployment del
  executor-service recibe esas variables por referencia al Secret y ningun valor aparece en claro
  en el render; y sin ese value el render sigue funcionando igual que hoy (instalable sin
  overrides, `spec/constitution/mission.md:23-26`).
- [ ] Dado `docs/checklist-instalacion.md`, cuando se lee, entonces tiene un item que dice que las
  variables de integracion llevan el prefijo, como se cargan en el Secret del organismo y que un
  flow con otros nombres no se puede desplegar.

## Impacto en lo existente

- **Cambio de contrato del DSL.** Un `.tflow` que hoy valida (`examples/ceibal.tflow:379-390`)
  pasa a ser invalido. Cualquier flow registrado con nombres fuera del prefijo deja de poder
  ejecutar ese step (salvo lo que decida la pregunta abierta 1). Candidato a ADR (abajo).
- **Tests que cambian**: `tests/test_adapters.py:27-64` y `:143-148` usan `TOKEN`, `NO_EXISTE`,
  `VACIA` y `LMS_URL`; el fixture e2e despliega `examples/ceibal.tflow`
  (`tests/e2e/conftest.py:48`) y fallaria con 422 si el ejemplo no se migra en el mismo cambio.
- **Operacion**: el `.env` de desarrollo y el entorno de cada organismo renombran sus variables de
  integracion (`LMS_URL` → `TFLOW_INTEG_LMS_URL`, etc., `.env.example:80-89`).
- **Chart**: value nuevo para el Secret de integraciones y, probablemente, un assert nuevo en el
  job `chart` de CI (`spec/constitution/tech_stack.md:92-94`) `(inferencia)`.
- **Composer**: los borradores generados con el prompt actual usan `${env.VAR}` libre
  (`teleflow/composer_service/providers.py:145`) y quedarian invalidos hasta cambiar el prompt.
- **Linea base**: `spec/features/base-lenguaje-tflow/spec.md:113-117` (claves de `integration` no
  validadas) y `spec/features/base-lenguaje-tflow/seguridad.md:89` pasan a describir algo que cambio.
- **Sin migracion Alembic** `(inferencia)`: la regla vive en validator y adapters; los flows
  registrados no se reescriben porque las versiones son inmutables
  (`teleflow/registry_service/main.py:83-87`).

**Candidato a ADR:** *Contrato de `${env.*}` en integraciones* — que variables puede leer un flow,
con que prefijo, en que capas se chequea (validator + runtime) y que pasa con los flows ya
registrados. Ya anotado en `spec/features/base-lenguaje-tflow/plan.md:183`.

## Preguntas abiertas (las responde una persona antes de diseñar)

1. **Flows ya desplegados con otros nombres** (p.ej. `ceibal` con `LMS_URL`). Las versiones son
   inmutables (`teleflow/registry_service/main.py:83-87`), asi que "migrar" es desplegar una
   version nueva. Opciones:
   - **A. Rechazo inmediato.** Desde el upgrade, el runtime rechaza los nombres viejos; el
     organismo despliega una version nueva con el prefijo. Costo bajo si no hay instalaciones
     productivas (`spec/features/base-lenguaje-tflow/plan.md:169` lo afirma citando el ADR de
     caida secuencial). Rompe instancias en vuelo que lleguen al step.
   - **B. Periodo de gracia.** Por un tiempo o hasta una version, el runtime resuelve nombres
     viejos con warning y metrica. Reabre el hueco mientras dure; si se elige, habria que acotarlo
     (p.ej. solo nombres que el operador liste, nunca variables de plataforma) y el criterio de
     defensa en runtime se reescribe explicitamente.
   - **C. Prefijo implicito.** El autor sigue escribiendo `${env.LMS_URL}` y la plataforma lee
     `TFLOW_INTEG_LMS_URL`. Los flows registrados siguen funcionando sin redeploy si el operador
     renombra la variable; cambia la semantica de la sintaxis y colisiona con la pregunta 2.
   - **D. Deteccion previa** (combinable con A o B): un reporte de flows registrados —latest y
     versiones viejas ejecutables (`teleflow/executor_service/engine.py:431-442`)— con referencias
     fuera del prefijo, para correr antes del upgrade.
2. **Nombre y forma del prefijo.** `TFLOW_INTEG_` es una propuesta. Tambien: si el autor escribe
   el nombre completo (`${env.TFLOW_INTEG_LMS_URL}`) o la plataforma lo agrega (opcion C), y si
   conviene una sintaxis distinta que no diga `env` (p.ej. `${integ.*}`).
3. **¿Warning o error en `/parse`?** Esta spec propone `error` en los dos endpoints (el deploy solo
   bloquea con errores, `teleflow/gateway/main.py:625-629`). Confirmar que no se quiere un warning
   transitorio mientras dure una eventual gracia (opcion B).
4. **Chart**: ¿el Secret de integraciones se monta solo en el executor o en todos los servicios
   como hoy? Solo en el executor adelanta parte de "separar el entorno por servicio", que esta
   fuera de alcance.

## Fuentes

- `teleflow/executor_service/adapters.py:3-4,31,48-84,119-159,168-169,222-229,257-261` — regex,
  resolucion y puntos donde se usa el valor
- `teleflow/executor_service/engine.py:431-442,592-634,897-902` — version explicita, error
  permanente sin reintento, persistencia del error
- `teleflow/executor_service/domain.py:70-81,94-106` — el executor carga la version `latest` y
  re-parsea sin validar
- `teleflow/dsl/validator.py:33-37,128-136` — `ValidationIssue` y chequeo actual de integraciones
- `teleflow/dsl/transformer.py:423-430`, `teleflow/dsl/teleflow.lark:137,155-157` — config y `path`
  como literales libres
- `teleflow/parser_service/main.py:52-86` — `/parse` devuelve `valid` e issues con `block`
- `teleflow/gateway/main.py:604-659,670` — deploy (422 con errores) y `/parse`
- `teleflow/gateway/auth.py:30,39` — `flows:deploy` y `keys:admin`
- `teleflow/registry_service/main.py:37-42,74-97` — registro sin validar, versiones inmutables
- `teleflow/common/config.py:7-23` — settings y scopes `*` por default
- `teleflow/composer_service/providers.py:145-146` — prompt con `${env.VAR}`
- `docker-compose.yml:3-26,103-115` — entorno compartido
- `helm/teleflow/values.yaml:10-16,26-28`, `helm/teleflow/templates/_helpers.tpl:243-277`,
  `helm/teleflow/templates/deployments.yaml:46-47` — env del chart
- `examples/ceibal.tflow:377-391` — usos reales
- `.env.example:63-89`, `README.md:75-81` — variables de integracion del ejemplo
- `docs/teleflow-dsl-reference.typ:32`, `docs/teleflow-deployment.typ:290` — lo que promete la doc
- `docs/checklist-instalacion.md:42-58,161-166` — Secret de aplicacion y rotacion
- `tests/test_adapters.py:27-64,143-148`, `tests/test_validator.py:305-309`,
  `tests/e2e/conftest.py:48`
- `spec/features/base-lenguaje-tflow/seguridad.md:89,93,95`, `plan.md:168-169,183`,
  `spec.md:113-117`
- `wiki/Knowledge/backlog-hardening.md:147-169` — item 8
- [[fallas-silenciosas]]

## Discrepancias doc ↔ codigo

- **Las variables de integracion del `.env` no llegan al executor en compose.** `README.md:81`
  indica apuntar `LMS_URL` y `.env.example:79-81` la lista para ese uso, pero `docker-compose.yml`
  pasa a los contenedores solo las claves de `x-python-env` (`docker-compose.yml:3-26`) y no
  declara `env_file:` (busqueda en `docker-compose*.yml`: sin coincidencias). El `env_file` de
  pydantic (`teleflow/common/config.py:8`) no exporta a `os.environ`, que es lo que lee
  `resolve_env` (`teleflow/executor_service/adapters.py:72`). Comprobado leyendo los archivos; no
  se levanto el stack. `(inferencia)` hoy definir `LMS_URL` en `.env` no cambia el resultado del
  walkthrough.
- **`docs/teleflow-dsl-reference.typ:341`** dice que `path` "soporta interpolacion `${...}`"; el
  codigo resuelve `${env.*}` y ademas `{payload.x}` / `{steps.y.z}` sin `$`
  (`teleflow/executor_service/adapters.py:32,122`). No se corrige desde aca.
