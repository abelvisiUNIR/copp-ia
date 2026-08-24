"""Validación semántica: errores que el parser-service debe bloquear."""
from teleflow.dsl.validator import validate_flow


def _errors(parser, source):
    flow = parser.parse(source)
    return [i for i in validate_flow(flow) if i.level == "error"]


def test_invalid_transition_state(parser):
    source = '''
    entity "x" {
      lifecycle {
        initial: "A"
        states ["A", "B"]
        transitions { A -> C via "ir" }
      }
    }
    '''
    errors = _errors(parser, source)
    assert any("no declarado 'C'" in e.message for e in errors)


def test_initial_not_in_states(parser):
    source = '''
    entity "x" {
      lifecycle {
        initial: "Z"
        states ["A"]
        transitions { }
      }
    }
    '''
    errors = _errors(parser, source)
    assert any("inicial" in e.message for e in errors)


def test_event_without_transition(parser):
    source = '''
    entity "x" {
      lifecycle {
        initial: "A"
        states ["A", "B"]
        transitions { A -> B via "ir" }
      }
      events { on_transition "volar" emit "x.volado" }
    }
    '''
    errors = _errors(parser, source)
    assert any("volar" in e.message for e in errors)


def test_rule_needs_exactly_one_trigger(parser):
    source = '''
    rule "r" {
      on_event: "a.b"
      on_state: "x.Y"
      execute: process.p
    }
    '''
    errors = _errors(parser, source)
    assert any("exactamente un trigger" in e.message for e in errors)


def test_process_references_unknown_step(parser):
    source = '''
    process "p" {
      stage "s" { mode: sequential steps [step.inexistente] }
    }
    '''
    errors = _errors(parser, source)
    assert any("inexistente" in e.message for e in errors)


def test_human_task_forbidden_in_parallel(parser):
    source = '''
    process "p" {
      stage "s" { mode: parallel steps [step.h] }
    }
    step "h" { type: human_task signals ["ok"] }
    '''
    errors = _errors(parser, source)
    assert any("parallel" in e.message for e in errors)


def test_branch_to_end_is_valid(parser):
    source = '''
    process "p" {
      stage "d" { mode: decision steps [] else -> stage.end }
    }
    '''
    assert _errors(parser, source) == []
