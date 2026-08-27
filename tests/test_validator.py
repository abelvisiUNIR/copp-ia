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


# ----------------------- refs colgadas cuando el archivo no define esa categoría
# Antes se silenciaban (`if flow.processes and ...`): un flow sin procesos podía tener
# una rule apuntando a un process inexistente y el deploy devolvía `issues: []`.

def test_rule_a_process_inexistente_avisa_aunque_el_flow_no_tenga_procesos(parser):
    source = '''
    entity "cosa" {
      lifecycle { initial: "A" states ["A", "B"] transitions { A -> B via "go" } }
      events { on_transition "go" emit "cosa.lista" }
    }
    rule "r" { on_event: "cosa.lista" execute: process.fantasma }
    '''
    assert any("process.fantasma" in w.message for w in _warnings(parser, source))


def test_view360_alerta_a_rule_inexistente_avisa_sin_rules_en_el_archivo(parser):
    source = '''
    entity "cosa" { }
    view360 "v" {
      entity: entity.cosa
      alerts { rule: rule.no_existe }
    }
    '''
    assert any("rule.no_existe" in w.message for w in _warnings(parser, source))


def test_relation_a_entity_inexistente_avisa_sin_entities_en_el_archivo(parser):
    source = '''
    relation "rel" { from: entity.fantasma to: entity.fantasma }
    '''
    assert any("entity.fantasma" in w.message for w in _warnings(parser, source))


def test_ref_valida_en_el_mismo_archivo_no_avisa(parser):
    """El warning es por ref colgada, no por existir: lo definido en el archivo no avisa."""
    source = '''
    entity "cosa" {
      lifecycle { initial: "A" states ["A", "B"] transitions { A -> B via "go" } }
      events { on_transition "go" emit "cosa.lista" }
    }
    process "p" { stage "s" { mode: sequential steps [step.x] } }
    step "x" { type: automated }
    rule "r" { on_event: "cosa.lista" execute: process.p }
    '''
    assert _warnings(parser, source) == []


# ------------------------------------------- que la firma y la decisión se hablen
#
# Nacen de un flow que compiló, se desplegó y **rechazó una licencia sin que ninguna persona la
# mirara**. Tenía dos defectos y ninguno era de sintaxis: el paso que debía esperar al jefe
# quedó `automated`, y la decisión evaluaba una señal que nadie emitía. Un archivo válido que
# hacía lo contrario de lo pedido.

_PROC = '''
process "gestion" {{
  input {{ a: string required }}
  stage "revision" {{ mode: sequential steps [step.revisar] }}
  stage "decidir" {{
    mode: decision
    steps []
    when signals.{firma}.signal == "approve" -> stage.ok
    else -> stage.mal
  }}
  stage "ok"  {{ mode: sequential steps [step.avisar_ok] }}
  stage "fin" {{ mode: decision steps [] else -> stage.end }}
  stage "mal" {{ mode: sequential steps [step.avisar_mal] }}
}}
step "revisar" {{ {revisar} }}
step "avisar_ok"  {{ type: notification channel: "email" template: "ok" }}
step "avisar_mal" {{ type: notification channel: "email" template: "mal" }}
'''

_HUMANO = 'type: human_task assignee: "rol:jefe" signals ["approve", "reject"]'


def test_el_caso_bien_escrito_no_se_marca(parser):
    """Guarda contra falsos positivos: si esto empieza a fallar, los chequeos molestan más
    de lo que ayudan."""
    fuente = _PROC.format(firma="revisar", revisar=_HUMANO)
    assert _errors(parser, fuente) == []
    assert _warnings(parser, fuente) == []


def test_una_decision_que_espera_una_firma_de_un_paso_automatico(parser):
    """El defecto exacto que rechazó la licencia: el paso no espera a nadie, así que la señal
    nunca llega y todo cae al else."""
    fuente = _PROC.format(firma="revisar", revisar='type: automated retries: 1')
    errores = _errors(parser, fuente)

    assert len(errores) == 1
    assert "revisar" in errores[0].message
    assert "automated" in errores[0].message
    assert "else" in errores[0].message


def test_una_decision_que_espera_una_firma_inexistente(parser):
    fuente = _PROC.format(firma="paso_que_no_existe", revisar=_HUMANO)
    errores = _errors(parser, fuente)

    assert any("paso_que_no_existe" in e.message for e in errores)
    assert any("no es un step de este archivo" in e.message for e in errores)


def test_una_firma_que_nadie_lee_avisa(parser):
    """Pedir elegir entre aprobar y rechazar, y después no ramificar, hace que las dos
    respuestas terminen igual. No es un error —el proceso corre— pero casi nunca es lo que
    se quiso."""
    fuente = '''
    process "gestion" {
      input { a: string required }
      stage "revision" { mode: sequential steps [step.revisar] }
      stage "aviso" { mode: sequential steps [step.avisar] }
    }
    step "revisar" { type: human_task assignee: "rol:jefe" signals ["approve", "reject"] }
    step "avisar" { type: notification channel: "email" template: "listo" }
    '''
    avisos = _warnings(parser, fuente)

    assert len(avisos) == 1
    assert "revisar" in avisos[0].message
    assert _errors(parser, fuente) == []


def test_una_firma_de_una_sola_senal_no_avisa(parser):
    """Con una sola señal el paso es un acuse de recibo, no una bifurcación: esperar sin
    ramificar es legítimo y avisar sería ruido."""
    fuente = '''
    process "gestion" {
      input { a: string required }
      stage "revision" { mode: sequential steps [step.revisar] }
    }
    step "revisar" { type: human_task assignee: "rol:jefe" signals ["listo"] }
    '''
    assert _warnings(parser, fuente) == []


# ------------------------------------------- que una rama no caiga dentro de otra

def test_una_rama_que_cae_dentro_de_la_otra(parser):
    """Un stage que no es decision cae en el siguiente, así que la rama buena corre y después
    sigue de largo hacia los stages de la mala: se ejecutan las dos. Se cierra con un stage
    decision de 'else -> stage.end', que es lo que hacen los ejemplos del repositorio."""
    fuente = '''
    process "gestion" {
      input { a: string required }
      stage "decidir" {
        mode: decision
        steps []
        when a == "si" -> stage.ok
        else -> stage.mal
      }
      stage "ok"  { mode: sequential steps [step.avisar_ok] }
      stage "mal" { mode: sequential steps [step.avisar_mal] }
    }
    step "avisar_ok"  { type: notification channel: "email" template: "ok" }
    step "avisar_mal" { type: notification channel: "email" template: "mal" }
    '''
    errores = _errors(parser, fuente)

    assert len(errores) == 1
    assert "'ok' cae dentro de la rama 'mal'" in errores[0].message
    assert "else -> stage.end" in errores[0].message


def test_cerrar_la_rama_con_un_decision_terminal_lo_resuelve(parser):
    fuente = '''
    process "gestion" {
      input { a: string required }
      stage "decidir" {
        mode: decision
        steps []
        when a == "si" -> stage.ok
        else -> stage.mal
      }
      stage "ok"  { mode: sequential steps [step.avisar_ok] }
      stage "fin" { mode: decision steps [] else -> stage.end }
      stage "mal" { mode: sequential steps [step.avisar_mal] }
    }
    step "avisar_ok"  { type: notification channel: "email" template: "ok" }
    step "avisar_mal" { type: notification channel: "email" template: "mal" }
    '''
    assert _errors(parser, fuente) == []


def test_los_ejemplos_del_repositorio_quedan_limpios(parser, ceibal_source, venta_source):
    """Los tres chequeos nuevos se agregan sobre flows que ya existen y están bien escritos.
    Si alguno los marca, el chequeo está mal, no el ejemplo."""
    for fuente in (ceibal_source, venta_source):
        assert validate_flow(parser.parse(fuente)) == []
