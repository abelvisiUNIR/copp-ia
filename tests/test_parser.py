"""Tests del parser DSL v2 contra los ejemplos del documento de arquitectura."""
import pytest

from teleflow.dsl.parser import TeleFlowSyntaxError
from teleflow.dsl.serialize import to_jsonable
from teleflow.dsl.validator import validate_flow


def test_parse_ceibal_blocks(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    assert set(flow.entities) == {"nino", "curso"}
    assert set(flow.relations) == {"inscripcion"}
    assert len(flow.rules) == 5
    assert "nino" in flow.views
    assert len(flow.processes) == 5
    assert "lms" in flow.integrations
    assert "cursos_ceibal" in flow.catalogs
    assert "tutor" in flow.parties


def test_entity_nino_lifecycle(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    nino = flow.entities["nino"]
    assert nino.lifecycle.initial == "REGISTRADO"
    assert set(nino.lifecycle.states) == {
        "REGISTRADO", "ACTIVO", "INSCRIPTO", "GRADUADO", "INACTIVO"}
    vias = {t.via for t in nino.lifecycle.transitions}
    assert {"activar", "inscribir", "graduar"} <= vias
    assert len(nino.invariants) == 2
    emits = {e.emit for e in nino.events}
    assert "nino.inscripto" in emits


def test_entity_fields(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    fields = flow.entities["nino"].field_map()
    assert fields["ci"].required and fields["ci"].unique
    assert fields["nivel"].type == "enum"
    assert fields["nivel"].enum_values == ["primaria", "secundaria", "utu"]
    assert fields["dispositivo"].optional

    progreso = flow.relations["inscripcion"].fields[2]
    assert progreso.name == "progreso"
    assert progreso.has_default and progreso.default == 0
    assert progreso.range == (0.0, 100.0)


def test_relation_refs(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    rel = flow.relations["inscripcion"]
    assert rel.from_ref.dotted == "entity.nino"
    assert rel.to_ref.dotted == "entity.curso"
    assert rel.cardinality == "many_to_many"


def test_timer_rule(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    rule = flow.rules["detectar_abandono"]
    assert rule.timer is not None
    assert rule.timer.after_seconds == 30 * 86400
    assert rule.timer.since == "inscripcion.activada"
    assert rule.execute.dotted == "process.reenganche_estudiante"
    assert set(rule.with_map) == {"nino_id", "curso_id"}


def test_view360(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    view = flow.views["nino"]
    assert view.entity.dotted == "entity.nino"
    assert len(view.relations) == 2
    activas = view.relations[0]
    assert activas.alias == "inscripciones_activas"
    assert activas.where is not None
    assert [r.dotted for r in activas.include] == [
        "curso.nombre", "progreso", "ultimo_acceso"]
    assert view.timeline.limit == 50
    assert len(view.alerts) == 2
    assert len(view.active_processes.include) == 4


def test_validation_clean(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    issues = validate_flow(flow)
    errors = [i for i in issues if i.level == "error"]
    assert errors == []


def test_venta_decision_stages(parser, venta_source):
    flow = parser.parse(venta_source)
    proc = flow.processes["venta_internet_hogar"]
    # Sin `fin_ok`: era un stage decision de `else -> stage.end` puesto para que la rama buena
    # no siguiera de largo hacia la de rechazo. Desde que las ramas de una decisión no se
    # derraman una en otra, ese cierre no hace falta y el archivo dice lo que hace.
    assert [s.name for s in proc.stages] == [
        "validacion", "aprobacion", "decidir", "activacion", "rechazo"]
    decidir = proc.stages[2]
    assert decidir.mode == "decision"
    assert len(decidir.branches) == 2
    assert decidir.branches[0].target.target == "activacion"
    assert decidir.branches[1].condition is None  # else
    human = flow.steps["aprobacion_gerencia"]
    assert human.type == "human_task"
    assert human.signals == ["approve", "reject"]
    assert human.timeout_seconds == 7 * 86400
    issues = validate_flow(flow)
    assert [i for i in issues if i.level == "error"] == []


def test_syntax_error_reports_line(parser):
    with pytest.raises(TeleFlowSyntaxError) as exc:
        parser.parse('entity "x" { lifecycle { ??? } }')
    assert exc.value.line is not None


def test_unexpected_char_message(parser):
    with pytest.raises(TeleFlowSyntaxError) as exc:
        parser.parse('entity "x" { lifecycle { ??? } }')
    msg = exc.value.message
    assert "carácter inesperado '?'" in msg
    assert exc.value.column is not None


def test_unexpected_token_lists_expected(parser):
    # `on_state:` sin el STRING que exige la gramática.
    with pytest.raises(TeleFlowSyntaxError) as exc:
        parser.parse('rule "r" { on_state: }')
    assert "se esperaba" in exc.value.message
    # el terminal aceptado se expone para tooling
    assert "STRING" in exc.value.expected


def test_unexpected_eof_message(parser):
    with pytest.raises(TeleFlowSyntaxError) as exc:
        parser.parse('entity "x" ')
    msg = exc.value.message
    assert "fin de archivo inesperado" in msg
    assert "'{'" in msg  # se esperaba abrir el bloque


def test_parse_expr_gives_context(parser):
    # parse_expr antes tiraba el contexto; ahora reporta línea/columna y pista.
    with pytest.raises(TeleFlowSyntaxError) as exc:
        parser.parse_expr("1 + ")
    assert exc.value.line is not None
    assert exc.value.column is not None
    assert "Expresión inválida" in exc.value.message
    assert "se esperaba" in exc.value.message


def test_ast_serializable(parser, ceibal_source):
    import json

    flow = parser.parse(ceibal_source)
    data = to_jsonable(flow)
    text = json.dumps(data)
    assert '"_node": "EntityDef"' in text


# Las unidades de tiempo aceptan singular y plural. La gramática solo tenía plural, así que
# `timeout: 1 day` fallaba con un error de sintaxis por una letra — y es la forma natural de
# escribirlo en castellano y en inglés. Apareció en un borrador del composer: el archivo entero
# parseaba salvo esa línea.
@pytest.mark.parametrize("unidad,segundos", [
    ("1 second", 1), ("1 seconds", 1),
    ("1 minute", 60), ("2 minutes", 120),
    ("1 hour", 3600), ("2 hours", 7200),
    ("1 day", 86400), ("3 days", 259200),
    ("1 week", 604800), ("2 weeks", 1209600),
])
def test_las_unidades_de_tiempo_aceptan_singular_y_plural(parser, unidad, segundos):
    src = f'''
    process "p" {{
      input {{ a: string required }}
      stage "s" {{ mode: sequential steps [step.uno] }}
    }}
    step "uno" {{ type: human_task signals ["approve"] timeout: {unidad} }}
    '''
    assert parser.parse(src).steps["uno"].timeout_seconds == segundos


# ------------------------------------------- dónde está el error, como dato
#
# `TeleFlowSyntaxError` siempre llevó `line` y `column`, pero el parser-service los aplastaba
# dentro del texto del mensaje. Del otro lado, la pantalla de revisión mostraba "línea 43,
# columna 62" y no podía llevar al revisor hasta ahí: había que contar a mano. Estos tests
# fijan que la posición viaje como dato hasta el borde del servicio.

# Un identificador con tilde: falla exactamente en el carácter, así que la posición reportada
# se puede afirmar sin ambigüedad. Con un error que el lexer arrastra —`requiredd` se lexa como
# un identificador válido y recién explota en el `}` de la línea siguiente— el test estaría
# fijando dónde se *descubre* el error, no dónde está.
FUENTE_CON_ERROR_EN_LA_LINEA_3 = (
    'process "p" {\n'
    '  input { a: string required }\n'
    '  stage "s" { mode: sequential steps [step.notificación] }\n'
    '}\n'
)


def test_el_error_de_sintaxis_lleva_linea_y_columna():
    from teleflow.dsl.parser import get_parser

    with pytest.raises(TeleFlowSyntaxError) as exc:
        get_parser().parse(FUENTE_CON_ERROR_EN_LA_LINEA_3)

    assert exc.value.line == 3
    assert exc.value.column is not None


def test_el_mensaje_incluye_el_fragmento_con_el_apuntador():
    """El `^` señala la columna exacta. Sirve solo si sobrevive con sus saltos de línea:
    renderizado como texto corrido queda flotando al final y no apunta a nada."""
    from teleflow.dsl.parser import get_parser

    with pytest.raises(TeleFlowSyntaxError) as exc:
        get_parser().parse('entity "x" {\n  fields {\n    a: string requiredd\n  }\n}\n')

    lineas = exc.value.message.split("\n")
    assert len(lineas) > 1, "el mensaje tiene que traer el fragmento del código, no solo texto"
    assert any("^" in l for l in lineas[1:])


def test_el_servicio_publica_la_posicion_del_error():
    """Que la excepción los traiga no sirve si el servicio no los expone: es donde se perdían."""
    from fastapi.testclient import TestClient

    from teleflow.parser_service.main import app

    with TestClient(app) as client:
        r = client.post("/parse", json={
            "source": FUENTE_CON_ERROR_EN_LA_LINEA_3, "name": "x",
        })

    assert r.status_code == 200
    issue = r.json()["issues"][0]
    assert issue["block"] == "syntax"
    assert issue["line"] == 3
    assert issue["column"] is not None


def test_los_issues_del_validador_no_inventan_posicion():
    """Un error del validador habla de un bloque entero, no de una posición en el archivo.
    Devolver una línea cualquiera mandaría al revisor a un lugar que no tiene nada que ver."""
    from fastapi.testclient import TestClient

    from teleflow.parser_service.main import app

    with TestClient(app) as client:
        r = client.post("/parse", json={
            "source": (
                'process "p" {\n'
                '  input { a: string required }\n'
                '  stage "s" { mode: sequential steps [step.no_existe] }\n'
                '}\n'
            ),
            "name": "x",
        })

    cuerpo = r.json()
    assert cuerpo["valid"] is False
    assert cuerpo["issues"], "el validador tenía que quejarse del step inexistente"
    assert all(i["line"] is None for i in cuerpo["issues"])


def test_un_identificador_con_tilde_no_parsea():
    """`notificación` es lo natural de escribir en castellano y el lenguaje no lo acepta: los
    identificadores son ASCII, el texto entre comillas no. La regla está en el prompt del
    composer; este test fija el comportamiento que ese prompt describe."""
    from teleflow.dsl.parser import get_parser

    with pytest.raises(TeleFlowSyntaxError) as exc:
        get_parser().parse(
            'process "p" {\n'
            '  input { a: string required }\n'
            '  stage "s" { mode: sequential steps [step.notificación] }\n'
            '}\n'
        )

    assert "ó" in exc.value.message
    assert exc.value.line == 3
