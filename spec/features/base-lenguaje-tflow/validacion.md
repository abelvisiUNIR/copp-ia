---
project: copp-ia
type: validacion
status: implementada
feature: base-lenguaje-tflow
provenance: copp-ia@devyos@5e64479
validated: 2026-09-14
---

# Validacion contra la spec — Linea base del lenguaje `.tflow`

<!--
  status: borrador | implementada (linea base as-built)
  Lo escribe el subagente `validador-spec`. No escribe tests: un criterio sin test vuelve al
  implementador. Un criterio NO CUMPLE nunca se "arregla" editando la spec para que calce.
-->

Modo **as-built**: el objetivo es medir cobertura, no aprobar. Provenance obtenida con
`git rev-parse --abbrev-ref HEAD` (`devyos`) y `git rev-parse --short HEAD` (`5e64479`). El working
tree tiene cambios sin commitear en `.claude/agents/`, `spec/features/_TEMPLATE/` y esta carpeta
(sin archivos de `teleflow/` ni `tests/` modificados, segun `git status --short`).

**Resumen: 77 criterios — 51 CUMPLE, 0 NO CUMPLE, 26 SIN TEST.**

## Gates ejecutados

| Comando | Resultado | Fecha | Commit |
|---|---|---|---|
| `mypy .` | **1 error**, 82 archivos: `tests/test_doc_contract.py:26: error: Library stubs not installed for "yaml" [import-untyped]`. `types-PyYAML` esta declarado en `pyproject.toml` pero no instalado en `.venv` (sin salida a PyPI desde este entorno). No es un error de tipos del codigo. | 2026-09-14 | `5e64479` |
| `mypy teleflow/dsl teleflow/parser_service` (modulo) | `Success: no issues found in 9 source files` | 2026-09-14 | `5e64479` |
| `pytest -m "not e2e" -q` | **no ejecutado por el validador en esta pasada**: la suite completa tarda ~23 min con el repo en Google Drive. Resultado de la corrida completa del 2026-09-14 **reportado por quien invoco al validador, no re-verificado aca**: 291 passed, 10 errors, todos en `tests/test_lease_de_instancia.py` por `aiosqlite` no instalado en `.venv`. | 2026-09-14 | `5e64479` |
| `pytest -p no:cacheprovider -v tests/test_parser.py tests/test_validator.py tests/test_evaluator.py tests/test_dag.py tests/test_error_handling.py::test_invariante_con_typo_queda_expuesto` (tests del modulo) | **71 passed**, 1 warning (`StarletteDeprecationWarning` de `.venv/Lib/site-packages/fastapi/testclient.py:1`, ajeno al modulo), 39.38 s. Cada test citado en la matriz aparece en la salida como `PASSED`, asi que existe y pasa. | 2026-09-14 | `5e64479` |
| `pytest -m e2e -q` | **no ejecutado** — stack no levantado: `curl -sf http://localhost:8000/health` salio con codigo 7 (conexion rechazada). | 2026-09-14 | `5e64479` |

Todos los tests se corrieron con el venv del repo (`.venv/Scripts/pytest.exe`, Python 3.14.3).

## Matriz criterio → evidencia

Criterios copiados literales de `spec.md` y agrupados como alli. La cita final de cada criterio en
la spec (`— tests/...`, `(sin test)`, `(indirecto)`) se movio a la columna de tests; lo demas es
texto literal. Los `|` dentro de codigo se escriben `\|` para no romper la tabla.

Regla aplicada a criterios compuestos: si una parte tiene test y otra no, el resultado es
**SIN TEST** y se detalla que parte quedo cubierta. No hay un cuarto valor en la definicion del
validador para "parcial".

### Gramatica y parseo

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 1 | Dado `examples/ceibal.tflow`, cuando se parsea, entonces `entity "nino"` tiene `lifecycle.initial == "REGISTRADO"`, exactamente los estados `REGISTRADO, ACTIVO, INSCRIPTO, GRADUADO, INACTIVO`, transiciones con `via` que incluyen `activar`, `inscribir` y `graduar`, 2 invariantes y un evento que emite `nino.inscripto` | `tests/test_parser.py::test_entity_nino_lifecycle` (asserts `test_parser.py:24-31`: igualdad de conjunto de estados, subconjunto de `via`, `len == 2`, `in emits`) | CUMPLE |
| 2 | Dado `examples/ceibal.tflow`, cuando se parsean los campos, entonces `ci` queda `required` y `unique`, `nivel` es `enum` con valores `["primaria", "secundaria", "utu"]`, `dispositivo` queda `optional`, y el campo `progreso` de `relation "inscripcion"` tiene `has_default`, `default == 0` y `range == (0.0, 100.0)` | `tests/test_parser.py::test_entity_fields` (`test_parser.py:37-45`) | CUMPLE |
| 3 | Dado `relation "inscripcion"` de ceibal, cuando se parsea, entonces `from_ref.dotted == "entity.nino"`, `to_ref.dotted == "entity.curso"` y `cardinality == "many_to_many"` | `tests/test_parser.py::test_relation_refs` (`test_parser.py:51-53`) | CUMPLE |
| 4 | Dada la rule `detectar_abandono` de ceibal con `on_timer { after: 30 days ... }`, cuando se parsea, entonces `timer.after_seconds == 2592000`, `timer.since == "inscripcion.activada"`, `execute.dotted == "process.reenganche_estudiante"` y `with` tiene exactamente las claves `nino_id` y `curso_id` | `tests/test_parser.py::test_timer_rule` (`test_parser.py:59-63`; `30 * 86400`, igualdad de conjunto de claves) | CUMPLE |
| 5 | Dado `view360 "nino"` de ceibal, cuando se parsea, entonces `entity.dotted == "entity.nino"`, tiene 2 relaciones (la primera con alias `inscripciones_activas`, `where` no nulo e `include == ["curso.nombre", "progreso", "ultimo_acceso"]`), `timeline.limit == 50`, 2 alerts y 4 procesos en `active_processes.include` | `tests/test_parser.py::test_view360` (`test_parser.py:69-78`) | CUMPLE |
| 6 | Dado `examples/venta_internet_hogar.tflow`, cuando se parsea, entonces el proceso tiene los stages `validacion, aprobacion, decidir, activacion, rechazo` en ese orden, `decidir` es `decision` con 2 branches (la primera apunta a `activacion`, la segunda es `else` con `condition is None`), `aprobacion_gerencia` es `human_task` con `signals == ["approve", "reject"]` y `timeout_seconds == 604800`, y `validate_flow` no da errores | `tests/test_parser.py::test_venta_decision_stages` (`test_parser.py:94-106`) | CUMPLE |
| 7 | Dado un step con `timeout: <n> <unidad>`, cuando la unidad es `second\|seconds`, `minute\|minutes`, `hour\|hours`, `day\|days` o `week\|weeks`, entonces parsea y `timeout_seconds` vale `n` por 1, 60, 3600, 86400 o 604800 respectivamente (10 casos parametrizados) | `tests/test_parser.py::test_las_unidades_de_tiempo_aceptan_singular_y_plural` (10 parametrizaciones `test_parser.py:163-169`, las 10 `PASSED`) | CUMPLE |
| 8 | Dado un identificador con tilde (`step.notificación`) en la linea 3, cuando se parsea, entonces se lanza `TeleFlowSyntaxError` con `line == 3` y el mensaje contiene `ó` | `tests/test_parser.py::test_un_identificador_con_tilde_no_parsea` (`test_parser.py:271-280`) | CUMPLE |
| 9 | Dado un archivo con dos bloques de la misma categoria y el mismo nombre, cuando se parsea, entonces no se lanza excepcion, queda uno solo en el diccionario y el par `(categoria, nombre)` se registra en `FlowFile.duplicates` (`transformer.py:488-491`) | `tests/test_validator.py::test_duplicate_entity_is_error`, `tests/test_validator.py::test_duplicate_step_is_error` (via validador; ver observacion) | CUMPLE |
| 10 | Dado un archivo con comentarios `// ...` y `# ...`, cuando se parsea, entonces los comentarios se ignoran (`teleflow.lark:210-213`) | `//`: `tests/test_parser.py::test_parse_ceibal_blocks` (parsea `examples/ceibal.tflow`, que usa `//` en `:1-5`). `#`: ninguno (Grep de `^\s*#` en `examples/` sin coincidencias; ninguna fuente `.tflow` embebida en `tests/` usa `#`) | SIN TEST (parcial: `//` cubierto) |
| 11 | Dada una fuente vacia, cuando se parsea, entonces devuelve un `FlowFile` con todas las categorias vacias (`teleflow.lark:7` es `block*`) y `validate_flow` devuelve `[]` | ninguno (Grep de `parse("")`/`parse('')` en `tests/` sin coincidencias; los unicos `source: ""` estan en `tests/test_auditoria.py:97`, que prueba un 403 del gateway) | SIN TEST |
| 12 | Dado un `product` con `price: 100` y `currency: "UYU"` dentro de un `catalog`, cuando se parsea, entonces `price == 100.0` (float) y `currency == "UYU"` (`transformer.py:436-440`) | ninguno (Grep de `price\|currency` en `tests/` sin coincidencias). `test_parse_ceibal_blocks` solo afirma que existen `cursos_ceibal` y `tutor` (`test_parser.py:17-18`) | SIN TEST |

### Errores de sintaxis

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 13 | Dada la fuente `entity "x" { lifecycle { ??? } }`, cuando se parsea, entonces se lanza `TeleFlowSyntaxError` con `line` y `column` no nulos y un mensaje que contiene `carácter inesperado '?'` | `tests/test_parser.py::test_syntax_error_reports_line` (`line`, `:112`), `tests/test_parser.py::test_unexpected_char_message` (mensaje y `column`, `:119-120`) | CUMPLE |
| 14 | Dada la fuente `rule "r" { on_state: }`, cuando se parsea, entonces el mensaje contiene `se esperaba` y `exc.expected` contiene el nombre de terminal `STRING` | `tests/test_parser.py::test_unexpected_token_lists_expected` (`test_parser.py:127-129`) | CUMPLE |
| 15 | Dada la fuente `entity "x" ` (sin abrir el bloque), cuando se parsea, entonces el mensaje contiene `fin de archivo inesperado` y `'{'` | `tests/test_parser.py::test_unexpected_eof_message` (`test_parser.py:136-137`) | CUMPLE |
| 16 | Dada la expresion `1 + `, cuando se llama a `parse_expr`, entonces se lanza `TeleFlowSyntaxError` con `line` y `column` no nulos y un mensaje que contiene `Expresión inválida` y `se esperaba` | `tests/test_parser.py::test_parse_expr_gives_context` (`test_parser.py:144-147`) | CUMPLE |
| 17 | Dada una fuente cuyo error esta en la linea 3, cuando se parsea, entonces `exc.line == 3` y `exc.column` no es nulo | `tests/test_parser.py::test_el_error_de_sintaxis_lleva_linea_y_columna` (`test_parser.py:206-207`) | CUMPLE |
| 18 | Dado un error de sintaxis en un archivo multilinea, cuando se lee `exc.message`, entonces tiene mas de una linea y alguna linea posterior a la primera contiene el apuntador `^` | `tests/test_parser.py::test_el_mensaje_incluye_el_fragmento_con_el_apuntador` (`test_parser.py:218-220`) | CUMPLE |
| 19 | Dado un error con mas de 8 terminales esperados, cuando se arma el mensaje, entonces se muestran 8 descripciones seguidas de `, …` (`parser.py:110-112`) | ninguno (Grep de `…` en `tests/` sin coincidencias) | SIN TEST |

### Validacion semantica — errores (bloquean el registro)

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 20 | Dado un lifecycle con una transicion `A -> C` y `states ["A", "B"]`, cuando se valida, entonces hay un error cuyo mensaje contiene `no declarado 'C'` | `tests/test_validator.py::test_invalid_transition_state` (`test_validator.py:25-26`) | CUMPLE |
| 21 | Dado un lifecycle con `initial: "Z"` y `states ["A"]`, cuando se valida, entonces hay un error cuyo mensaje contiene `inicial` | `tests/test_validator.py::test_initial_not_in_states` (`test_validator.py:39-40`) | CUMPLE |
| 22 | Dado `on_transition "volar"` sin ninguna transicion `via "volar"`, cuando se valida, entonces hay un error que menciona `volar` | `tests/test_validator.py::test_event_without_transition` (`test_validator.py:54-55`) | CUMPLE |
| 23 | Dada una rule con `on_event` y `on_state` a la vez, cuando se valida, entonces hay un error que contiene `exactamente un trigger` | `tests/test_validator.py::test_rule_needs_exactly_one_trigger` (`test_validator.py:66-67`) | CUMPLE |
| 24 | Dado un stage con `steps [step.inexistente]`, cuando se valida, entonces hay un error que menciona `inexistente` | `tests/test_validator.py::test_process_references_unknown_step` (`test_validator.py:76-77`) | CUMPLE |
| 25 | Dado un stage `parallel` que incluye un step `human_task`, cuando se valida, entonces hay un error que menciona `parallel` | `tests/test_validator.py::test_human_task_forbidden_in_parallel` (`test_validator.py:87-88`) | CUMPLE |
| 26 | Dado un stage `decision` con `else -> stage.end`, cuando se valida, entonces no hay errores (`end` es destino terminal valido) | `tests/test_validator.py::test_branch_to_end_is_valid` (`test_validator.py:97`) | CUMPLE |
| 27 | Dadas dos `entity "cliente"` (o dos `step "a"`) en el mismo archivo, cuando se valida, entonces hay un error con `block` `entity.cliente` (o `step.a`) y mensaje `definido más de una vez en el mismo archivo` | `tests/test_validator.py::test_duplicate_entity_is_error` (`:106-107`), `tests/test_validator.py::test_duplicate_step_is_error` (`:115`) (ver observacion sobre el alcance de los asserts) | CUMPLE |
| 28 | Dada una decision que lee `signals.revisar.signal` y `revisar` es `automated`, cuando se valida, entonces hay exactamente 1 error, que menciona `revisar`, `automated` y `else` | `tests/test_validator.py::test_una_decision_que_espera_una_firma_de_un_paso_automatico` (`test_validator.py:258-261`) | CUMPLE |
| 29 | Dada una decision que lee la firma de un step que no existe, cuando se valida, entonces hay un error que menciona el nombre y `no es un step de este archivo` | `tests/test_validator.py::test_una_decision_que_espera_una_firma_inexistente` (`test_validator.py:268-269`) | CUMPLE |
| 30 | Dada una decision que lee la firma de un `human_task` definido en el archivo pero que ese proceso no ejecuta, cuando se valida, entonces hay un error con `es un step que este proceso no ejecuta` (`validator.py:223-224`) | ninguno (Grep de `este proceso no ejecuta` en `tests/` sin coincidencias) | SIN TEST |
| 31 | Dado un `process` sin ningun stage, cuando se valida, entonces hay un error `process.<nombre>: no tiene stages` (`validator.py:92-94`) | ninguno (Grep de `no tiene stages` sin coincidencias) | SIN TEST |
| 32 | Dado un stage `decision` sin branches, cuando se valida, entonces hay un error `stage decision sin branches` (`validator.py:111-116`) | ninguno (Grep de `sin branches` sin coincidencias) | SIN TEST |
| 33 | Dado un branch que apunta a un stage que no existe y no es `end`, cuando se valida, entonces hay un error `branch apunta a stage inexistente '<nombre>'` (`validator.py:117-126`) | ninguno (Grep de `apunta a stage\|stage inexistente` sin coincidencias) | SIN TEST |
| 34 | Dado un step `notification` sin `channel`, cuando se valida, entonces hay un error `notification requiere 'channel'` (`validator.py:144-147`) | ninguno (Grep de `requiere 'channel'` sin coincidencias; todos los `notification` de los tests declaran `channel`) | SIN TEST |
| 35 | Dada una rule sin `execute`, cuando se valida, entonces hay un error `falta 'execute'` (`validator.py:76-78`) | ninguno (Grep de `falta 'execute'` sin coincidencias; los `falta '}'` de `tests/test_composer.py:309,362,377` son issues simulados del composer, no del validador) | SIN TEST |
| 36 | Dada una relation sin `from`/`to`, o con uno que no referencia `entity.<nombre>`, cuando se valida, entonces hay un error `falta '<from\|to>'` o `debe referenciar entity.<nombre>` (`validator.py:375-380`) | ninguno (Grep de `debe referenciar` sin coincidencias) | SIN TEST |
| 37 | Dado un `on_field_change` sobre un nombre que no es campo (en entity o en relation), o un `on_transition` de relation sin transicion declarada, cuando se valida, entonces hay un error (`validator.py:349-354`, `validator.py:388-395`) | ninguno (Grep de `on_field_change` en `tests/` sin coincidencias; `test_event_without_transition` cubre solo `on_transition` de **entity**) | SIN TEST |
| 38 | Dado un invariante que no parsea como expresion, cuando se valida, entonces hay un error `invariante no parseable` (`validator.py:357-369`) — `(sin test)` en el validador. Del lado del executor, un invariante con typo (`edad >= 5 AN edad <= 18`) no bloquea la transicion e incrementa `teleflow_invariants_skipped_total{reason="unparseable"}` en 1 (`executor_service/entities.py:273-281`) | Validador: ninguno (Grep de `no parseable` sin coincidencias). Executor `(indirecto)`: `tests/test_error_handling.py::test_invariante_con_typo_queda_expuesto` (`test_error_handling.py:131-135`: la llamada no levanta y la metrica sube exactamente 1) | SIN TEST (parcial: la parte del executor CUMPLE) |

### Validacion semantica — warnings (se informan, no bloquean)

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 39 | Dada una rule con `on_event: "no.existe"` en un archivo que emite otros eventos, cuando se valida, entonces hay un warning que contiene `on_event 'no.existe'` | `tests/test_validator.py::test_rule_on_event_unknown_warns` (`test_validator.py:127`) | CUMPLE |
| 40 | Dada una rule cuyo `on_event` coincide con un `emit` declarado, cuando se valida, entonces no hay warnings sobre `on_event` | `tests/test_validator.py::test_rule_on_event_known_is_clean` (`test_validator.py:138`) | CUMPLE |
| 41 | Dada una rule con `on_relation: "norel"` y ninguna relation con ese nombre, cuando se valida, entonces hay un warning que contiene `on_relation 'norel'` | `tests/test_validator.py::test_rule_on_relation_unknown_warns` (`test_validator.py:147`) | CUMPLE |
| 42 | Dada una rule con `on_state: "cli.Z"` y `Z` fuera del lifecycle de `cli`, cuando se valida, entonces hay un warning que contiene `on_state 'cli.Z'` | `tests/test_validator.py::test_rule_on_state_bad_state_warns` (`test_validator.py:157`) | CUMPLE |
| 43 | Dada una rule con `on_state: "ACTIVO"` (sin punto), cuando se valida, entonces hay un warning que contiene `<entidad\|relación>.<estado>` | `tests/test_validator.py::test_rule_on_state_malformed_warns` (`test_validator.py:164-165`) | CUMPLE |
| 44 | Dada una rule con `execute: process.fantasma` en un archivo sin procesos, cuando se valida, entonces hay un warning que menciona `process.fantasma` | `tests/test_validator.py::test_rule_a_process_inexistente_avisa_aunque_el_flow_no_tenga_procesos` (`test_validator.py:180`) | CUMPLE |
| 45 | Dado un `view360` con `alerts { rule: rule.no_existe }` en un archivo sin rules, cuando se valida, entonces hay un warning que menciona `rule.no_existe` | `tests/test_validator.py::test_view360_alerta_a_rule_inexistente_avisa_sin_rules_en_el_archivo` (`test_validator.py:191`) | CUMPLE |
| 46 | Dada una relation con `from: entity.fantasma` en un archivo sin entities, cuando se valida, entonces hay un warning que menciona `entity.fantasma` | `tests/test_validator.py::test_relation_a_entity_inexistente_avisa_sin_entities_en_el_archivo` (`test_validator.py:198`) | CUMPLE |
| 47 | Dado un archivo donde entity, process, step y rule se referencian entre si correctamente, cuando se valida, entonces la lista de warnings es vacia | `tests/test_validator.py::test_ref_valida_en_el_mismo_archivo_no_avisa` (`test_validator.py:212`) | CUMPLE |
| 48 | Dado un `human_task` con `signals ["approve", "reject"]` que ninguna decision lee, cuando se valida, entonces hay exactamente 1 warning, que menciona el step, y ningun error | `tests/test_validator.py::test_una_firma_que_nadie_lee_avisa` (`test_validator.py:287-289`) | CUMPLE |
| 49 | Dado un `human_task` con una sola senal que ninguna decision lee, cuando se valida, entonces no hay warnings | `tests/test_validator.py::test_una_firma_de_una_sola_senal_no_avisa` (`test_validator.py:302`) | CUMPLE |
| 50 | Dado un proceso cuya decision lee la firma de un `human_task` con dos senales que el proceso ejecuta, cuando se valida, entonces no hay errores ni warnings | `tests/test_validator.py::test_el_caso_bien_escrito_no_se_marca` (`test_validator.py:248-249`) | CUMPLE |
| 51 | Dada una rule con `on_timer.since` que no coincide con ningun evento emitido, cuando se valida, entonces hay un warning con `on_timer.since '<evento>'` (`validator.py:278-286`) | ninguno (Grep de `on_timer\.since` en `tests/` sin coincidencias). Solo el caso negativo queda cubierto de rebote: `detectar_abandono` usa `since: "inscripcion.activada"` (`ceibal.tflow:131`) y `test_los_ejemplos_del_repositorio_quedan_limpios` exige cero issues | SIN TEST |
| 52 | Dada una rule que escucha `<entidad>.transitioned`, `<relacion>.transitioned` o `relation.<relacion>.created` de un tipo declarado en el archivo, cuando se valida, entonces no hay warning de `on_event` (eventos sinteticos, `validator.py:258-264`) | ninguno (Grep de `transitioned\|\.created` en `tests/` y en `examples/` sin coincidencias) | SIN TEST |
| 53 | Dado un step `automated` con `integration: integration.x` no definida, un `human_task` sin `signals`, o un `view360` cuya `entity` o `relation` no esta definida, cuando se valida, entonces hay un warning por cada caso (`validator.py:129-143`, `validator.py:150-162`) | ninguno (Grep de `no definida en este archivo\|sin señales` sin coincidencias; en todos los tests los `human_task` declaran `signals` y las `integration` referenciadas existen) | SIN TEST |

### Evaluador de expresiones

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 54 | Dada `edad >= 5 AND edad <= 18`, cuando se evalua con `edad = 10`, entonces da `True`, y con `edad = 30` da `False` | `tests/test_evaluator.py::test_comparisons` (`test_evaluator.py:12-13`, `is True` / `is False`) | CUMPLE |
| 55 | Dado el contexto `{"x": None}`, cuando se evalua `x == null` da `True`, `x >= 30` da `False` y `x >= 30 OR x == null` da `True` | `tests/test_evaluator.py::test_null_handling` (`test_evaluator.py:17-20`) | CUMPLE |
| 56 | Dada `nivel != null WHEN estado == INSCRIPTO`, cuando `estado` no es `INSCRIPTO` da `True` aunque `nivel` sea nulo; con `estado = INSCRIPTO` y `nivel` nulo da `False`; con `nivel` informado da `True` | `tests/test_evaluator.py::test_when_invariant` (`test_evaluator.py:26-28`) | CUMPLE |
| 57 | Dada `estado in ["COMPLETADA", "ABANDONADA"]`, cuando `estado = "COMPLETADA"` da `True`, y `estado in ["COMPLETADA"]` con `estado = "ACTIVA"` da `False` | `tests/test_evaluator.py::test_in_operator` (`test_evaluator.py:32-34`) | CUMPLE |
| 58 | Dada la referencia con puntos `event.entity.dispositivo`, cuando el contexto la anida con valor nulo, entonces `event.entity.dispositivo == null` da `True` | `tests/test_evaluator.py::test_dotted_refs` (`test_evaluator.py:38-39`) | CUMPLE |
| 59 | Dada `days_since(relation.inscripcion.ultimo_acceso) >= 30 OR ... == null`, cuando la fecha ISO es de hace 45 dias da `True`, de hace 2 dias da `False`, y nula da `True` | `tests/test_evaluator.py::test_days_since` (`test_evaluator.py:43-54`) | CUMPLE |
| 60 | Dado un nombre suelto que no esta en el contexto (`ACTIVA`), cuando se evalua `estado == ACTIVA` con `estado = "ACTIVA"`, entonces da `True` (el nombre se toma como literal) | `tests/test_evaluator.py::test_bare_name_as_literal` (`test_evaluator.py:59`) | CUMPLE |
| 61 | Dada una llamada a una funcion que no es `days_since`, `years_since`, `now`, `len` ni una pasada en `funcs`, cuando se evalua, entonces se lanza `EvaluationError` `Función desconocida: <nombre>` (`evaluator.py:76`, `evaluator.py:86-88`) | ninguno (Grep de `EvaluationError\|Función desconocida` en `tests/` sin coincidencias) | SIN TEST |
| 62 | Dada una comparacion de orden entre tipos incomparables (p.ej. string contra numero), o un `in` contra `null`, cuando se evalua, entonces da `False` sin excepcion (`evaluator.py:115-118`, `evaluator.py:128-129`) | ninguno (`test_null_handling` prueba `>=` contra `None`, que corta en `evaluator.py:117-118`, no la rama `TypeError` de `:128-129` ni `in` contra `null`). `test_invariante_no_evaluable_no_bloquea` fuerza el `TypeError` con monkeypatch sobre `evaluate` del executor, asi que tampoco ejercita el evaluador | SIN TEST |
| 63 | Dada una referencia con puntos cuyo camino no existe en el contexto, cuando se evalua, entonces resuelve a `None` (`evaluator.py:70`) | ninguno (Grep de `resolve_ref` en `tests/` sin coincidencias; `test_dotted_refs` y `test_days_since` usan caminos que existen con valor `None`) | SIN TEST |

### Serializacion del AST

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 64 | Dado el `FlowFile` de ceibal, cuando se pasa por `to_jsonable` y `json.dumps`, entonces no falla y el texto contiene `"_node": "EntityDef"` | `tests/test_parser.py::test_ast_serializable` (`test_parser.py:154-156`) | CUMPLE |
| 65 | Dado un `FlowFile` con duplicados registrados, cuando se serializa, entonces el JSON no contiene la clave `duplicates` (`ast_nodes.py:312-314`, `serialize.py:12-13`) | ninguno (Grep de `duplicates` en `tests/` sin coincidencias) | SIN TEST |
| 66 | Dada una `Ref`, cuando se serializa, entonces `parts` sale como lista JSON y el nodo lleva `"_node": "Ref"` (`serialize.py:9-10`, `serialize.py:18-19`) | ninguno (`test_ast_serializable` solo busca `EntityDef`; Grep de `_node.*Ref` sin coincidencias) | SIN TEST |

### Servicio HTTP `POST /parse`

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 67 | Dada una fuente con error de sintaxis en la linea 3, cuando se hace `POST /parse`, entonces responde `200`, `issues[0].block == "syntax"`, `issues[0].line == 3` e `issues[0].column` no es nulo | `tests/test_parser.py::test_el_servicio_publica_la_posicion_del_error` (`test_parser.py:234-238`, `TestClient` sobre `parser_service.main.app`) | CUMPLE |
| 68 | Dada una fuente que parsea pero referencia `step.no_existe`, cuando se hace `POST /parse`, entonces `valid` es `false`, `issues` no es vacio y todos los issues tienen `line: null` | `tests/test_parser.py::test_los_issues_del_validador_no_inventan_posicion` (`test_parser.py:260-262`) | CUMPLE |
| 69 | Dada una fuente con error de sintaxis, cuando se hace `POST /parse`, entonces `ast` es `null`, `summary` es `{}` y hay un unico issue de nivel `error` (`teleflow/parser_service/main.py:58-65`) | ninguno (`test_el_servicio_publica_la_posicion_del_error` no afirma `ast`, `summary`, `len(issues)` ni `level`) | SIN TEST |
| 70 | Dada una fuente valida, cuando se hace `POST /parse`, entonces `valid` es `true`, `ast` trae el `FlowFile` serializado y `summary` trae las siete listas ordenadas `entities`, `relations`, `rules`, `views`, `processes`, `steps`, `integrations` (`teleflow/parser_service/main.py:67-86`) | ninguno en unitarios (Grep de `summary` en `tests/` solo encuentra `tests/test_alertas.py:71`, ajeno). En e2e tampoco: Grep de `parse\|valid\|summary` en `tests/e2e/` no encuentra ningun test de `/parse` | SIN TEST |
| 71 | Dada una fuente que solo produce warnings, cuando se hace `POST /parse`, entonces `valid` es `true` y los warnings viajan en `issues` (`teleflow/parser_service/main.py:68`, `teleflow/parser_service/main.py:80-85`) | ninguno | SIN TEST |
| 72 | Dada cualquier fuente, valida o no, cuando se hace `POST /parse`, entonces `checksum` es el SHA-256 hexadecimal del `source` en UTF-8 (`teleflow/parser_service/main.py:55`, `parser.py:171-172`) | ninguno (Grep de `checksum` en `tests/`: solo `tests/test_auditoria.py:67-80`, que prueba que el gateway no guarda el `source` y no afirma ningun hash) | SIN TEST |
| 73 | Dado el parser-service levantado, cuando se pide `GET /health`, entonces responde `{"status": "ok", "service": "parser-service"}` (`teleflow/parser_service/main.py:19`, `teleflow/common/observability.py:46-48`) | ninguno en este modulo (los `GET /health` de `tests/test_gateway_scopes.py:136` y `tests/test_auditoria.py:176` van contra la app del gateway y solo miran el status code; `tests/e2e/conftest.py:30` pega al gateway) | SIN TEST |

### Ejemplos de referencia

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 74 | Dado `examples/ceibal.tflow`, cuando se parsea, entonces define las entities `nino` y `curso`, la relation `inscripcion`, 5 rules, la vista `nino`, 5 procesos, la integration `lms`, el catalog `cursos_ceibal` y el party `tutor` | `tests/test_parser.py::test_parse_ceibal_blocks` (`test_parser.py:11-18`) | CUMPLE |
| 75 | Dados `examples/ceibal.tflow` y `examples/venta_internet_hogar.tflow`, cuando se validan, entonces `validate_flow` devuelve la lista vacia (ni errores ni warnings) | `tests/test_validator.py::test_los_ejemplos_del_repositorio_quedan_limpios` (`test_validator.py:308-309`, `== []` para los dos). `tests/test_parser.py::test_validation_clean` solo afirma cero errores en ceibal (`:84-85`) | CUMPLE |
| 76 | Dado cualquier proceso de los dos ejemplos, cuando el executor arma su DAG de stages, entonces el grafo es aciclico; en `asignacion_dispositivo` el orden topologico es `verificacion, entrega`, y en `venta_internet_hogar` existen las aristas `decidir -> activacion` y `decidir -> rechazo` | `(indirecto)` `tests/test_dag.py::test_el_pegote_terminal_sigue_funcionando` (aciclicidad de todos los procesos de ambos ejemplos, `:107-109`), `tests/test_dag.py::test_sequential_dag` (`:15`), `tests/test_dag.py::test_decision_dag` (`:22-24`) | CUMPLE |
| 77 | Dado un proceso parseado con una decision de dos ramas escritas una debajo de la otra, cuando el executor arma el DAG, entonces hay aristas desde la decision a las dos ramas y no entre las ramas hermanas | `(indirecto)` `tests/test_dag.py::test_una_rama_no_cae_en_su_hermana` (`test_dag.py:56-59`) | CUMPLE |

### Conteo

| Grupo | Criterios | CUMPLE | NO CUMPLE | SIN TEST |
|---|---|---|---|---|
| Gramatica y parseo | 12 | 9 | 0 | 3 |
| Errores de sintaxis | 7 | 6 | 0 | 1 |
| Validacion — errores | 19 | 10 | 0 | 9 |
| Validacion — warnings | 15 | 12 | 0 | 3 |
| Evaluador | 10 | 7 | 0 | 3 |
| Serializacion | 3 | 1 | 0 | 2 |
| `POST /parse` | 7 | 2 | 0 | 5 |
| Ejemplos de referencia | 4 | 4 | 0 | 0 |
| **Total** | **77** | **51** | **0** | **26** |

Ningun criterio marcado `(sin test)` en la spec resulto tener test: los 26 SIN TEST coinciden uno a
uno con los que la spec ya marcaba. Los dos `(indirecto)` que prueban el resultado (76, 77) quedan
CUMPLE; el `(indirecto)` del criterio 38 cubre solo la mitad del executor.

Para los SIN TEST se leyo ademas el codigo citado: en ninguno el codigo contradice el criterio
(`validator.py:76-78, 92-94, 111-126, 129-162, 223-224, 258-286, 349-395`,
`evaluator.py:58-130`, `serialize.py:8-20`, `ast_nodes.py:312-314`, `parser_service/main.py:52-86`,
`parser.py:110-112, 171-172`, `observability.py:46-48`, `teleflow.lark:7, 210-213`,
`transformer.py:436-440`). Eso no los vuelve CUMPLE: el codigo "parece hacerlo", nadie lo prueba.

## Criterios sin test

Lo que la spec promete y ningun test comprueba. Cada uno es trabajo pendiente, no un detalle.

- **#10** — comentarios con `#` ignorados (el `//` si queda cubierto por los ejemplos).
- **#11** — fuente vacia → `FlowFile` vacio y `validate_flow` devuelve `[]`.
- **#12** — `product` con `price` como float y `currency` como string.
- **#19** — mas de 8 terminales esperados → 8 descripciones y `, …`.
- **#30** — firma de un `human_task` que el proceso no ejecuta → `es un step que este proceso no ejecuta`.
- **#31** — `process` sin stages → `no tiene stages`.
- **#32** — stage `decision` sin branches → `stage decision sin branches`.
- **#33** — branch a stage inexistente distinto de `end`.
- **#34** — `notification` sin `channel`.
- **#35** — rule sin `execute`.
- **#36** — relation sin `from`/`to` o que no referencia `entity.<nombre>`.
- **#37** — `on_field_change` sobre algo que no es campo (entity y relation) y `on_transition` de relation sin transicion.
- **#38** — invariante no parseable como error del **validador** (la metrica del executor si esta probada).
- **#51** — warning por `on_timer.since` desconocido.
- **#52** — eventos sinteticos `<tipo>.transitioned` / `relation.<tipo>.created` no avisan.
- **#53** — warnings por `integration` no definida, `human_task` sin `signals` y `view360` con `entity`/`relation` no definida.
- **#61** — funcion desconocida → `EvaluationError`.
- **#62** — comparacion de orden entre tipos incomparables y `in` contra `null` → `False` sin excepcion.
- **#63** — referencia con puntos a un camino inexistente → `None`.
- **#65** — el JSON serializado no incluye `duplicates`.
- **#66** — `Ref` serializada con `parts` como lista y `"_node": "Ref"`.
- **#69** — `POST /parse` con error de sintaxis: `ast: null`, `summary: {}`, un unico issue `error`.
- **#70** — `POST /parse` con fuente valida: `valid: true`, `ast` y las siete listas del `summary`.
- **#71** — `POST /parse` con solo warnings: `valid: true` y warnings en `issues`.
- **#72** — `checksum` = SHA-256 hex del `source` en UTF-8.
- **#73** — `GET /health` del parser-service.

Concentracion: 9 de los 26 son errores del validador que bloquean el registro (#30-#38). Un
regreso en cualquiera de ellos deja pasar al deploy un flow incoherente sin que ningun test falle
`(inferencia: consecuencia de que el gateway rechaza solo si valid es false, gateway/main.py:613-629, citado por spec.md; no re-leido en esta pasada)`.

## Comportamiento observado que la spec no menciona

Tests que prueban algo que ningun criterio pide, y precisiones sobre el alcance real de los
asserts. Se anota, no se decide aca.

- **Semantica de ejecucion en `tests/test_dag.py`** (6 tests, todos `PASSED`):
  `test_la_caida_sigue_valiendo_fuera_de_las_ramas`, `test_una_rama_de_varios_stages_sigue_encadenada`,
  `test_al_terminar_una_rama_el_proceso_termina`, `test_sin_venir_de_una_decision_se_cae_normal`,
  `test_dentro_de_una_rama_se_sigue_cayendo`, `test_la_ultima_rama_termina_por_fin_de_archivo`.
  Prueban `build_stage_dag` y `siguiente_stage` del executor; la spec deja esa semantica explicitamente
  fuera ("No entra: Semantica de ejecucion"). No es un criterio faltante de este modulo sino de la
  linea base del executor.
- **`tests/test_parser.py::test_validation_clean`** (`:81-85`) queda subsumido por
  `test_los_ejemplos_del_repositorio_quedan_limpios`: afirma solo cero errores y solo para ceibal.
- **Tests con la misma entrada**: `test_syntax_error_reports_line` y `test_unexpected_char_message`
  parsean la misma fuente (`test_parser.py:111`, `:117`); `test_el_error_de_sintaxis_lleva_linea_y_columna`
  y `test_un_identificador_con_tilde_no_parsea` tambien (`FUENTE_CON_ERROR_EN_LA_LINEA_3`,
  `test_parser.py:192-197`, y la fuente literal identica en `:272-277`).
- **Criterio #9 (duplicados en el parseo)**: el test no llama al transformer por separado. "No se
  lanza excepcion" queda probado porque `parser.parse` corre sin `pytest.raises`; "se registra en
  `FlowFile.duplicates`" queda probado a traves del unico emisor de ese mensaje
  (`validator.py:49-54`). "Queda uno solo en el diccionario" **no tiene assert**: lo garantiza el tipo
  `dict` (`ast_nodes.py:301-309`). Cual de los dos bloques sobrevive (el ultimo,
  `transformer.py:491`) no lo pide la spec ni lo fija ningun test.
- **Criterio #27 (mensaje de duplicado)**: los asserts son mas laxos que el criterio.
  `test_duplicate_entity_is_error` busca la subcadena `más de una vez` y `"entity.cliente" in e.block`
  (pertenencia, no igualdad); `test_duplicate_step_is_error` solo mira `"step.a" in e.block` y no
  el mensaje. El texto literal `definido más de una vez en el mismo archivo` no se afirma completo.
- **Criterio #76 / discrepancia ya anotada en la spec, confirmada**: `test_el_pegote_terminal_sigue_funcionando`
  dice cubrir flows con el stage decision terminal, pero Grep de `stage "\|stage\.end` en `examples/`
  muestra que ninguno lo tiene (`venta_internet_hogar.tflow:17-39`: `validacion`, `aprobacion`,
  `decidir`, `activacion`, `rechazo`). El test sigue probando aciclicidad, que es lo que pide el
  criterio; la compatibilidad con el "pegote" no esta probada en el DAG.
- **Criterio #62, hueco adyacente**: `_compare` evalua `left in right` fuera del `try`
  (`evaluator.py:115-116`, el `try` empieza en `:119`), asi que un `in` contra un valor no nulo y no
  iterable (p.ej. un numero) levantaria `TypeError` en vez de dar `False`
  `(inferencia: lectura de codigo, no ejecutado)`. El criterio solo promete el caso `in` contra
  `null`, por lo que no lo contradice; queda para que una persona decida si es un criterio faltante.
- **Criterio #38, lado executor**: `test_error_handling.py` tiene ademas
  `test_invariante_valido_sigue_bloqueando` y `test_invariante_no_evaluable_no_bloquea`
  (`:138-160`), que no se corrieron en esta pasada y que ningun criterio de esta spec pide (son del
  executor).
