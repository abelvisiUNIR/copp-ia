---
project: copp-ia
type: plan
status: implementada
feature: base-lenguaje-tflow
provenance: copp-ia@devyos@5e64479
created: 2026-09-14
---

<!-- status: borrador | consolidada | implementada (linea base as-built) -->
<!-- Lo escribe el subagente `disenador-tecnico` (comando /disenar). En as-built, "Enfoque" y
     "Archivos que toca" describen como esta resuelto hoy, con cita. -->


# Plan de implementacion — Linea base del lenguaje `.tflow`

> As-built. Describe como esta resuelto hoy, no un cambio a hacer. Insumo: `spec.md` de esta
> carpeta; los huecos de seguridad estan en `seguridad.md` y aca solo se referencian. Todo lo
> que no lleva `(inferencia)` se comprobo leyendo el archivo citado en `copp-ia@devyos@5e64479`.

## Enfoque

Un pipeline de cuatro etapas puras en `teleflow/dsl/`, expuesto por un servicio HTTP sin estado:
**gramatica Lark LALR** (`teleflow.lark:1-7`, `parser.py:57-63`) → **transformer** a dataclasses
(`transformer.py:47`, `ast_nodes.py:297-314`) → **validador** que devuelve issues `error`/`warning`
sin lanzar (`validator.py:46-171`) → **serializacion** a JSON (`serialize.py:8-20`). El evaluador
de expresiones (`evaluator.py:74-107`) no participa del parseo: lo consume el executor en runtime.
`POST /parse` del parser-service encadena parseo, validacion y serializacion y nunca persiste ni
ejecuta (`parser_service/main.py:52-86`).

Consumidores (fuera de `teleflow/dsl/`, citados como frontera):

- **gateway** — proxy `POST /parse` con scope `flows:read` que arma los headers desde cero
  (`teleflow/gateway/main.py:655-659`, `teleflow/gateway/main.py:409-418`); y deploy `POST /flows/{name}`: parse →
  `422` si `valid` es `false` → register con `ast` y `checksum` → `201` con los warnings
  (`gateway/main.py:604-652`).
- **composer** — `_validate_source` manda cada borrador a `parser-service /parse` y guarda
  `{parses, issues}`; `parses: None` si el parser no respondio (`composer_service/main.py:108-134`).
- **executor** — **no** pasa por el parser-service: importa `teleflow.dsl` como libreria.
  `DomainLoader` re-parsea el `source` de cada `latest` registrado y combina con
  `FlowFile.merge` (`executor_service/domain.py:3-4`, `domain.py:77-81`, `domain.py:94-106`);
  una version explicita se re-parsea en `engine.py:440-442`. El evaluador corre en invariantes
  (`entities.py:266-293`), ramas y steps `decision` (`engine.py:586`, `engine.py:607`), rules
  (`rules.py:139,146,247,258`), vista 360 (`view360.py:195`) y payloads (`adapters.py:99,200`).
- **CLI** — `tflow validate` contra el `/parse` del gateway (`teleflow/cli.py:52-63`).

Enfoques descartados, con su ADR:

- PLY, Parsimonious (PEG), Tree-sitter y parser combinador manual, frente a Lark LALR —
  `wiki/Knowledge/decisions/2026-06-30-adr-001-lark-lalr.md:36-38`.
- Validar el borrador importando el parser como libreria en el composer —
  `2026-07-25-composer-llm-fallos-explicitos.md:125-127`. Ver en Riesgos la tension con el
  executor, que si lo importa.
- Validar la edicion del borrador en el navegador (segunda implementacion de la gramatica) —
  `2026-08-27-correccion-del-borrador-en-la-revision.md:108-110`, `:153-155`.
- Chequeo `_check_derrame_entre_ramas` en el validador: se retiro al cambiar la semantica de
  ramas en el executor; el marcador de version del lenguaje (opcion E) quedo como deuda —
  `2026-08-27-caida-secuencial-entre-etapas.md:125-129`, `:145-146`.

Contradicciones con ADRs vigentes: ninguna de decision. Hay dos afirmaciones de ADR
desactualizadas que `spec.md:441-451` ya documenta (conteo de errores de `mypy` en ADR-001:32-33
y `examples/reclamo_corte.tflow` citado por el ADR de caida secuencial); corresponde enmendar
esos ADRs, no el codigo.

## Archivos que toca

Archivos que componen el modulo y su rol.

| Archivo | Rol |
|---|---|
| `teleflow/dsl/teleflow.lark` | Gramatica EBNF, fuente de verdad del lenguaje (ADR-001): nueve bloques de primer nivel (`:7-17`), sublenguaje de expresiones (`:176-195`), terminales `NAME`/`NUMBER`/`STRING` (`:206-208`) y comentarios (`:210-213`) |
| `teleflow/dsl/parser.py` | Fachada: `TeleFlowParser` con dos entradas, `start` y `expr` (`:57-81`); traduce excepciones de Lark a `TeleFlowSyntaxError` en castellano con linea, columna, terminales esperados y fragmento (`:22-35`, `:114-158`); singleton por proceso `get_parser` (`:161-168`); `checksum` SHA-256 (`:171-172`) |
| `teleflow/dsl/transformer.py` | `TeleFlowTransformer`: arbol Lark → dataclasses (`:47-467`); `start` agrupa por categoria y registra duplicados en vez de pisarlos (`:470-492`). Sin atributos de instancia (ninguna asignacion `self.x =` en el archivo) |
| `teleflow/dsl/ast_nodes.py` | Dataclasses del AST; `Ref.dotted/kind/target` (`:21-37`); `FlowFile` con `duplicates` marcado `transient` (`:297-314`); `FlowFile.merge`, ultimo gana por nombre (`:316-329`) |
| `teleflow/dsl/validator.py` | `validate_flow` (`:46-171`); chequeo de firmas decision↔human_task (`:199-247`); universo de eventos incluidos los sinteticos (`:250-271`); referencias de triggers (`:274-316`); lifecycle, eventos, invariantes y relaciones (`:319-395`). `FlowValidationError` definida (`:40-43`) y nunca lanzada (`spec.md:426-428`) |
| `teleflow/dsl/evaluator.py` | `evaluate` null-safe (`:74-107`), `resolve_ref` con nombre suelto como literal (`:58-71`), lista blanca `BUILTIN_FUNCS` (`:50-55`), `_compare` (`:110-130`) |
| `teleflow/dsl/serialize.py` | `to_jsonable`: dataclass → dict con `_node`, omite campos `transient` (`:8-20`) |
| `teleflow/dsl/__init__.py` | Superficie publica: parser, error de sintaxis, validador (`:1-10`). `evaluate`, `get_parser`, `to_jsonable` se importan por su modulo, no desde el paquete |
| `teleflow/parser_service/main.py` | `POST /parse`: `ParseRequest`/`IssueOut`/`ParseResponse` (`:22-49`); error de sintaxis → `valid: false` con posicion (`:56-65`); validacion, `summary` de siete categorias y AST serializado (`:67-86`) |
| `examples/ceibal.tflow` | Flow de referencia: entities, relation, rules con timer, view360, cinco procesos, integration con `${env.*}`, catalog y party (`tests/test_parser.py:9-18`) |
| `examples/venta_internet_hogar.tflow` | Flow de referencia con stage `decision` y `human_task` de dos senales (`tests/test_parser.py:88-106`) |

## Reutiliza

Lo que una feature que toque el lenguaje ya tiene resuelto y no deberia reescribir:

- `get_parser()` — singleton por proceso, sin estado mutable (`teleflow/dsl/parser.py:164-168`).
  No construir otro `TeleFlowParser` salvo inyeccion explicita, como hace `DomainLoader`
  (`executor_service/main.py:46`).
- `TeleFlowSyntaxError.expected` — terminales aceptados como dato, para tooling
  (`teleflow/dsl/parser.py:34-35`).
- `_refs_de` — recorre cualquier expresion y devuelve todas sus `Ref`
  (`teleflow/dsl/validator.py:174-196`). Base natural para validar referencias o funciones
  dentro de expresiones.
- `_emitted_events` — universo de eventos del archivo, sinteticos incluidos
  (`teleflow/dsl/validator.py:250-271`).
- `Ref.kind` / `Ref.target` / `Ref.dotted` (`teleflow/dsl/ast_nodes.py:27-37`).
- Metadata `transient` para excluir un campo del JSON (`ast_nodes.py:312-314`,
  `serialize.py:12-13`).
- `_validate_source` del composer, con el estado `parses: None` para "no se pudo verificar"
  (`teleflow/composer_service/main.py:108-129`).
- `_post_upstream` / `_proxy` del gateway (`teleflow/gateway/main.py:399-429`); el deploy
  convierte `UpstreamDown` en `502` (`gateway/main.py:616-617`).
- Metricas de degradacion del dominio: `teleflow_domain_parse_failures_total`,
  `teleflow_domain_broken_flows` (`executor_service/domain.py:26-34`) y
  `teleflow_invariants_skipped_total` (`executor_service/entities.py:34`).
- Fixtures de test `parser`, `ceibal_source`, `venta_source` (`tests/conftest.py:13-15`,
  `:114-121`) y el patron `TestClient(app)` contra el parser-service
  (`tests/test_parser.py:223-238`).

## Migraciones

Alembic: **no**. El DSL y el parser-service no leen ni escriben base de datos
(`parser_service/main.py:52-86` no importa sesion ni modelos).

Tablas que dependen del resultado del modulo, via sus consumidores:

| Tabla.columna | Creada en | Quien la escribe / lee |
|---|---|---|
| `flow_definitions.source`, `.ast`, `.checksum` | `alembic/versions/0001_initial.py:18-29` (ORM `common/models.py:28-37`) | Escribe el registry con lo que devuelve `/parse` (`gateway/main.py:632-641`); el executor lee **solo** `source` y lo re-parsea (`executor_service/domain.py:77`, `engine.py:442`); `ast` solo se devuelve por API (`registry_service/main.py:181`; busqueda de `.ast` y `["ast"]` en `teleflow/`: ademas solo `registry_service/main.py:93` y `gateway/main.py:638`, que lo escriben) |
| `flow_latest` | `0001_initial.py:31-36` | Define que version re-parsea `DomainLoader` (`domain.py:67-74`) |
| `flow_drafts.validation` | `alembic/versions/0003_draft_validation.py:24-27` | Composer, con el resultado de `/parse` (`composer_service/main.py:95-99`) |

Compatibilidad hacia atras: no aplica a migraciones, pero si a la **gramatica**: un cambio que
deje de aceptar un `source` ya registrado lo saca del dominio del executor (`spec.md:401-405`).

## Tests

Existentes, por archivo. Sin tests para el parser-service mas alla de los dos de `test_parser.py`.

- Unitarios:
  - `tests/test_parser.py` — 20 funciones (una parametrizada con 10 casos): bloques y detalle de
    ceibal y venta, unidades de tiempo, mensajes de error (caracter, token, EOF, expresion,
    fragmento con `^`), identificador con tilde, serializacion, y dos contra el parser-service
    (`test_el_servicio_publica_la_posicion_del_error`,
    `test_los_issues_del_validador_no_inventan_posicion`).
  - `tests/test_validator.py` — 24 funciones: lifecycle, triggers, steps inexistentes,
    `human_task` en `parallel`, `stage.end`, duplicados, warnings de referencias colgadas,
    firmas decision↔human_task y `test_los_ejemplos_del_repositorio_quedan_limpios` (`:305`).
  - `tests/test_evaluator.py` — 7 funciones: comparaciones, null, `WHEN`, `in`, refs con puntos,
    `days_since`, nombre suelto como literal.
  - `tests/test_dag.py` — 10 funciones `(indirecto)`: el DAG del executor sobre ASTs parseados,
    incluida la regla de ramas del ADR de caida secuencial.
  - `tests/test_error_handling.py` — `(indirecto)` invariantes en el executor:
    `test_invariante_con_typo_queda_expuesto` (`:126`), `test_invariante_valido_sigue_bloqueando`
    (`:138`), `test_invariante_no_evaluable_no_bloquea` (`:145`).
  - `tests/test_composer.py` — `(indirecto)` con el parser mockeado:
    `test_borrador_que_compila_queda_marcado_ok` (`:298`),
    `test_borrador_que_no_compila_se_marca_pero_no_levanta` (`:307`),
    `test_parser_caido_no_se_confunde_con_compila` (`:317`),
    `test_editar_revalida_contra_el_parser` (`:467`).
  - `tests/test_gateway_scopes.py` — `(indirecto)` `test_key_de_solo_lectura_no_puede_desplegar`
    (`:50`), `test_deploy_con_el_parser_caido_da_502_no_500` (`:113`).
- e2e (`-m e2e`):
  - `tests/e2e/conftest.py:38-63` — fixture `deployed`: despliega los dos ejemplos por el gateway
    y exige `201`, salvo que ya existan (`:51-52`). No hay un test e2e dedicado a `/parse`.

La lista de criterios `(sin test)` esta en `spec.md:130-394`; no se repite aca.

## Riesgos

Limites conscientes y huecos observados. Los que ya documentaron `spec.md` ("No entra",
`:71-128`) y `seguridad.md` ("Huecos", `:85-101`) se **referencian**; el detalle esta alla.

| Riesgo | Mitigacion |
|---|---|
| **Huecos de validacion ya documentados** en `spec.md` "No entra": `catalog`/`party` sin validar (`:73-80`), referencias dentro de expresiones y nombre suelto como literal (`:98-104`), prefijo `kind` ignorado en refs (`:105-108`), duplicados entre archivos (`:109-112`), coherencia de campos (`:113-117`). | Hoy ninguna. Son decisiones de lenguaje: ver candidatos a ADR. |
| **Huecos de seguridad ya documentados** en `seguridad.md`: `${env.*}` sin lista blanca, severidad alta (`:89`); sin limite de tamaño (`:90`, tambien `spec.md:86-91`); parseo CPU en handler `async` (`:91`); sin limite de profundidad → 500 (`:92`); parser-service sin auth en red interna (`:93`); token completo en el mensaje y log (`:94`); numeros sin tope (`:99`); resto de severidad baja (`:95-101`). | Parcial: rate limit por key y scope en el gateway (`seguridad.md:64-67`). La direccion propuesta esta en cada fila de `seguridad.md`. |
| **Sin marcador de version del lenguaje** (`spec.md:118-120`): un cambio de gramatica o de semantica reinterpreta en silencio los flows registrados. | Ninguna tecnica. Hoy no hay instalacion productiva (`2026-08-27-caida-secuencial-entre-etapas.md:84-88`); la ventana se cierra con el primer organismo. |
| **El AST persistido y el que ejecuta pueden divergir.** El registry guarda `ast` sin re-parsear (`seguridad.md:93`), pero el executor ignora esa columna y re-parsea `source` con la gramatica de su propia imagen (`domain.py:77`, `domain.py:98`; `spec.md:121-122`). Tras un cambio de gramatica, `flow_definitions.ast` describe algo que ya no es lo que corre. `(inferencia)` sobre la divergencia; los hechos estan comprobados. | Ninguna. Relacionado con el marcador de version. |
| **¿Asume un solo proceso?** Parser-service: no. `get_parser` es un singleton por proceso (`parser.py:161-168`) y el transformer no guarda estado de instancia, asi que las 2 replicas del chart (`helm/teleflow/values.yaml:80-82`) son equivalentes. Executor: cada replica tiene su propio cache de dominio con TTL de 30 s (`domain.py:48-59`), asi que tras un deploy las replicas pueden ver dominios distintos hasta que venza (`(inferencia)`; el e2e espera 32 s por eso, `tests/e2e/conftest.py:62-63`). | Consciente: TTL corto documentado en `domain.py:4-5`. No hay invalidacion activa entre replicas. |
| **Desfase de gramatica durante un upgrade rolling.** Los servicios comparten imagen (`spec/constitution/tech_stack.md:50-51`), pero durante un `helm upgrade` conviven pods viejos y nuevos: un flow que valida el parser-service nuevo (p.ej. una forma recien aceptada, como las unidades en singular de `teleflow.lark:83-91`) puede no parsear en una replica vieja del executor, que lo saca de su dominio (`domain.py:97-102`). Contradice en la practica el motivo del ADR del composer — "duplicaria la version de la gramatica efectiva en dos procesos" (`2026-07-25-composer-llm-fallos-explicitos.md:125-127`) — porque el executor ya la duplica. `(inferencia)`: no se reprodujo un upgrade. | Parcial: la falla es visible como metrica (`domain.py:26-34`) y se corrige sola al rotar los pods. Ver fila siguiente. |
| **Fallas silenciosas: senales sin alerta.** Un flow registrado que deja de parsear o un invariante que no parsea se cuentan en `teleflow_domain_parse_failures_total`, `teleflow_domain_broken_flows` (`domain.py:26-34`) y `teleflow_invariants_skipped_total` (`entities.py:34`, `:280`, `:289`), pero ninguna regla de alerta las usa (busqueda de los tres nombres en `helm/` y en todo el repo: solo aparecen en el codigo del executor, en `spec.md` y en la wiki). Es "un aviso que no corta" (`wiki/Knowledge/concepts/fallas-silenciosas.md:56-57`). | Parcial: metrica + `log.error` (`domain.py:87-88`, `:100`; `entities.py:278`). Falta la alerta. |
| **Fallas silenciosas: el e2e no re-verifica los ejemplos.** El fixture `deployed` saltea el deploy si el flow ya existe (`tests/e2e/conftest.py:51-52`), asi que contra un stack reutilizado un cambio de gramatica que rompa un ejemplo no se ve en e2e. | Si: `tests/test_validator.py:305` parsea y valida los dos ejemplos en el gate rapido. |
| **`in` depende del tipo del operando derecho.** `_compare` evalua `left in right` fuera del `try` (`evaluator.py:115-116`; el `try` empieza en `:119`): contra un numero lanza `TypeError`, y contra un string hace busqueda de subcadena (`estado in "ACTIVA"` es `True` con `estado = "ACT"`). Comprobado leyendo el codigo y la semantica de Python; no ejecutado. En un invariante, ese `TypeError` cae en `not_evaluable`, que no bloquea y se loguea en `debug` (`entities.py:284-290`). El test de esa rama la fabrica con monkeypatch porque asume que el evaluador no lanza (`tests/test_error_handling.py:149-155`). | Ninguna. El validador no mira tipos de operandos. |
| **Funciones desconocidas recien fallan en runtime.** El validador recorre `Func` solo para buscar refs (`validator.py:191-193`) y no contrasta el nombre con `BUILTIN_FUNCS` (`evaluator.py:50-55`), asi que `dias_desde(x) > 3` pasa `/parse` y levanta `EvaluationError` al evaluarse (`evaluator.py:86-88`). Amplia el hueco de `spec.md:98-104`. | Ninguna en validacion. Lista blanca efectiva en runtime (`seguridad.md:39-46`). |
| **Duraciones y enteros negativos.** `NUMBER` acepta signo (`teleflow.lark:207`) y `duration` multiplica sin cota (`transformer.py:131-132`): `after: -30 days`, `timeout: -1 day`, `retries: -1` o `limit: -5` parsean y validan. Solo `retries` se acota en el consumidor (`engine.py:597`). Complementa `seguridad.md:99`. Efecto en timers y timeouts: `(inferencia)`, no verificado. | Parcial para `retries` (`max(0, ...)`). |
| **Superficie publica muerta.** `FlowValidationError` se exporta (`teleflow/dsl/__init__.py:2`) y nadie la lanza (`spec.md:426-428`). | Ninguna; bajo impacto. |

**Candidatos a ADR** (una linea cada uno; no se escriben aca):

- **Identificadores del `.tflow` solo ASCII** — hoy lo fijan la gramatica (`teleflow.lark:206`), un test (`tests/test_parser.py:265-269`) y el prompt del composer (`composer_service/providers.py:30`), sin ADR.
- **Contrato de `${env.*}` en integraciones: prefijo dedicado y chequeo en el validador** — hoy el contrato vive solo en el executor (`executor_service/adapters.py:31`, `:72`) y el validador no lo conoce (`seguridad.md:89`).
- **Marcador de version del lenguaje en el `.tflow` y en el registro** — opcion E, anotada como deuda en `2026-08-27-caida-secuencial-entre-etapas.md:145-146`, `:173-177`.
- **Limites de entrada del parser (tamaño de fuente, profundidad de anidamiento) y en que capa se cortan** — `seguridad.md:90`, `:92`.
- **Nombre suelto como literal frente a validar referencias en expresiones** — `evaluator.py:68-69`, `spec.md:98-104`.
- **Politica de nombres repetidos entre archivos del dominio (`merge` ultimo gana)** — `ast_nodes.py:316-329`, `spec.md:109-112`.
- **Donde se parsea en runtime: executor como libreria o via parser-service, y convivencia de versiones durante un upgrade** — tension entre `executor_service/domain.py:19` y `2026-07-25-composer-llm-fallos-explicitos.md:125-127`.
- **Destino de `catalog` y `party`: validarlos, darles consumidor o retirarlos del lenguaje** — `spec.md:73-80`.

## Verificacion

Que la linea base sigue describiendo el codigo. Desde la raiz del repo, con el venv activo.

```
mypy .
pytest -m "not e2e" -q
pytest tests/test_parser.py tests/test_validator.py tests/test_evaluator.py tests/test_dag.py tests/test_error_handling.py -q
```

Contra el stack (compose levantado, key de desarrollo o `TELEFLOW_API_KEY` definida):

```
docker compose up --build -d
pytest -m e2e -q
tflow validate examples/ceibal.tflow
tflow validate examples/venta_internet_hogar.tflow
```

`tflow validate` sale con codigo 1 si el flow no es valido (`teleflow/cli.py:62-63`). Como el
fixture e2e no redespliega ejemplos existentes (`tests/e2e/conftest.py:51-52`), para que el e2e
verifique la gramatica actual hay que partir de un stack sin esos flows registrados.
