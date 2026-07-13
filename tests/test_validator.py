"""Validación semántica: errores que el parser-service debe bloquear."""
from teleflow.dsl.validator import validate_flow


def _errors(parser, source):
    flow = parser.parse(source)
    return [i for i in validate_flow(flow) if i.level == "error"]


def _warnings(parser, source):
    flow = parser.parse(source)
    return [i for i in validate_flow(flow) if i.level == "warning"]


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


def test_duplicate_entity_is_error(parser):
    source = '''
    entity "cliente" { }
    entity "cliente" { }
    '''
    errors = _errors(parser, source)
    assert any("más de una vez" in e.message and "entity.cliente" in e.block
               for e in errors)


def test_duplicate_step_is_error(parser):
    source = '''
    step "a" { type: automated }
    step "a" { type: automated }
    '''
    assert any("step.a" in e.block for e in _errors(parser, source))


def test_rule_on_event_unknown_warns(parser):
    # hay eventos declarados, pero la regla escucha uno que nadie emite
    source = '''
    entity "cli" {
      lifecycle { initial: "A" states ["A", "B"] transitions { A -> B via "go" } }
      events { on_transition "go" emit "cli.movido" }
    }
    rule "r" { on_event: "no.existe" execute: process.p }
    '''
    assert any("on_event 'no.existe'" in w.message for w in _warnings(parser, source))


def test_rule_on_event_known_is_clean(parser):
    source = '''
    entity "cli" {
      lifecycle { initial: "A" states ["A", "B"] transitions { A -> B via "go" } }
      events { on_transition "go" emit "cli.movido" }
    }
    rule "r" { on_event: "cli.movido" execute: process.p }
    '''
    assert not any("on_event" in w.message for w in _warnings(parser, source))


def test_rule_on_relation_unknown_warns(parser):
    source = '''
    entity "cli" { }
    relation "rel1" { from: entity.cli to: entity.cli }
    rule "r" { on_relation: "norel" execute: process.p }
    '''
    assert any("on_relation 'norel'" in w.message for w in _warnings(parser, source))


def test_rule_on_state_bad_state_warns(parser):
    source = '''
    entity "cli" {
      lifecycle { initial: "A" states ["A", "B"] transitions { A -> B via "go" } }
    }
    rule "r" { on_state: "cli.Z" execute: process.p }
    '''
    assert any("on_state 'cli.Z'" in w.message for w in _warnings(parser, source))


def test_rule_on_state_malformed_warns(parser):
    source = '''
    rule "r" { on_state: "ACTIVO" execute: process.p }
    '''
    assert any("<entidad|relación>.<estado>" in w.message
               for w in _warnings(parser, source))
