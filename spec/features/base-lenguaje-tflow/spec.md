---
project: copp-ia
type: spec
status: implementada
feature: base-lenguaje-tflow
provenance: copp-ia@devyos@5e64479
created: 2026-09-14
---

<!-- Linea base as-built: documenta lo que el codigo hace hoy. Nunca se sincroniza con Jira. -->
<!-- Lo escribe el subagente `analista-requisitos` (modo as-built). Ante conflicto, manda el codigo. -->


# Linea base — lenguaje `.tflow` (gramatica, parser, validador, evaluador, parser-service)

## Que resuelve

Un organismo declara su dominio de negocio (entidades, relaciones, reglas, vistas 360,
procesos, pasos, integraciones, catalogos y actores) en un archivo `.tflow`, y la plataforma
necesita convertir ese texto en una estructura tipada, rechazar lo que esta mal escrito con la
posicion exacta del error, y marcar lo que esta bien escrito pero es incoherente antes de
registrarlo o ejecutarlo.

Lo resuelve hoy asi (comprobado leyendo el codigo en `copp-ia@devyos@5e64479`):

- **Gramatica unica**: `teleflow/dsl/teleflow.lark:1-5` se declara fuente de verdad del lenguaje
  (ADR-001). Nueve tipos de bloque de primer nivel (`teleflow.lark:7-17`) y un sublenguaje de
  expresiones (`teleflow.lark:176-195`).
- **Parser LALR** con dos puntos de entrada, archivo completo y expresion suelta
  (`teleflow/dsl/parser.py:57-63`, `parser.py:66-81`), y un singleton de proceso
  (`parser.py:164-168`).
- **Transformer** que baja el arbol de Lark a dataclasses (`teleflow/dsl/transformer.py:47`,
  `teleflow/dsl/ast_nodes.py:297-314`) y registra los nombres declarados dos veces en el mismo
  archivo en vez de pisarlos en silencio (`transformer.py:488-491`).
- **Errores de sintaxis legibles** en castellano, con linea, columna, terminales esperados y el
  fragmento con apuntador (`parser.py:114-158`).
- **Validacion semantica** que separa `error` (bloquea el registro) de `warning` (se informa y no
  bloquea) (`teleflow/dsl/validator.py:1-11`, `validator.py:46-171`).
- **Evaluador null-safe** de expresiones para condiciones, filtros e invariantes
  (`teleflow/dsl/evaluator.py:1-9`, `evaluator.py:74-130`).
- **Serializacion del AST a JSON** para el registro y la API (`teleflow/dsl/serialize.py:8-20`).
- **Servicio HTTP** `POST /parse` en el parser-service, que nunca ejecuta nada
  (`teleflow/parser_service/main.py:1-4`, `teleflow/parser_service/main.py:52-86`).

## Objetivo

Que todo `.tflow` que llegue a la plataforma quede parseado a un AST tipado o rechazado con la
posicion del error, y que las incoherencias semanticas conocidas se reporten como error o
warning antes del registro.

## Alcance

**Entra:**

- `teleflow/dsl/teleflow.lark` — gramatica completa: `entity`, `relation`, `rule`, `view360`,
  `process`, `step`, `integration`, `catalog`, `party`, duraciones, expresiones, literales y
  comentarios (`teleflow.lark:7-213`).
- `teleflow/dsl/parser.py` — `TeleFlowParser.parse`, `parse_expr`, `TeleFlowSyntaxError`,
  `get_parser`, `checksum`.
- `teleflow/dsl/transformer.py` y `teleflow/dsl/ast_nodes.py` — AST en dataclasses, incluido
  `FlowFile.merge` (`ast_nodes.py:316-329`).
- `teleflow/dsl/validator.py` — `validate_flow` y sus chequeos.
- `teleflow/dsl/evaluator.py` — `evaluate`, `resolve_ref`, funciones built-in
  (`evaluator.py:50-55`).
- `teleflow/dsl/serialize.py` — `to_jsonable`.
- `teleflow/dsl/__init__.py` — superficie publica exportada (`teleflow/dsl/__init__.py:1-10`).
- `teleflow/parser_service/main.py` — `POST /parse`.
- `examples/ceibal.tflow` y `examples/venta_internet_hogar.tflow` — flows de referencia que
  tienen que validar limpios (`AGENTS.md:40`).

**No entra (y por que):**

- **Validacion semantica de `catalog` y `party`.** La gramatica los acepta
  (`teleflow.lark:160-173`) y el transformer los arma (`transformer.py:433-467`), pero
  `validate_flow` no recorre `flow.catalogs` ni `flow.parties` (`validator.py:46-171`): un
  `instantiates: entity.no_existe` o `entity: entity.no_existe` pasa sin error ni warning, y
  `price` no tiene cota. Motivo observado: fuera de `teleflow/dsl/` no hay ningun consumidor de
  `catalogs` ni de `parties` (busqueda de `catalog|party|parties` en `teleflow/`: solo aparecen en
  `teleflow.lark`, `ast_nodes.py` y `transformer.py`), asi que hoy son bloques declarativos sin
  efecto. Que por eso nadie priorizo validarlos es `(inferencia)`.
- **`catalogs` y `parties` en el `summary` de `POST /parse`.** El `summary` lista solo siete
  categorias: `entities`, `relations`, `rules`, `views`, `processes`, `steps`, `integrations`
  (`parser_service/main.py:69-77`), y el log `parse_ok` cuenta las mismas
  (`teleflow/parser_service/main.py:78-79`). Los catalogos y actores si viajan dentro del `ast`
  (`teleflow/parser_service/main.py:83`, `ast_nodes.py:308-309`). Motivo: mismo que el anterior, sin consumidor.
- **Limite de tamaño de la fuente.** `ParseRequest.source` es `str` sin `max_length`
  (`parser_service/main.py:22-24`); el gateway tampoco lo acota ni en el deploy
  (`teleflow/gateway/main.py:598-601`) ni en el proxy de `/parse`, que lee el body entero
  (`gateway/main.py:416`). Una busqueda de `body-size|client_max|limit-request|h11_max|max_request`
  en todo el repo no da coincidencias. Motivo: no se decidio un limite; queda escrito como hueco.
  No verificado: limites que pueda imponer un ingress del organismo, que esta fuera del repo.
- **Identificadores con tilde o no ASCII.** `NAME` es `/[a-zA-Z_][a-zA-Z0-9_]*/`
  (`teleflow.lark:206`): `step.notificación` es error de sintaxis. El texto entre comillas si
  acepta cualquier caracter (`teleflow.lark:208`). Es comportamiento fijado por test
  (`tests/test_parser.py::test_un_identificador_con_tilde_no_parsea`), no un descuido; el motivo
  que da el test es que los identificadores son ASCII y el texto entre comillas no
  (`tests/test_parser.py:265-269`).
- **Validacion de las referencias dentro de expresiones.** `condition`, `with`, `where`,
  `filter` y los invariantes no se contrastan contra los campos declarados: de los invariantes
  solo se comprueba que parseen (`validator.py:357-369`). Ademas un nombre suelto que no existe
  en el contexto se evalua como literal string (`evaluator.py:68-69`), asi que un typo como
  `estdo == ACTIVA` no falla: compara `"estdo"` contra `"ACTIVA"` y da `False`. Motivo: el
  literal implicito es lo que permite escribir estados sin comillas
  (`tests/test_evaluator.py::test_bare_name_as_literal`); no hay chequeo que lo compense.
- **El prefijo (`kind`) de las referencias en steps, branches y alerts.** El validador compara
  solo la ultima parte (`Ref.target`, `ast_nodes.py:35-37`) en `validator.py:97`,
  `validator.py:119` y `validator.py:164`: `steps [entity.x]` resuelve si existe `step "x"`. Un
  `execute:` cuyo prefijo no es `process` no genera ningun issue (`validator.py:76-87`). Sin test.
- **Duplicados entre archivos del dominio.** Los duplicados solo se detectan dentro de un
  archivo (`transformer.py:488-491`, `validator.py:49-54`). Al combinar flows,
  `FlowFile.merge` resuelve "ultimo gana por nombre" y no conserva `duplicates`
  (`ast_nodes.py:316-329`); el executor lo usa asi (`executor_service/domain.py:81`). Sin test.
- **Coherencia de campos.** No se valida `default` fuera de `range`, `default` fuera de los
  valores del `enum`, ni `required` y `optional` a la vez: `validate_flow` no inspecciona
  `FieldDef` salvo el nombre (`validator.py:340`, `validator.py:387`). Tampoco las claves de
  `integration` (cualquier `NAME: literal`, `teleflow.lark:156`) ni la semantica de un step
  `type: decision` (`teleflow.lark:150`). Sin test.
- **Marcador de version del lenguaje.** Ningun bloque de la gramatica declara version
  (`teleflow.lark:7-17`); el ADR de caida secuencial lo deja como deuda (opcion E,
  `wiki/Knowledge/decisions/2026-08-27-caida-secuencial-entre-etapas.md:145-146`).
- **Deserializar el AST JSON.** No existe el camino inverso de `to_jsonable`: el executor
  re-parsea el `source` registrado (`executor_service/domain.py:3-4`, `domain.py:97-98`).
- **Aritmetica en expresiones.** La gramatica no tiene operadores `+ - * /`
  (`teleflow.lark:176-195`); `1 + ` es expresion invalida
  (`tests/test_parser.py::test_parse_expr_gives_context`).
- **Semantica de ejecucion** (caida entre etapas, ramas, reintentos, durable sleep). Vive en el
  executor (`executor_service/engine.py`), no en el DSL; aca solo se usa como evidencia indirecta
  de que el AST de procesos es consumible.

## Criterios de aceptacion

Cada criterio nombra el test que lo comprueba. `(sin test)` = el codigo lo hace y ningun test lo
prueba. `(indirecto)` = lo prueba un test de otro modulo que consume el DSL.

### Gramatica y parseo

- [ ] Dado `examples/ceibal.tflow`, cuando se parsea, entonces `entity "nino"` tiene
  `lifecycle.initial == "REGISTRADO"`, exactamente los estados `REGISTRADO, ACTIVO, INSCRIPTO,
  GRADUADO, INACTIVO`, transiciones con `via` que incluyen `activar`, `inscribir` y `graduar`,
  2 invariantes y un evento que emite `nino.inscripto` —
  `tests/test_parser.py::test_entity_nino_lifecycle`
- [ ] Dado `examples/ceibal.tflow`, cuando se parsean los campos, entonces `ci` queda `required`
  y `unique`, `nivel` es `enum` con valores `["primaria", "secundaria", "utu"]`, `dispositivo`
  queda `optional`, y el campo `progreso` de `relation "inscripcion"` tiene `has_default`,
  `default == 0` y `range == (0.0, 100.0)` — `tests/test_parser.py::test_entity_fields`
- [ ] Dado `relation "inscripcion"` de ceibal, cuando se parsea, entonces `from_ref.dotted ==
  "entity.nino"`, `to_ref.dotted == "entity.curso"` y `cardinality == "many_to_many"` —
  `tests/test_parser.py::test_relation_refs`
- [ ] Dada la rule `detectar_abandono` de ceibal con `on_timer { after: 30 days ... }`, cuando se
  parsea, entonces `timer.after_seconds == 2592000`, `timer.since == "inscripcion.activada"`,
  `execute.dotted == "process.reenganche_estudiante"` y `with` tiene exactamente las claves
  `nino_id` y `curso_id` — `tests/test_parser.py::test_timer_rule`
- [ ] Dado `view360 "nino"` de ceibal, cuando se parsea, entonces `entity.dotted ==
  "entity.nino"`, tiene 2 relaciones (la primera con alias `inscripciones_activas`, `where` no
  nulo e `include == ["curso.nombre", "progreso", "ultimo_acceso"]`), `timeline.limit == 50`,
  2 alerts y 4 procesos en `active_processes.include` — `tests/test_parser.py::test_view360`
- [ ] Dado `examples/venta_internet_hogar.tflow`, cuando se parsea, entonces el proceso tiene los
  stages `validacion, aprobacion, decidir, activacion, rechazo` en ese orden, `decidir` es
  `decision` con 2 branches (la primera apunta a `activacion`, la segunda es `else` con
  `condition is None`), `aprobacion_gerencia` es `human_task` con `signals == ["approve",
  "reject"]` y `timeout_seconds == 604800`, y `validate_flow` no da errores —
  `tests/test_parser.py::test_venta_decision_stages`
- [ ] Dado un step con `timeout: <n> <unidad>`, cuando la unidad es `second|seconds`,
  `minute|minutes`, `hour|hours`, `day|days` o `week|weeks`, entonces parsea y
  `timeout_seconds` vale `n` por 1, 60, 3600, 86400 o 604800 respectivamente (10 casos
  parametrizados) — `tests/test_parser.py::test_las_unidades_de_tiempo_aceptan_singular_y_plural`
- [ ] Dado un identificador con tilde (`step.notificación`) en la linea 3, cuando se parsea,
  entonces se lanza `TeleFlowSyntaxError` con `line == 3` y el mensaje contiene `ó` —
  `tests/test_parser.py::test_un_identificador_con_tilde_no_parsea`
- [ ] Dado un archivo con dos bloques de la misma categoria y el mismo nombre, cuando se parsea,
  entonces no se lanza excepcion, queda uno solo en el diccionario y el par
  `(categoria, nombre)` se registra en `FlowFile.duplicates` (`transformer.py:488-491`) —
  comprobado a traves del validador en `tests/test_validator.py::test_duplicate_entity_is_error`
- [ ] Dado un archivo con comentarios `// ...` y `# ...`, cuando se parsea, entonces los
  comentarios se ignoran (`teleflow.lark:210-213`) — `(sin test)` para `#`; `//` queda cubierto
  porque `examples/ceibal.tflow:1-5` lo usa y `tests/test_parser.py::test_parse_ceibal_blocks`
  parsea ese archivo
- [ ] Dada una fuente vacia, cuando se parsea, entonces devuelve un `FlowFile` con todas las
  categorias vacias (`teleflow.lark:7` es `block*`) y `validate_flow` devuelve `[]` — `(sin test)`
- [ ] Dado un `product` con `price: 100` y `currency: "UYU"` dentro de un `catalog`, cuando se
  parsea, entonces `price == 100.0` (float) y `currency == "UYU"` (`transformer.py:436-440`) —
  `(sin test)`; la presencia de catalogos y actores si esta probada en
  `tests/test_parser.py::test_parse_ceibal_blocks`

### Errores de sintaxis

- [ ] Dada la fuente `entity "x" { lifecycle { ??? } }`, cuando se parsea, entonces se lanza
  `TeleFlowSyntaxError` con `line` y `column` no nulos y un mensaje que contiene
  `carácter inesperado '?'` — `tests/test_parser.py::test_syntax_error_reports_line`,
  `tests/test_parser.py::test_unexpected_char_message`
- [ ] Dada la fuente `rule "r" { on_state: }`, cuando se parsea, entonces el mensaje contiene
  `se esperaba` y `exc.expected` contiene el nombre de terminal `STRING` —
  `tests/test_parser.py::test_unexpected_token_lists_expected`
- [ ] Dada la fuente `entity "x" ` (sin abrir el bloque), cuando se parsea, entonces el mensaje
  contiene `fin de archivo inesperado` y `'{'` —
  `tests/test_parser.py::test_unexpected_eof_message`
- [ ] Dada la expresion `1 + `, cuando se llama a `parse_expr`, entonces se lanza
  `TeleFlowSyntaxError` con `line` y `column` no nulos y un mensaje que contiene
  `Expresión inválida` y `se esperaba` — `tests/test_parser.py::test_parse_expr_gives_context`
- [ ] Dada una fuente cuyo error esta en la linea 3, cuando se parsea, entonces
  `exc.line == 3` y `exc.column` no es nulo —
  `tests/test_parser.py::test_el_error_de_sintaxis_lleva_linea_y_columna`
- [ ] Dado un error de sintaxis en un archivo multilinea, cuando se lee `exc.message`, entonces
  tiene mas de una linea y alguna linea posterior a la primera contiene el apuntador `^` —
  `tests/test_parser.py::test_el_mensaje_incluye_el_fragmento_con_el_apuntador`
- [ ] Dado un error con mas de 8 terminales esperados, cuando se arma el mensaje, entonces se
  muestran 8 descripciones seguidas de `, …` (`parser.py:110-112`) — `(sin test)`

### Validacion semantica

Errores (bloquean el registro):

- [ ] Dado un lifecycle con una transicion `A -> C` y `states ["A", "B"]`, cuando se valida,
  entonces hay un error cuyo mensaje contiene `no declarado 'C'` —
  `tests/test_validator.py::test_invalid_transition_state`
- [ ] Dado un lifecycle con `initial: "Z"` y `states ["A"]`, cuando se valida, entonces hay un
  error cuyo mensaje contiene `inicial` — `tests/test_validator.py::test_initial_not_in_states`
- [ ] Dado `on_transition "volar"` sin ninguna transicion `via "volar"`, cuando se valida,
  entonces hay un error que menciona `volar` —
  `tests/test_validator.py::test_event_without_transition`
- [ ] Dada una rule con `on_event` y `on_state` a la vez, cuando se valida, entonces hay un error
  que contiene `exactamente un trigger` —
  `tests/test_validator.py::test_rule_needs_exactly_one_trigger`
- [ ] Dado un stage con `steps [step.inexistente]`, cuando se valida, entonces hay un error que
  menciona `inexistente` — `tests/test_validator.py::test_process_references_unknown_step`
- [ ] Dado un stage `parallel` que incluye un step `human_task`, cuando se valida, entonces hay
  un error que menciona `parallel` —
  `tests/test_validator.py::test_human_task_forbidden_in_parallel`
- [ ] Dado un stage `decision` con `else -> stage.end`, cuando se valida, entonces no hay
  errores (`end` es destino terminal valido) — `tests/test_validator.py::test_branch_to_end_is_valid`
- [ ] Dadas dos `entity "cliente"` (o dos `step "a"`) en el mismo archivo, cuando se valida,
  entonces hay un error con `block` `entity.cliente` (o `step.a`) y mensaje
  `definido más de una vez en el mismo archivo` —
  `tests/test_validator.py::test_duplicate_entity_is_error`,
  `tests/test_validator.py::test_duplicate_step_is_error`
- [ ] Dada una decision que lee `signals.revisar.signal` y `revisar` es `automated`, cuando se
  valida, entonces hay exactamente 1 error, que menciona `revisar`, `automated` y `else` —
  `tests/test_validator.py::test_una_decision_que_espera_una_firma_de_un_paso_automatico`
- [ ] Dada una decision que lee la firma de un step que no existe, cuando se valida, entonces hay
  un error que menciona el nombre y `no es un step de este archivo` —
  `tests/test_validator.py::test_una_decision_que_espera_una_firma_inexistente`
- [ ] Dada una decision que lee la firma de un `human_task` definido en el archivo pero que ese
  proceso no ejecuta, cuando se valida, entonces hay un error con
  `es un step que este proceso no ejecuta` (`validator.py:223-224`) — `(sin test)`
- [ ] Dado un `process` sin ningun stage, cuando se valida, entonces hay un error
  `process.<nombre>: no tiene stages` (`validator.py:92-94`) — `(sin test)`
- [ ] Dado un stage `decision` sin branches, cuando se valida, entonces hay un error
  `stage decision sin branches` (`validator.py:111-116`) — `(sin test)`
- [ ] Dado un branch que apunta a un stage que no existe y no es `end`, cuando se valida,
  entonces hay un error `branch apunta a stage inexistente '<nombre>'`
  (`validator.py:117-126`) — `(sin test)`
- [ ] Dado un step `notification` sin `channel`, cuando se valida, entonces hay un error
  `notification requiere 'channel'` (`validator.py:144-147`) — `(sin test)`
- [ ] Dada una rule sin `execute`, cuando se valida, entonces hay un error `falta 'execute'`
  (`validator.py:76-78`) — `(sin test)`
- [ ] Dada una relation sin `from`/`to`, o con uno que no referencia `entity.<nombre>`, cuando se
  valida, entonces hay un error `falta '<from|to>'` o `debe referenciar entity.<nombre>`
  (`validator.py:375-380`) — `(sin test)`
- [ ] Dado un `on_field_change` sobre un nombre que no es campo (en entity o en relation), o un
  `on_transition` de relation sin transicion declarada, cuando se valida, entonces hay un error
  (`validator.py:349-354`, `validator.py:388-395`) — `(sin test)`
- [ ] Dado un invariante que no parsea como expresion, cuando se valida, entonces hay un error
  `invariante no parseable` (`validator.py:357-369`) — `(sin test)` en el validador. Del lado del
  executor, un invariante con typo (`edad >= 5 AN edad <= 18`) no bloquea la transicion e
  incrementa `teleflow_invariants_skipped_total{reason="unparseable"}` en 1
  (`executor_service/entities.py:273-281`) — `(indirecto)`
  `tests/test_error_handling.py::test_invariante_con_typo_queda_expuesto`

Warnings (se informan, no bloquean):

- [ ] Dada una rule con `on_event: "no.existe"` en un archivo que emite otros eventos, cuando se
  valida, entonces hay un warning que contiene `on_event 'no.existe'` —
  `tests/test_validator.py::test_rule_on_event_unknown_warns`
- [ ] Dada una rule cuyo `on_event` coincide con un `emit` declarado, cuando se valida, entonces
  no hay warnings sobre `on_event` — `tests/test_validator.py::test_rule_on_event_known_is_clean`
- [ ] Dada una rule con `on_relation: "norel"` y ninguna relation con ese nombre, cuando se
  valida, entonces hay un warning que contiene `on_relation 'norel'` —
  `tests/test_validator.py::test_rule_on_relation_unknown_warns`
- [ ] Dada una rule con `on_state: "cli.Z"` y `Z` fuera del lifecycle de `cli`, cuando se valida,
  entonces hay un warning que contiene `on_state 'cli.Z'` —
  `tests/test_validator.py::test_rule_on_state_bad_state_warns`
- [ ] Dada una rule con `on_state: "ACTIVO"` (sin punto), cuando se valida, entonces hay un
  warning que contiene `<entidad|relación>.<estado>` —
  `tests/test_validator.py::test_rule_on_state_malformed_warns`
- [ ] Dada una rule con `execute: process.fantasma` en un archivo sin procesos, cuando se valida,
  entonces hay un warning que menciona `process.fantasma` —
  `tests/test_validator.py::test_rule_a_process_inexistente_avisa_aunque_el_flow_no_tenga_procesos`
- [ ] Dado un `view360` con `alerts { rule: rule.no_existe }` en un archivo sin rules, cuando se
  valida, entonces hay un warning que menciona `rule.no_existe` —
  `tests/test_validator.py::test_view360_alerta_a_rule_inexistente_avisa_sin_rules_en_el_archivo`
- [ ] Dada una relation con `from: entity.fantasma` en un archivo sin entities, cuando se valida,
  entonces hay un warning que menciona `entity.fantasma` —
  `tests/test_validator.py::test_relation_a_entity_inexistente_avisa_sin_entities_en_el_archivo`
- [ ] Dado un archivo donde entity, process, step y rule se referencian entre si correctamente,
  cuando se valida, entonces la lista de warnings es vacia —
  `tests/test_validator.py::test_ref_valida_en_el_mismo_archivo_no_avisa`
- [ ] Dado un `human_task` con `signals ["approve", "reject"]` que ninguna decision lee, cuando
  se valida, entonces hay exactamente 1 warning, que menciona el step, y ningun error —
  `tests/test_validator.py::test_una_firma_que_nadie_lee_avisa`
- [ ] Dado un `human_task` con una sola senal que ninguna decision lee, cuando se valida,
  entonces no hay warnings — `tests/test_validator.py::test_una_firma_de_una_sola_senal_no_avisa`
- [ ] Dado un proceso cuya decision lee la firma de un `human_task` con dos senales que el
  proceso ejecuta, cuando se valida, entonces no hay errores ni warnings —
  `tests/test_validator.py::test_el_caso_bien_escrito_no_se_marca`
- [ ] Dada una rule con `on_timer.since` que no coincide con ningun evento emitido, cuando se
  valida, entonces hay un warning con `on_timer.since '<evento>'` (`validator.py:278-286`) —
  `(sin test)`
- [ ] Dada una rule que escucha `<entidad>.transitioned`, `<relacion>.transitioned` o
  `relation.<relacion>.created` de un tipo declarado en el archivo, cuando se valida, entonces no
  hay warning de `on_event` (eventos sinteticos, `validator.py:258-264`) — `(sin test)`
- [ ] Dado un step `automated` con `integration: integration.x` no definida, un `human_task` sin
  `signals`, o un `view360` cuya `entity` o `relation` no esta definida, cuando se valida,
  entonces hay un warning por cada caso (`validator.py:129-143`, `validator.py:150-162`) —
  `(sin test)`

### Evaluador de expresiones

- [ ] Dada `edad >= 5 AND edad <= 18`, cuando se evalua con `edad = 10`, entonces da `True`, y con
  `edad = 30` da `False` — `tests/test_evaluator.py::test_comparisons`
- [ ] Dado el contexto `{"x": None}`, cuando se evalua `x == null` da `True`, `x >= 30` da
  `False` y `x >= 30 OR x == null` da `True` — `tests/test_evaluator.py::test_null_handling`
- [ ] Dada `nivel != null WHEN estado == INSCRIPTO`, cuando `estado` no es `INSCRIPTO` da `True`
  aunque `nivel` sea nulo; con `estado = INSCRIPTO` y `nivel` nulo da `False`; con `nivel`
  informado da `True` — `tests/test_evaluator.py::test_when_invariant`
- [ ] Dada `estado in ["COMPLETADA", "ABANDONADA"]`, cuando `estado = "COMPLETADA"` da `True`, y
  `estado in ["COMPLETADA"]` con `estado = "ACTIVA"` da `False` —
  `tests/test_evaluator.py::test_in_operator`
- [ ] Dada la referencia con puntos `event.entity.dispositivo`, cuando el contexto la anida con
  valor nulo, entonces `event.entity.dispositivo == null` da `True` —
  `tests/test_evaluator.py::test_dotted_refs`
- [ ] Dada `days_since(relation.inscripcion.ultimo_acceso) >= 30 OR ... == null`, cuando la fecha
  ISO es de hace 45 dias da `True`, de hace 2 dias da `False`, y nula da `True` —
  `tests/test_evaluator.py::test_days_since`
- [ ] Dado un nombre suelto que no esta en el contexto (`ACTIVA`), cuando se evalua
  `estado == ACTIVA` con `estado = "ACTIVA"`, entonces da `True` (el nombre se toma como literal)
  — `tests/test_evaluator.py::test_bare_name_as_literal`
- [ ] Dada una llamada a una funcion que no es `days_since`, `years_since`, `now`, `len` ni una
  pasada en `funcs`, cuando se evalua, entonces se lanza `EvaluationError`
  `Función desconocida: <nombre>` (`evaluator.py:76`, `evaluator.py:86-88`) — `(sin test)`
- [ ] Dada una comparacion de orden entre tipos incomparables (p.ej. string contra numero), o un
  `in` contra `null`, cuando se evalua, entonces da `False` sin excepcion
  (`evaluator.py:115-118`, `evaluator.py:128-129`) — `(sin test)`
- [ ] Dada una referencia con puntos cuyo camino no existe en el contexto, cuando se evalua,
  entonces resuelve a `None` (`evaluator.py:70`) — `(sin test)`

### Serializacion del AST

- [ ] Dado el `FlowFile` de ceibal, cuando se pasa por `to_jsonable` y `json.dumps`, entonces no
  falla y el texto contiene `"_node": "EntityDef"` — `tests/test_parser.py::test_ast_serializable`
- [ ] Dado un `FlowFile` con duplicados registrados, cuando se serializa, entonces el JSON no
  contiene la clave `duplicates` (`ast_nodes.py:312-314`, `serialize.py:12-13`) — `(sin test)`
- [ ] Dada una `Ref`, cuando se serializa, entonces `parts` sale como lista JSON y el nodo lleva
  `"_node": "Ref"` (`serialize.py:9-10`, `serialize.py:18-19`) — `(sin test)`

### Servicio HTTP `POST /parse`

- [ ] Dada una fuente con error de sintaxis en la linea 3, cuando se hace `POST /parse`, entonces
  responde `200`, `issues[0].block == "syntax"`, `issues[0].line == 3` e `issues[0].column` no es
  nulo — `tests/test_parser.py::test_el_servicio_publica_la_posicion_del_error`
- [ ] Dada una fuente que parsea pero referencia `step.no_existe`, cuando se hace `POST /parse`,
  entonces `valid` es `false`, `issues` no es vacio y todos los issues tienen `line: null` —
  `tests/test_parser.py::test_los_issues_del_validador_no_inventan_posicion`
- [ ] Dada una fuente con error de sintaxis, cuando se hace `POST /parse`, entonces `ast` es
  `null`, `summary` es `{}` y hay un unico issue de nivel `error` (`teleflow/parser_service/main.py:58-65`) — `(sin test)`
- [ ] Dada una fuente valida, cuando se hace `POST /parse`, entonces `valid` es `true`, `ast` trae
  el `FlowFile` serializado y `summary` trae las siete listas ordenadas `entities`, `relations`,
  `rules`, `views`, `processes`, `steps`, `integrations` (`teleflow/parser_service/main.py:67-86`) — `(sin test)` en
  unitarios
- [ ] Dada una fuente que solo produce warnings, cuando se hace `POST /parse`, entonces `valid` es
  `true` y los warnings viajan en `issues` (`teleflow/parser_service/main.py:68`, `teleflow/parser_service/main.py:80-85`) — `(sin test)`
- [ ] Dada cualquier fuente, valida o no, cuando se hace `POST /parse`, entonces `checksum` es el
  SHA-256 hexadecimal del `source` en UTF-8 (`teleflow/parser_service/main.py:55`, `parser.py:171-172`) — `(sin test)`
- [ ] Dado el parser-service levantado, cuando se pide `GET /health`, entonces responde
  `{"status": "ok", "service": "parser-service"}` (`teleflow/parser_service/main.py:19`,
  `teleflow/common/observability.py:46-48`) — `(sin test)` en este modulo

### Ejemplos de referencia

- [ ] Dado `examples/ceibal.tflow`, cuando se parsea, entonces define las entities `nino` y
  `curso`, la relation `inscripcion`, 5 rules, la vista `nino`, 5 procesos, la integration `lms`,
  el catalog `cursos_ceibal` y el party `tutor` — `tests/test_parser.py::test_parse_ceibal_blocks`
- [ ] Dados `examples/ceibal.tflow` y `examples/venta_internet_hogar.tflow`, cuando se validan,
  entonces `validate_flow` devuelve la lista vacia (ni errores ni warnings) —
  `tests/test_validator.py::test_los_ejemplos_del_repositorio_quedan_limpios`,
  `tests/test_parser.py::test_validation_clean`
- [ ] Dado cualquier proceso de los dos ejemplos, cuando el executor arma su DAG de stages,
  entonces el grafo es aciclico; en `asignacion_dispositivo` el orden topologico es
  `verificacion, entrega`, y en `venta_internet_hogar` existen las aristas `decidir -> activacion`
  y `decidir -> rechazo` — `(indirecto)`
  `tests/test_dag.py::test_el_pegote_terminal_sigue_funcionando`,
  `tests/test_dag.py::test_sequential_dag`, `tests/test_dag.py::test_decision_dag`
- [ ] Dado un proceso parseado con una decision de dos ramas escritas una debajo de la otra,
  cuando el executor arma el DAG, entonces hay aristas desde la decision a las dos ramas y no
  entre las ramas hermanas — `(indirecto)` `tests/test_dag.py::test_una_rama_no_cae_en_su_hermana`

## Impacto en lo existente

Esta carpeta no cambia codigo. Lo que depende del modulo, y por lo tanto se rompe si el lenguaje
cambia:

- **Flows ya registrados.** El registro guarda `source` y el executor lo re-parsea al cargar el
  dominio (`executor_service/domain.py:3-4`, `domain.py:94-102`). Un cambio de gramatica que deje
  de aceptar un archivo registrado lo saca del dominio: sus procesos y rules dejan de existir, con
  `teleflow_domain_parse_failures_total` y `teleflow_domain_broken_flows` como unica señal
  (`domain.py:24-34`, `domain.py:78-80`). No hay marcador de version del lenguaje (ver "No entra").
- **Deploy.** El gateway llama a `/parse` antes de persistir y responde `422` si `valid` es `false`
  (`gateway/main.py:613-629`); los warnings se devuelven junto al `201` (`gateway/main.py:650`).
- **Validacion sin persistir.** `POST /parse` del gateway es un proxy que exige `flows:read`
  (`gateway/main.py:655-659`). Tambien lo usan el CLI (`teleflow/cli.py:55`) y el composer para
  validar borradores (`teleflow/composer_service/main.py:120`).
- **Executor.** Invariantes (`executor_service/entities.py:266-293`, con el campo derivado `edad`
  en `entities.py:90-99`), combinacion de dominios (`domain.py:81`) y DAG de stages consumen el AST
  en memoria.
- **Contrato de `POST /parse`.** `ParseResponse` (`parser_service/main.py:44-49`) e `IssueOut`
  con `line`/`column` solo para errores de sintaxis (`teleflow/parser_service/main.py:27-41`). Agregar `catalogs` o
  `parties` al `summary` es un cambio aditivo del contrato.

## Fuentes

- `teleflow/dsl/teleflow.lark:1-213` — gramatica completa; `:206` identificadores ASCII.
- `teleflow/dsl/parser.py:22-35` — `TeleFlowSyntaxError` con `line`, `column`, `expected`.
- `teleflow/dsl/parser.py:114-158` — armado del mensaje de error (token, caracter, fin de archivo).
- `teleflow/dsl/transformer.py:470-492` — `start`: agrupa bloques y registra duplicados.
- `teleflow/dsl/validator.py:46-171` — `validate_flow`; `:199-247` chequeo de firmas;
  `:250-271` universo de eventos; `:274-316` referencias de triggers.
- `teleflow/dsl/validator.py:40-43` — `FlowValidationError` esta definida y exportada
  (`teleflow/dsl/__init__.py:2`), pero ninguna parte del repo la lanza (busqueda de
  `FlowValidationError` en `*.py`).
- `teleflow/dsl/evaluator.py:58-130` — resolucion de refs y comparaciones null-safe.
- `teleflow/dsl/serialize.py:8-20` — `to_jsonable`.
- `teleflow/dsl/ast_nodes.py:297-329` — `FlowFile` y `merge`.
- `teleflow/parser_service/main.py:22-86` — modelos y handler de `POST /parse`.
- `examples/ceibal.tflow`, `examples/venta_internet_hogar.tflow` — flows de referencia.
- `tests/e2e/conftest.py:38-63` — el fixture `deployed` despliega los dos ejemplos por el gateway
  y exige `201`, pero saltea el deploy si el flow ya existe (`tests/e2e/conftest.py:51-52`).
- [[2026-06-30-adr-001-lark-lalr]] — Lark LALR, gramatica como fuente de verdad.
- [[2026-08-27-caida-secuencial-entre-etapas]] — semantica de ramas; retiro del chequeo de derrame.

Discrepancias detectadas al escribir esta linea base (comprobadas, sin corregir):

- `tests/test_dag.py::test_el_pegote_terminal_sigue_funcionando` dice probar flows escritos con el
  `stage` decision terminal (`tests/test_dag.py:103-106`), pero ningun ejemplo lo tiene ya:
  `venta_internet_hogar.tflow:27-42` no declara `stage "fin"` y `ceibal.tflow` no tiene decisiones.
  El test sigue verificando aciclicidad, pero la compatibilidad con el pegote quedo sin cubrir en
  el DAG (el pegote solo aparece en `tests/test_validator.py:233`, que no arma DAG).
- El ADR de caida secuencial cita `examples/reclamo_corte.tflow`
  (`2026-08-27-caida-secuencial-entre-etapas.md:35`, `:187`), que no existe en este commit: en
  `examples/` solo estan `ceibal.tflow` y `venta_internet_hogar.tflow`.
- ADR-001 dice que `transformer.py` concentra errores de `mypy --strict` por metodos sin tipar
  (`2026-06-30-adr-001-lark-lalr.md:32-33`); hoy todos los metodos del transformer estan anotados
  (`transformer.py:47-492`). Que `mypy .` de 0 no se verifico en esta pasada.
