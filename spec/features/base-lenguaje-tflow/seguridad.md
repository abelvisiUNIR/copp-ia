---
project: copp-ia
type: seguridad
status: implementada
feature: base-lenguaje-tflow
provenance: copp-ia@devyos@5e64479
reviewed: 2026-09-14
---

# Seguridad e infraestructura — Base del lenguaje .tflow

> Linea base as-built. Provenance: `copp-ia@devyos@5e64479`. Alcance: `teleflow/dsl/`
> (`teleflow.lark`, `parser.py`, `transformer.py`, `validator.py`, `evaluator.py`,
> `ast_nodes.py`, `serialize.py`), `teleflow/parser_service/main.py`, `examples/*.tflow` y la
> llegada de `/parse` desde afuera (`teleflow/gateway/main.py`). Donde un hallazgo depende de un
> consumidor del DSL fuera de ese alcance (executor), se cita igual y se marca como frontera.
> Las citas a Lark apuntan a la libreria instalada en `.venv/Lib/site-packages/lark/` (no
> versionada; `pyproject.toml:14` pide `lark>=1.1.9`).

## Superficie expuesta

| Superficie | Quien puede llegar | Control | Fuente |
|---|---|---|---|
| `POST /parse` (gateway :8000) | cualquier cliente con key valida | scope `flows:read` + rate limit por key | `teleflow/gateway/main.py:655-659`, `teleflow/gateway/main.py:145-163` |
| `POST /flows/{name}` (gateway :8000) | cliente con key valida | scope `flows:deploy`; valida en parser antes de persistir | `teleflow/gateway/main.py:604-652` |
| `POST /parse` (parser-service :8001) | cualquier pod/contenedor de la red interna | **ninguno** (sin auth, sin rate limit, sin auditoria) | `teleflow/parser_service/main.py:52-86` |
| `GET /health`, `/ready`, `/metrics` (parser-service) | red interna | ninguno (publicos por diseño) | `teleflow/common/observability.py:46-64` |
| `GET /docs`, `/openapi.json` (parser-service) | red interna | ninguno: `FastAPI(...)` sin `docs_url=None` `(inferencia: defaults de FastAPI)` | `teleflow/parser_service/main.py:18` |
| composer-service → `POST /parse` interno | composer (fuente generada por LLM) | ninguno | `teleflow/composer_service/main.py:118-122` |
| CLI `tflow` → `POST /parse` del gateway | operador con key | `flows:read` | `teleflow/cli.py:55` |
| Consumo en runtime del DSL: re-parseo de la fuente persistida, invariantes, `${env.*}` | executor-service | — (frontera, fuera de alcance) | `teleflow/executor_service/engine.py:442`, `entities.py:270`, `adapters.py:48-84` |

Puerto del parser en despliegue: compose no publica puertos al host
(`docker-compose.yml:83-91`, sin `ports:`); Helm lo expone como `ClusterIP`
(`helm/teleflow/templates/deployments.yaml:77-81`, `values.yaml:80-83` sin `external`).

## Controles existentes

- **El evaluador solo llama funciones de lista blanca** (confirmado). `BUILTIN_FUNCS` tiene
  cuatro entradas: `days_since`, `years_since`, `now`, `len` (`teleflow/dsl/evaluator.py:50-55`).
  Un `Func` se resuelve con `fns.get(n.name)` y un nombre desconocido levanta
  `EvaluationError` (`evaluator.py:85-89`). No hay `eval`, `exec`, `compile`, `__import__`,
  `pickle` ni `subprocess` en `teleflow/` (busqueda:
  `\beval\(|\bexec\(|__import__|\bcompile\(|importlib|subprocess|pickle|yaml\.load`; unica
  coincidencia en el alcance: `from importlib import resources` para leer la gramatica,
  `parser.py:6,39`).
- **Los nodos no evaluables fallan cerrados**: cualquier tipo de nodo no previsto levanta
  `EvaluationError` (`evaluator.py:105`); operador desconocido idem (`evaluator.py:130`).
- **El transformer no permite inyectar atributos**: todos los `setattr` usan claves literales
  fijadas por la gramatica (`transformer.py:179,215,234,265,281,304,317,361,419,445,454,466`);
  los pares clave-valor libres del autor (`integration`, `with`, `payload`) van a un `dict`,
  no a atributos (`transformer.py:253-257,413-414,423-430`).
- **Nombres duplicados se detectan** en vez de pisarse en silencio (`transformer.py:488-490`) y
  son error de validacion (`validator.py:49-54`).
- **El parser-service no ejecuta ni persiste**: parsea, valida, serializa y responde
  (`parser_service/main.py:3,53-86`). Singleton por proceso sin estado compartido
  (`parser.py:161-168`), compatible con las 2 replicas del chart (`values.yaml:80-83`).
- **LALR**: `Lark(..., parser="lalr")` (`parser.py:57-63`); determinístico y sin backtracking
  (ADR-001 descarta PEG por "backtracking sin limite",
  `wiki/Knowledge/decisions/2026-06-30-adr-001-lark-lalr.md:37`). `(inferencia)` el costo de
  parseo es lineal en el tamaño de la fuente.
- **Errores de sintaxis estructurados**: linea y columna viajan como dato
  (`parser_service/main.py:40-41,63-64`), sin traceback en la respuesta.
- **Gateway**: `/parse` exige `flows:read` (`gateway/main.py:655-656`) y el deploy
  `flows:deploy` (`teleflow/gateway/main.py:604-605`), ambos detras del middleware de auth + rate limit
  (`teleflow/gateway/main.py:145-163`). El proxy arma los headers desde cero, no copia los del cliente
  (`teleflow/gateway/main.py:409-418`). Timeout del cliente hacia upstream: 60 s (`teleflow/gateway/main.py:51`).
- **El deploy bloquea un flow invalido** (422 con los issues) antes de llegar al registry
  (`gateway/main.py:625-629`).
- **Auditoria del deploy sin guardar codigo**: se registran version y checksum SHA-256 de la
  fuente (`gateway/main.py:609-612,624`; `parser.py:171-172`); `flows:deploy` es scope de
  escritura y se audita siempre (`gateway/auth.py:155-158,170`).
- **Credenciales de integraciones fuera del DSL en los ejemplos**: en `examples/ceibal.tflow`
  todo campo sensible se referencia por `${env.*}` — `base_url`, `auth_header`, `host`,
  `username`, `password` (`examples/ceibal.tflow:377-391`). `examples/venta_internet_hogar.tflow`
  no declara integraciones (busqueda: `integration|base_url|url|password|token`, sin
  coincidencias). No se encontraron literales de credenciales en `examples/` (busqueda:
  `(password|token|secret|api_key|auth_header)\s*:\s*"[^$]`).
- **Variable faltante falla fuerte** en vez de mandar un header vacio
  (frontera: `executor_service/adapters.py:48-84`).
- **Log del parseo exitoso sin fuente**: `parse_ok` registra nombre del flow, validez y conteos
  por categoria, no el codigo (`parser_service/main.py:78-79`). Logs JSON con structlog
  (`teleflow/common/logging.py:22`).

## Huecos

| Hueco | Severidad | Evidencia |
|---|---|---|
| **`${env.*}` resuelve cualquier variable del proceso executor, sin lista blanca, y la manda a un host que elige el autor del flow.** Un `.tflow` desplegado puede declarar `auth_header: "${env.TELEFLOW_API_KEY}"` o `"${env.DATABASE_URL}"` con un `base_url` propio: el executor la resuelve y la envia como header HTTP. La key de bootstrap tiene scopes `*` por default, asi que `flows:deploy` escala a todos los scopes (incluido `keys:admin`) y filtra las credenciales de Postgres/RabbitMQ. Direccion: restringir `${env.*}` a un prefijo dedicado (p.ej. `TFLOW_INTEG_*`) y validarlo en el `validator`. | alta | Regex sin restriccion de nombre `executor_service/adapters.py:31`; `os.environ.get(nombre)` `adapters.py:72`; `base_url`, `Authorization` y header arbitrario resueltos `adapters.py:121-131`; request a ese host `adapters.py:135-139`; `api_key_header` con nombre de header libre `adapters.py:128-131`; misma env para todos los servicios `docker-compose.yml:3-8,103-107`, `helm/teleflow/templates/_helpers.tpl:243-277`; default `teleflow_api_key_scopes = "*"` `teleflow/common/config.py:23`; `flows:deploy` descrito como "ejecutar codigo nuevo" `gateway/auth.py:30`. El `validator` no inspecciona `IntegrationDef.config` (`validator.py:128-136` solo mira si la integracion existe). |
| Sin limite de tamaño de fuente en ninguna capa. `source: str` sin `max_length` en el parser y en el deploy; el gateway lee el body entero. Alcanzable con `flows:read`, el scope de menor privilegio. | media | `parser_service/main.py:22-24`; `gateway/main.py:598-601`; `gateway/main.py:416`; limite de memoria 512Mi por pod `deployments.yaml:66-67`. Mitigacion parcial: 120 rpm por key `docker-compose.yml:26`. |
| El parseo (CPU) corre dentro de un handler `async def`: una fuente grande bloquea el event loop de la replica, incluidos `/health` y `/ready`. Direccion: `run_in_threadpool` + tope de tamaño. | media | `parser_service/main.py:53,57`; probes `deployments.yaml:50-61`. `(inferencia)` liveness fallida → reinicio del pod durante un parseo largo. |
| Sin limite de profundidad: el `Transformer` de Lark es recursivo y el del repo hereda de `Transformer`, no de `Transformer_NonRecursive`. Una expresion anidada (`NOT NOT NOT ...` o parentesis con operadores) puede agotar la pila; el servicio solo captura `TeleFlowSyntaxError`, asi que termina en 500. El evaluador, el serializador y `_refs_de` tambien recursan. | media | `transformer.py:47`; `.venv/Lib/site-packages/lark/visitors.py:143-157` (recursion) y `:127-128` (envuelve en `VisitError`); gramatica recursiva `teleflow.lark:183,192`; catch unico `parser_service/main.py:56-58`; `evaluator.py:78-105`; `serialize.py:8-20`; `validator.py:174-196`. `(inferencia)` no se ejecuto una fuente de prueba. |
| parser-service sin auth propia y alcanzable directo desde la red interna: saltea rate limit y auditoria del gateway. No hay NetworkPolicy en el chart. | media | Sin dependencia de auth en `parser_service/main.py:52`; `ClusterIP` `deployments.yaml:77-81`; NetworkPolicies no reescritas, anotado `helm/teleflow/templates/datos.yaml:14-15`; busqueda `NetworkPolicy` en `helm/`: solo ese comentario. Compose sin `ports:` `docker-compose.yml:83-91` `(inferencia: red default de compose, visible para todo contenedor del stack)`. Mismo patron fuera de alcance: registry acepta `ast` sin re-parsear `registry_service/main.py:41,93`. |
| El token inesperado entra **completo** al mensaje de error, que se devuelve y se loguea. Un `STRING` o `NAME` de megabytes en posicion invalida produce una linea de log de ese tamaño (amplificacion de logs con `flows:read`). | media | `parser.py:133-136` (`'{tok}'` sin truncar); log `parser_service/main.py:59`; respuesta `teleflow/parser_service/main.py:63-64`. |
| Contenedor como root y sin `securityContext`; el parser-service recibe todas las credenciales (`DATABASE_URL`, `RABBITMQ_URL`, `TELEFLOW_API_KEY`, `LLM_API_KEY`) aunque no usa ninguna: un compromiso del parser las expone todas. | media | `Dockerfile:3-16` sin `USER`; `deployments.yaml:36-67` sin `securityContext` (busqueda `securityContext|runAsNonRoot` en `helm/`: sin coincidencias); env compartida `_helpers.tpl:243-277`, `docker-compose.yml:86-88`. |
| El mensaje de sintaxis incluye ~40 caracteres de la fuente antes y despues del error y se loguea: si la fuente trae un literal sensible cerca del error, queda en logs. El validador devuelve el invariante entero en el mensaje (no se loguea). | baja | `parser.py:119-122,154-155`; `.venv/Lib/site-packages/lark/exceptions.py:55-69` (`span=40`); log `parser_service/main.py:59`; `validator.py:367`. |
| `resolve_ref` recorre atributos arbitrarios de objetos no-`Mapping`, incluidos nombres con `_` (dunder); el valor no se invoca pero se stringifica en templates y payloads que salen a integraciones. | baja | `evaluator.py:65-66`; `NAME` admite `_` inicial `teleflow.lark:206`; `executor_service/adapters.py:92-93,99`. `(inferencia)` fuga limitada a `repr` de objetos internos, segun que objetos lleguen al contexto. |
| El parametro `funcs` de `evaluate` amplia la lista blanca; hoy ningun llamador lo usa, pero la puerta queda abierta sin control. | baja | `evaluator.py:74-76`; llamadas sin `funcs`: `adapters.py:99,200`, `engine.py:586,607`, `rules.py:139,146,247,258`, `view360.py:195`, `entities.py:283`. |
| Numeros sin tope: un `NUMBER` de mas de 4300 digitos hace fallar `int()` dentro del transformer → `VisitError` no capturado → 500. Tambien `retries`, `limit` del timeline y `timeout` llegan sin cota al runtime (el validador no los acota). | baja | `teleflow.lark:207`; `transformer.py:55-57,293-294,389-390`; imagen `python:3.12` `Dockerfile:3`; consumo `engine.py:597-600`, `view360.py:150,160`. `(inferencia)` limite `int_max_str_digits` de CPython >= 3.11. |
| `/docs` y `/openapi.json` del parser-service habilitados. | baja | `parser_service/main.py:18` `(inferencia: defaults de FastAPI)`. |
| Imagen referenciada por tag, no por digest. | baja | `values.yaml:2-4`; `deployments.yaml:41`. |

## Datos personales

- **El DSL declara el esquema de datos personales, no los valores.** Ejemplo:
  `entity "nino"` con `ci`, `nombre`, `fecha_nac`, `tutor_email` (`examples/ceibal.tflow:10-18`).
  Los valores viven en las entidades en runtime (executor), fuera de este alcance.
- **Literales en la fuente**: `default(...)`, `template`, `description` y valores de
  `integration` son texto libre (`teleflow.lark:40,145,156`). Nada impide que un autor escriba
  un dato personal ahi; no hay chequeo (busqueda en `validator.py`: no inspecciona literales).
  El unico correo en los ejemplos es institucional (`examples/ceibal.tflow:388`).
- **Donde se persiste**: `/parse` no persiste nada (`parser_service/main.py:53-86`). El deploy
  manda la fuente completa al registry (`gateway/main.py:632-641`) — tabla `flow_definitions`
  (frontera: `engine.py:435-442` la lee de ahi).
- **A donde viaja**: a logs del parser solo en error de sintaxis, como fragmento (hueco baja) y
  como token completo (hueco media). No viaja a RabbitMQ ni a un LLM desde este modulo; la
  fuente generada por LLM entra por el composer (`composer_service/main.py:118-122`), fuera de
  alcance.
- **`audit_log`**: el deploy guarda version y checksum, no la fuente
  (`gateway/main.py:609-612,624`). `/parse` no se audita: `flows:read` es scope de lectura
  (`gateway/auth.py:163-170`) — decision, no omision.

## Secretos y configuracion

- **Credenciales de integraciones**: por contrato van en el entorno y se referencian con
  `${env.NOMBRE}` (`examples/ceibal.tflow:379-380,386,389-390`); se resuelven en el executor en
  el momento de la llamada, no en el parser (`executor_service/adapters.py:48-84`). El parser
  y el AST guardan el placeholder literal, nunca el valor (`transformer.py:423-430`). Hueco
  alta: el nombre de variable no esta acotado (ver tabla).
- **El parser-service no lee ninguna variable propia**: solo `setup_logging` y
  `setup_observability` (`parser_service/main.py:16-19`). Recibe igual el entorno compartido.
- **Defaults inseguros heredados** (no del modulo, pero presentes en el pod del parser):
  `TELEFLOW_API_KEY` `[REDACTED]` con default de desarrollo en `teleflow/common/config.py:18` y
  `docker-compose.yml:7`; scopes `*` por default (`config.py:23`, `docker-compose.yml:8`);
  contraseñas de Postgres/RabbitMQ con default `[REDACTED]` en `docker-compose.yml:4,6`.
- **Chart**: `DATABASE_URL` y `RABBITMQ_URL` llegan por `secretKeyRef`; `TELEFLOW_API_KEY` y
  `LLM_API_KEY` tambien (`_helpers.tpl:264-277`). `REDIS_URL` va como valor a proposito
  (`_helpers.tpl:260-262`). El chart falla si no se define `apiKey` ni `existingSecret`
  (`values.yaml:10-16`).
- **Errores**: el mensaje de sintaxis no incluye variables de entorno; si incluye fragmentos de
  la fuente (ver huecos). No se encontro logueo de secretos en `teleflow/dsl/` ni en
  `parser_service/main.py` (busqueda: llamadas a `log.` en ambos; solo `teleflow/parser_service/main.py:59,78`).

## Impacto en despliegue

- **As-built, sin cambios**: el modulo no tiene migraciones Alembic propias ni estado; el
  parser-service es stateless y ya corre con 2 replicas (`values.yaml:80-83`) sin asumir
  proceso unico.
- **Compose**: `parser-service` sin puertos publicados (`docker-compose.yml:83-91`); el gateway
  depende de el (`docker-compose.yml:150-151`).
- **Helm**: Deployment + Service `ClusterIP` genericos (`deployments.yaml:1-89`), limites
  `256Mi`/`512Mi` y sin limite de CPU (`deployments.yaml:62-67`). Faltan NetworkPolicy, PDB y
  `securityContext` (ver huecos).
- **TLS interno**: gateway → parser en claro, limite consciente documentado (`README.md:362-365`);
  la fuente del flow viaja sin cifrar dentro del cluster.
- **Instalable por organismo sin overrides**: si (`spec/constitution/mission.md:23-26`). Ningun
  hueco listado exige override para instalar; si exigen trabajo para endurecer.
