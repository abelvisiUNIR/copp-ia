---
project: copp-ia
type: tasks
status: implementada
feature: base-lenguaje-tflow
provenance: copp-ia@devyos@5e64479
created: 2026-09-14
---

# Desglose de tareas — Linea base del lenguaje `.tflow`

<!--
  status: implementada = linea base as-built (carpeta base-*): no se sincroniza nunca con Jira.
  Lo escribe el subagente `desglosador-tareas` (modo as-built).

  Cada `- [x]` es una capacidad que el codigo ya tiene, con su evidencia:
  cita al codigo (ruta desde la raiz del repo) · test que la prueba, o `(sin test)`.
  El estado de test sale de `validacion.md`: lo que alli es SIN TEST aca no lleva test.
  `#NN` = numero del criterio en la matriz de `validacion.md`.
  `(indirecto)` = lo prueba un test de otro modulo que consume el DSL.
-->

## Gramatica y parseo

- [x] Que entity, relation, rule con timer y view360 bajen al AST con campos, lifecycle, eventos y referencias — `teleflow/dsl/teleflow.lark:20-111`, `teleflow/dsl/transformer.py:150-318` · `tests/test_parser.py::test_entity_nino_lifecycle`, `tests/test_parser.py::test_entity_fields`, `tests/test_parser.py::test_relation_refs`, `tests/test_parser.py::test_timer_rule`, `tests/test_parser.py::test_view360`
  - lifecycle de `entity "nino"`: inicial, estados, transiciones `via`, invariantes y `emit` (#1)
  - modificadores de campo `required`, `unique`, `enum`, `optional`, `default` y `range` (#2, `teleflow/dsl/transformer.py:153-180`)
  - `from`/`to` y `cardinality` de relation (#3)
  - rule `on_timer` con `after`, `since`, `execute` y `with` (#4, `teleflow/dsl/transformer.py:250-260`)
  - view360 con relaciones, `where`, `include`, timeline, alerts y procesos activos (#5)
- [x] Que los procesos bajen al AST con stages en orden, ramas when/else y steps con senales y timeout — `teleflow/dsl/teleflow.lark:114-152`, `teleflow/dsl/transformer.py:320-420` · `tests/test_parser.py::test_venta_decision_stages`
  - stages de `venta_internet_hogar`, decision con dos branches y `human_task` con `signals` y `timeout` (#6)
- [x] Que las duraciones acepten singular y plural y se conviertan a segundos — `teleflow/dsl/teleflow.lark:82-91`, `teleflow/dsl/transformer.py:116-132` · `tests/test_parser.py::test_las_unidades_de_tiempo_aceptan_singular_y_plural`
  - 10 casos parametrizados: second(s), minute(s), hour(s), day(s), week(s) (#7)
- [x] Que un identificador con tilde sea error de sintaxis con su linea — `teleflow/dsl/teleflow.lark:206` · `tests/test_parser.py::test_un_identificador_con_tilde_no_parsea`
  - `step.notificación` en la linea 3 da `TeleFlowSyntaxError` con `line == 3` (#8)
- [x] Que los comentarios `//` se ignoren al parsear — `teleflow/dsl/teleflow.lark:210-213` · `tests/test_parser.py::test_parse_ceibal_blocks`
  - cubierto porque `examples/ceibal.tflow:1-5` usa `//` y el test parsea ese archivo (#10, parte `//`)
- [x] Que los comentarios `#`, la fuente vacia y los productos de catalogo parseen segun la gramatica — `teleflow/dsl/teleflow.lark:7`, `teleflow/dsl/teleflow.lark:160-167`, `teleflow/dsl/teleflow.lark:210`, `teleflow/dsl/transformer.py:436-440` · (sin test)
  - comentario `#` ignorado (#10, parte `#`)
  - fuente vacia → `FlowFile` con todas las categorias vacias y `validate_flow` devuelve `[]` (#11)
  - `product` con `price` como float y `currency` como string (#12)

## Errores de sintaxis

- [x] Que un error de sintaxis se reporte en castellano con linea, columna, esperados y fragmento con apuntador — `teleflow/dsl/parser.py:22-35`, `teleflow/dsl/parser.py:66-81`, `teleflow/dsl/parser.py:100-158` · `tests/test_parser.py::test_syntax_error_reports_line`, `tests/test_parser.py::test_unexpected_char_message`, `tests/test_parser.py::test_unexpected_token_lists_expected`, `tests/test_parser.py::test_unexpected_eof_message`, `tests/test_parser.py::test_parse_expr_gives_context`, `tests/test_parser.py::test_el_error_de_sintaxis_lleva_linea_y_columna`, `tests/test_parser.py::test_el_mensaje_incluye_el_fragmento_con_el_apuntador`
  - caracter inesperado (#13, `teleflow/dsl/parser.py:137-142`)
  - token inesperado con los terminales esperados en `exc.expected` (#14, `teleflow/dsl/parser.py:124-136`)
  - fin de archivo inesperado (#15, `teleflow/dsl/parser.py:127-131`)
  - expresion suelta invalida en `parse_expr` (#16, `teleflow/dsl/parser.py:75-79`)
  - linea y columna como dato de la excepcion (#17, `teleflow/dsl/parser.py:117-118`, `teleflow/dsl/parser.py:156-157`)
  - fragmento de la fuente con apuntador `^` (#18, `teleflow/dsl/parser.py:119-122`, `teleflow/dsl/parser.py:154-155`)
- [x] Que la lista de esperados se corte en 8 descripciones seguidas de `, …` — `teleflow/dsl/parser.py:110-112` · (sin test)
  - mas de 8 terminales esperados (#19)

## Validacion semantica — errores (bloquean el registro)

- [x] Que el validador bloquee lifecycles incoherentes y on_transition de entity sin transicion — `teleflow/dsl/validator.py:319-348` · `tests/test_validator.py::test_invalid_transition_state`, `tests/test_validator.py::test_initial_not_in_states`, `tests/test_validator.py::test_event_without_transition`
  - transicion a un estado no declarado (#20)
  - estado inicial fuera de `states` (#21)
  - `on_transition` sin ninguna transicion `via` con ese nombre (#22)
- [x] Que una rule con cero o mas de un trigger quede bloqueada — `teleflow/dsl/validator.py:65-74` · `tests/test_validator.py::test_rule_needs_exactly_one_trigger`
  - `on_event` y `on_state` a la vez (#23)
- [x] Que un proceso con steps inexistentes o human_task en stage parallel quede bloqueado, aceptando `stage.end` — `teleflow/dsl/validator.py:95-110`, `teleflow/dsl/validator.py:117-120` · `tests/test_validator.py::test_process_references_unknown_step`, `tests/test_validator.py::test_human_task_forbidden_in_parallel`, `tests/test_validator.py::test_branch_to_end_is_valid`
  - `steps [step.inexistente]` (#24)
  - `human_task` dentro de un stage `parallel` (#25)
  - `else -> stage.end` es destino terminal valido (#26)
- [x] Que un nombre declarado dos veces en el mismo archivo se registre al parsear y bloquee el registro — `teleflow/dsl/transformer.py:487-491`, `teleflow/dsl/validator.py:49-54` · `tests/test_validator.py::test_duplicate_entity_is_error`, `tests/test_validator.py::test_duplicate_step_is_error`
  - el parseo no lanza y el par `(categoria, nombre)` queda en `FlowFile.duplicates` (#9)
  - el validador lo reporta como error con `definido más de una vez en el mismo archivo` (#27)
- [x] Que una decision que espera la firma de un step inexistente o automated quede bloqueada — `teleflow/dsl/validator.py:199-233` · `tests/test_validator.py::test_una_decision_que_espera_una_firma_de_un_paso_automatico`, `tests/test_validator.py::test_una_decision_que_espera_una_firma_inexistente`
  - firma de un step `automated` (#28)
  - firma de un step que no existe en el archivo (#29)
- [x] Que el validador bloquee procesos, stages, steps y rules mal formados — `teleflow/dsl/validator.py:76-147`, `teleflow/dsl/validator.py:223-224` · (sin test)
  - firma de un `human_task` que el proceso no ejecuta (#30, `teleflow/dsl/validator.py:223-224`)
  - `process` sin stages (#31, `teleflow/dsl/validator.py:92-94`)
  - stage `decision` sin branches (#32, `teleflow/dsl/validator.py:111-116`)
  - branch a un stage inexistente distinto de `end` (#33, `teleflow/dsl/validator.py:117-126`)
  - step `notification` sin `channel` (#34, `teleflow/dsl/validator.py:144-147`)
  - rule sin `execute` (#35, `teleflow/dsl/validator.py:76-78`)
- [x] Que el validador bloquee relations sin from/to validos, eventos sobre nombres inexistentes e invariantes que no parsean — `teleflow/dsl/validator.py:349-395` · (sin test)
  - relation sin `from`/`to` o que no referencia `entity.<nombre>` (#36, `teleflow/dsl/validator.py:375-380`)
  - `on_field_change` sobre algo que no es campo (entity y relation) y `on_transition` de relation sin transicion (#37, `teleflow/dsl/validator.py:349-354`, `teleflow/dsl/validator.py:388-395`)
  - invariante no parseable como error del validador (#38, parte validador, `teleflow/dsl/validator.py:357-369`)
- [x] Que un invariante con typo quede expuesto en metrica sin bloquear la transicion en el executor — `teleflow/executor_service/entities.py:273-281` · `tests/test_error_handling.py::test_invariante_con_typo_queda_expuesto` (indirecto)
  - `teleflow_invariants_skipped_total{reason="unparseable"}` sube exactamente 1 (#38, parte executor)

## Validacion semantica — warnings (se informan, no bloquean)

- [x] Que los triggers de rule con eventos, relations o estados desconocidos avisen sin bloquear — `teleflow/dsl/validator.py:274-316` · `tests/test_validator.py::test_rule_on_event_unknown_warns`, `tests/test_validator.py::test_rule_on_event_known_is_clean`, `tests/test_validator.py::test_rule_on_relation_unknown_warns`, `tests/test_validator.py::test_rule_on_state_bad_state_warns`, `tests/test_validator.py::test_rule_on_state_malformed_warns`
  - `on_event` desconocido avisa; el que coincide con un `emit` no (#39, #40)
  - `on_relation` sin relation con ese nombre (#41)
  - `on_state` con estado fuera del lifecycle o sin punto (#42, #43)
- [x] Que una referencia a process, rule o entity fuera del archivo avise aunque la categoria este vacia — `teleflow/dsl/validator.py:79-87`, `teleflow/dsl/validator.py:163-169`, `teleflow/dsl/validator.py:381-384` · `tests/test_validator.py::test_rule_a_process_inexistente_avisa_aunque_el_flow_no_tenga_procesos`, `tests/test_validator.py::test_view360_alerta_a_rule_inexistente_avisa_sin_rules_en_el_archivo`, `tests/test_validator.py::test_relation_a_entity_inexistente_avisa_sin_entities_en_el_archivo`, `tests/test_validator.py::test_ref_valida_en_el_mismo_archivo_no_avisa`
  - `execute: process.fantasma` sin procesos (#44)
  - alert a `rule.no_existe` sin rules (#45)
  - relation a `entity.fantasma` sin entities (#46)
  - referencias correctas en el mismo archivo no avisan (#47)
- [x] Que un human_task de varias senales que ninguna decision lee avise, y el de una sola senal no — `teleflow/dsl/validator.py:235-247` · `tests/test_validator.py::test_una_firma_que_nadie_lee_avisa`, `tests/test_validator.py::test_una_firma_de_una_sola_senal_no_avisa`, `tests/test_validator.py::test_el_caso_bien_escrito_no_se_marca`
  - dos senales sin lector: 1 warning y ningun error (#48)
  - una sola senal: sin warnings (#49)
  - decision que lee la firma de un human_task que el proceso ejecuta: limpio (#50)
- [x] Que el validador avise por timers, integraciones, senales y vistas colgadas y acepte los eventos sinteticos — `teleflow/dsl/validator.py:129-162`, `teleflow/dsl/validator.py:250-286` · (sin test)
  - `on_timer.since` que no coincide con ningun evento emitido (#51, `teleflow/dsl/validator.py:278-286`)
  - `<tipo>.transitioned` y `relation.<tipo>.created` no avisan (#52, `teleflow/dsl/validator.py:258-264`)
  - step `automated` con integration no definida, `human_task` sin `signals`, view360 con entity o relation no definida (#53, `teleflow/dsl/validator.py:129-143`, `teleflow/dsl/validator.py:150-162`)

## Evaluador de expresiones

- [x] Que las expresiones se evaluen null-safe con comparaciones, AND/OR, WHEN, `in` y refs con puntos — `teleflow/dsl/evaluator.py:58-130` · `tests/test_evaluator.py::test_comparisons`, `tests/test_evaluator.py::test_null_handling`, `tests/test_evaluator.py::test_when_invariant`, `tests/test_evaluator.py::test_in_operator`, `tests/test_evaluator.py::test_dotted_refs`
  - comparaciones con `AND` (#54)
  - `== null` y orden contra `None` da `False` (#55)
  - invariante condicional `WHEN` (#56)
  - `in` contra lista (#57)
  - ref con puntos anidada con valor nulo (#58)
- [x] Que `days_since` mida dias desde una fecha ISO y devuelva nulo ante una fecha nula — `teleflow/dsl/evaluator.py:22-42`, `teleflow/dsl/evaluator.py:50-55` · `tests/test_evaluator.py::test_days_since`
  - hace 45 dias, hace 2 dias y nula (#59)
- [x] Que un nombre suelto ausente del contexto se evalue como literal string — `teleflow/dsl/evaluator.py:68-69` · `tests/test_evaluator.py::test_bare_name_as_literal`
  - `estado == ACTIVA` con `estado = "ACTIVA"` da `True` (#60)
- [x] Que el evaluador rechace funciones fuera de la lista blanca y no lance ante tipos incomparables o caminos inexistentes — `teleflow/dsl/evaluator.py:50-130` · (sin test)
  - funcion desconocida → `EvaluationError` `Función desconocida: <nombre>` (#61, `teleflow/dsl/evaluator.py:76`, `teleflow/dsl/evaluator.py:86-88`)
  - orden entre tipos incomparables o `in` contra `null` → `False` (#62, `teleflow/dsl/evaluator.py:115-118`, `teleflow/dsl/evaluator.py:128-129`)
  - ref con puntos a un camino inexistente → `None` (#63, `teleflow/dsl/evaluator.py:70`)

## Serializacion del AST

- [x] Que el AST se serialice a JSON con el tipo de cada nodo en `_node` — `teleflow/dsl/serialize.py:8-20` · `tests/test_parser.py::test_ast_serializable`
  - `FlowFile` de ceibal pasa por `json.dumps` y contiene `"_node": "EntityDef"` (#64)
- [x] Que el JSON omita `duplicates` y serialice las Ref con `parts` como lista — `teleflow/dsl/ast_nodes.py:312-314`, `teleflow/dsl/serialize.py:8-20` · (sin test)
  - campo `transient` omitido (#65, `teleflow/dsl/serialize.py:12-13`)
  - `Ref` con `"_node": "Ref"` y `parts` como lista (#66, `teleflow/dsl/serialize.py:9-10`, `teleflow/dsl/serialize.py:18-19`)

## Servicio HTTP `POST /parse`

- [x] Que `POST /parse` devuelva la linea y columna de un error de sintaxis como dato — `teleflow/parser_service/main.py:56-65` · `tests/test_parser.py::test_el_servicio_publica_la_posicion_del_error`
  - `200`, `issues[0].block == "syntax"`, `line == 3` y `column` no nulo (#67)
- [x] Que `POST /parse` marque invalido un flow con errores semanticos sin inventar posicion — `teleflow/parser_service/main.py:67-68`, `teleflow/parser_service/main.py:80-85` · `tests/test_parser.py::test_los_issues_del_validador_no_inventan_posicion`
  - `valid: false` y todos los issues con `line: null` (#68)
- [x] Que `POST /parse` responda ast, summary, checksum y warnings segun el resultado del parseo — `teleflow/parser_service/main.py:52-86`, `teleflow/dsl/parser.py:171-172` · (sin test)
  - error de sintaxis: `ast` nulo, `summary` vacio y un unico issue `error` (#69, `teleflow/parser_service/main.py:58-65`)
  - fuente valida: `valid: true`, `ast` serializado y las siete listas del `summary` (#70, `teleflow/parser_service/main.py:67-86`)
  - solo warnings: `valid: true` y warnings en `issues` (#71, `teleflow/parser_service/main.py:68`, `teleflow/parser_service/main.py:80-85`)
  - `checksum` = SHA-256 hex del `source` en UTF-8 (#72, `teleflow/parser_service/main.py:55`, `teleflow/dsl/parser.py:171-172`)
- [x] Que el parser-service responda `GET /health` con su nombre de servicio — `teleflow/parser_service/main.py:19`, `teleflow/common/observability.py:46-48` · (sin test)
  - `{"status": "ok", "service": "parser-service"}` (#73)

## Ejemplos de referencia

- [x] Que `examples/ceibal.tflow` declare entities, relation, rules, vista, procesos, integration, catalog y party — `examples/ceibal.tflow:7-412` · `tests/test_parser.py::test_parse_ceibal_blocks`
  - `nino`, `curso`, `inscripcion`, 5 rules, vista `nino`, 5 procesos, `lms`, `cursos_ceibal`, `tutor` (#74)
- [x] Que los dos ejemplos del repositorio validen sin errores ni warnings — `examples/ceibal.tflow:7-412`, `examples/venta_internet_hogar.tflow:8-88`, `teleflow/dsl/validator.py:46-171` · `tests/test_validator.py::test_los_ejemplos_del_repositorio_quedan_limpios`, `tests/test_parser.py::test_validation_clean`
  - `validate_flow` devuelve `[]` para los dos (#75)
- [x] Que los procesos parseados armen en el executor un DAG aciclico sin aristas entre ramas hermanas — `teleflow/executor_service/engine.py:118-136` · `tests/test_dag.py::test_el_pegote_terminal_sigue_funcionando`, `tests/test_dag.py::test_sequential_dag`, `tests/test_dag.py::test_decision_dag`, `tests/test_dag.py::test_una_rama_no_cae_en_su_hermana` (indirecto)
  - aciclicidad de todos los procesos de ambos ejemplos, orden de `asignacion_dispositivo` y aristas de `decidir` (#76)
  - decision con dos ramas escritas una debajo de la otra: sin arista entre hermanas (#77)

## Pendientes observados

<!--
  Huecos conocidos, no tareas comprometidas. No se sincronizan: esta carpeta es linea base.
  Las referencias `spec.md`, `plan.md`, `validacion.md` y `seguridad.md` son los archivos de esta
  misma carpeta (`spec/features/base-lenguaje-tflow/`). El detalle y la evidencia en codigo estan
  alla; aca solo se consolidan sin duplicar.
-->

### Seguridad (de `seguridad.md`, de mayor a menor severidad)

- [ ] Que `${env.*}` en integraciones solo resuelva un prefijo dedicado y el validador lo verifique (severidad alta) (no sincronizar: linea base) — `seguridad.md:89`, `seguridad.md:125-129`, `plan.md:183`
- [ ] Que la fuente de `/parse` y del deploy tenga un tamaño maximo (severidad media) (no sincronizar: linea base) — `seguridad.md:90`, `spec.md:86-91`, `plan.md:185`
- [ ] Que un parseo grande no bloquee el event loop ni las probes del parser-service (severidad media) (no sincronizar: linea base) — `seguridad.md:91`
- [ ] Que una expresion anidada muy profunda se rechace como error y no termine en 500 (severidad media) (no sincronizar: linea base) — `seguridad.md:92`, `plan.md:185`
- [ ] Que el parser-service no sea alcanzable sin control desde la red interna (severidad media) (no sincronizar: linea base) — `seguridad.md:93`
- [ ] Que el token inesperado se trunque en el mensaje de error y en el log (severidad media) (no sincronizar: linea base) — `seguridad.md:94`
- [ ] Que el contenedor corra sin root y el parser-service no reciba credenciales que no usa (severidad media) (no sincronizar: linea base) — `seguridad.md:95`
- [ ] Que el fragmento de fuente del mensaje de sintaxis no lleve literales sensibles al log (severidad baja) (no sincronizar: linea base) — `seguridad.md:96`
- [ ] Que las refs de una expresion no recorran atributos internos de objetos que no son Mapping (severidad baja) (no sincronizar: linea base) — `seguridad.md:97`
- [ ] Que ampliar la lista blanca de funciones del evaluador quede controlado (severidad baja) (no sincronizar: linea base) — `seguridad.md:98`
- [ ] Que numeros gigantes y duraciones o enteros negativos se rechacen al validar (severidad baja) (no sincronizar: linea base) — `seguridad.md:99`, `plan.md:177`
- [ ] Que `/docs` y `/openapi.json` del parser-service no queden expuestos (severidad baja) (no sincronizar: linea base) — `seguridad.md:100`
- [ ] Que la imagen del chart se referencie por digest y no por tag (severidad baja) (no sincronizar: linea base) — `seguridad.md:101`

### Lenguaje y validacion (de `spec.md` "No entra" y `plan.md` "Riesgos")

- [ ] Que `catalog` y `party` se validen, tengan consumidor o salgan del lenguaje (no sincronizar: linea base) — `spec.md:73-80`, `plan.md:189`
- [ ] Que el `summary` de `POST /parse` incluya catalogos y actores (no sincronizar: linea base) — `spec.md:81-85`
- [ ] Que las referencias dentro de expresiones se contrasten con los campos declarados (no sincronizar: linea base) — `spec.md:98-104`, `plan.md:186`
- [ ] Que una funcion fuera de la lista blanca se detecte al validar y no recien en runtime (no sincronizar: linea base) — `plan.md:176`
- [ ] Que `in` contra un numero no lance y contra un string no haga busqueda de subcadena (no sincronizar: linea base) — `plan.md:175`, `validacion.md:256-260`
- [ ] Que se verifique el prefijo de las referencias en steps, branches, alerts y execute (no sincronizar: linea base) — `spec.md:105-108`
- [ ] Que un nombre repetido entre archivos del dominio se detecte al combinarlos (no sincronizar: linea base) — `spec.md:109-112`, `plan.md:187`
- [ ] Que se valide la coherencia de campos, las claves de integration y los steps decision (no sincronizar: linea base) — `spec.md:113-117`
- [ ] Que el `.tflow` y el registro lleven marcador de version del lenguaje (no sincronizar: linea base) — `spec.md:118-120`, `plan.md:169`, `plan.md:184`
- [ ] Que el AST persistido no describa algo distinto de lo que ejecuta el executor (no sincronizar: linea base) — `spec.md:121-122`, `plan.md:170`
- [ ] Que la regla de identificadores solo ASCII quede decidida en un ADR (no sincronizar: linea base) — `spec.md:92-97`, `plan.md:182`
- [ ] Que se decida si las expresiones admiten aritmetica (no sincronizar: linea base) — `spec.md:123-125`
- [ ] Que `FlowValidationError` se use o salga de la superficie publica del DSL (no sincronizar: linea base) — `spec.md:426-428`, `plan.md:178`

### Operacion (de `plan.md` "Riesgos")

- [ ] Que un flow registrado que deja de parsear o un invariante salteado disparen una alerta (no sincronizar: linea base) — `plan.md:173`
- [ ] Que un upgrade rolling no saque flows del dominio por desfase de gramatica entre pods (no sincronizar: linea base) — `plan.md:172`, `plan.md:188`
- [ ] Que las replicas del executor no vean dominios distintos tras un deploy (no sincronizar: linea base) — `plan.md:171`
- [ ] Que el e2e re-verifique los ejemplos aunque el stack ya los tenga registrados (no sincronizar: linea base) — `plan.md:174`

### Tests faltantes (de `validacion.md`: 26 SIN TEST y alcance de asserts)

- [ ] Que tengan test los casos borde de parseo y el corte de esperados (#10 `#`, #11, #12, #19) (no sincronizar: linea base) — `validacion.md:192-195`
- [ ] Que tengan test los nueve errores del validador sin cobertura (#30 a #38) (no sincronizar: linea base) — `validacion.md:196-204`, `validacion.md:219-221`
- [ ] Que tengan test los warnings de timer, eventos sinteticos, integraciones, senales y vistas (#51 a #53) (no sincronizar: linea base) — `validacion.md:205-207`
- [ ] Que tengan test la funcion desconocida, los tipos incomparables y los caminos inexistentes (#61 a #63) (no sincronizar: linea base) — `validacion.md:208-210`
- [ ] Que tenga test la serializacion sin `duplicates` y la de las Ref (#65, #66) (no sincronizar: linea base) — `validacion.md:211-212`
- [ ] Que tengan test la respuesta completa de `POST /parse` y el `/health` del parser-service (#69 a #73) (no sincronizar: linea base) — `validacion.md:213-217`
- [ ] Que los tests de duplicados afirmen el mensaje literal y el bloque exacto (no sincronizar: linea base) — `validacion.md:241-250`
- [ ] Que el DAG vuelva a cubrir un flow con el stage decision terminal (no sincronizar: linea base) — `spec.md:441-445`, `validacion.md:251-255`

### Documentacion

- [ ] Que los ADR de caida secuencial y ADR-001 no citen un ejemplo inexistente ni un conteo de mypy viejo (no sincronizar: linea base) — `spec.md:446-451`, `plan.md:60-63`
