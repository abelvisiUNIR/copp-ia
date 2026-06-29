"""Evaluador de expresiones: semántica null-safe del documento."""
from datetime import datetime, timedelta, timezone

from teleflow.dsl.evaluator import evaluate


def _eval(parser, text, ctx):
    return evaluate(parser.parse_expr(text), ctx)


def test_comparisons(parser):
    assert _eval(parser, "edad >= 5 AND edad <= 18", {"edad": 10}) is True
    assert _eval(parser, "edad >= 5 AND edad <= 18", {"edad": 30}) is False


def test_null_handling(parser):
    ctx = {"x": None}
    assert _eval(parser, "x == null", ctx) is True
    assert _eval(parser, "x >= 30", ctx) is False
    assert _eval(parser, "x >= 30 OR x == null", ctx) is True


def test_when_invariant(parser):
    # "nivel != null WHEN estado == INSCRIPTO"
    expr = 'nivel != null WHEN estado == INSCRIPTO'
    assert _eval(parser, expr, {"nivel": None, "estado": "REGISTRADO"}) is True
    assert _eval(parser, expr, {"nivel": None, "estado": "INSCRIPTO"}) is False
    assert _eval(parser, expr, {"nivel": "primaria", "estado": "INSCRIPTO"}) is True


def test_in_operator(parser):
    assert _eval(parser, 'estado in ["COMPLETADA", "ABANDONADA"]',
                 {"estado": "COMPLETADA"}) is True
    assert _eval(parser, 'estado in ["COMPLETADA"]', {"estado": "ACTIVA"}) is False


def test_dotted_refs(parser):
    ctx = {"event": {"entity": {"dispositivo": None}}}
    assert _eval(parser, "event.entity.dispositivo == null", ctx) is True


def test_days_since(parser):
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    ctx = {"relation": {"inscripcion": {"ultimo_acceso": old}}}
    expr = ("days_since(relation.inscripcion.ultimo_acceso) >= 30 "
            "OR relation.inscripcion.ultimo_acceso == null")
    assert _eval(parser, expr, ctx) is True

    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    ctx2 = {"relation": {"inscripcion": {"ultimo_acceso": recent}}}
    assert _eval(parser, expr, ctx2) is False

    ctx3 = {"relation": {"inscripcion": {"ultimo_acceso": None}}}
    assert _eval(parser, expr, ctx3) is True


def test_bare_name_as_literal(parser):
    # estados/enums sin comillas se interpretan como literal string
    assert _eval(parser, "estado == ACTIVA", {"estado": "ACTIVA"}) is True
