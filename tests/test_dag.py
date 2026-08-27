"""Construcción del DAG de stages (networkx) en el executor."""
import networkx as nx

from teleflow.executor_service.engine import (
    build_stage_dag,
    ramas_por_decision,
    siguiente_stage,
)


def test_sequential_dag(parser, ceibal_source):
    flow = parser.parse(ceibal_source)
    proc = flow.processes["asignacion_dispositivo"]
    graph = build_stage_dag(proc)
    assert list(nx.topological_sort(graph)) == ["verificacion", "entrega"]


def test_decision_dag(parser, venta_source):
    flow = parser.parse(venta_source)
    proc = flow.processes["venta_internet_hogar"]
    graph = build_stage_dag(proc)
    assert graph.has_edge("decidir", "activacion")
    assert graph.has_edge("decidir", "rechazo")
    assert nx.is_directed_acyclic_graph(graph)


# ------------------------------------------- las ramas no se derraman una en otra
#
# Un stage que no es decision cae en el de al lado, y las ramas de una decisión se escriben una
# debajo de la otra. Antes eso hacía que elegir la rama buena la ejecutara **y después siguiera
# de largo hacia la mala**: se corrían las dos. Un flow generado el 2026-08-27 llegó desplegado
# con ese defecto y, al firmarse una aprobación, iba a mandar el correo de aprobación, el de
# rechazo y el aviso de "nadie respondió". Ver el ADR de la caída secuencial.

_DOS_RAMAS = '''
process "p" {
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


def test_una_rama_no_cae_en_su_hermana(parser):
    proc = parser.parse(_DOS_RAMAS).processes["p"]
    graph = build_stage_dag(proc)

    assert graph.has_edge("decidir", "ok")
    assert graph.has_edge("decidir", "mal")
    # La de abajo: `ok` termina el proceso en vez de seguir hacia `mal`.
    assert not graph.has_edge("ok", "mal")


def test_la_caida_sigue_valiendo_fuera_de_las_ramas(parser):
    """La regla es acotada: solo corta el paso hacia **otra rama de la misma decisión**. Un
    stage común sigue cayendo en el de al lado, que es lo que hace legible un proceso lineal."""
    fuente = '''
    process "p" {
      input { a: string required }
      stage "uno" { mode: sequential steps [step.x] }
      stage "dos" { mode: sequential steps [step.x] }
    }
    step "x" { type: automated retries: 1 }
    '''
    graph = build_stage_dag(parser.parse(fuente).processes["p"])

    assert graph.has_edge("uno", "dos")


def test_una_rama_de_varios_stages_sigue_encadenada(parser):
    """Una rama puede tener más de un stage: la caída se corta al llegar a la hermana, no al
    salir del primer stage. Es la diferencia con haber hecho que toda rama terminara el
    proceso, que habría prohibido esto."""
    fuente = '''
    process "p" {
      input { a: string required }
      stage "decidir" {
        mode: decision
        steps []
        when a == "si" -> stage.ok_uno
        else -> stage.mal
      }
      stage "ok_uno" { mode: sequential steps [step.x] }
      stage "ok_dos" { mode: sequential steps [step.x] }
      stage "mal"    { mode: sequential steps [step.x] }
    }
    step "x" { type: automated retries: 1 }
    '''
    graph = build_stage_dag(parser.parse(fuente).processes["p"])

    assert graph.has_edge("ok_uno", "ok_dos"), "la rama tiene que poder seguir"
    assert not graph.has_edge("ok_dos", "mal"), "pero no pisar a la hermana"


def test_el_pegote_terminal_sigue_funcionando(parser, venta_source, ceibal_source):
    """Los flows escritos con el `stage` decision terminal —el pegote que existía para tapar
    esto— tienen que seguir comportándose igual. Si alguno cambia, el cambio de semántica
    rompió archivos que ya andaban."""
    for fuente in (venta_source, ceibal_source):
        for proc in parser.parse(fuente).processes.values():
            assert nx.is_directed_acyclic_graph(build_stage_dag(proc))


# ------------------------------------------- la regla que ejecuta el intérprete
#
# El DAG de arriba solo alimenta el aviso de ciclos. Lo que decide qué corre de verdad es
# `siguiente_stage()`, y estos tests son sobre esa función.

def _proc_y_ramas(parser, fuente, nombre="p"):
    proc = parser.parse(fuente).processes[nombre]
    return proc, ramas_por_decision(proc)


def test_al_terminar_una_rama_el_proceso_termina(parser):
    proc, ramas = _proc_y_ramas(parser, _DOS_RAMAS)
    indice = {s.name: i for i, s in enumerate(proc.stages)}

    # Venimos de la decisión `decidir` y estamos parados en `ok`. La de al lado es `mal`,
    # su hermana: el proceso termina en vez de mandar los dos avisos.
    assert siguiente_stage(proc, ramas, indice["ok"], "decidir") == len(proc.stages)


def test_sin_venir_de_una_decision_se_cae_normal(parser):
    proc, ramas = _proc_y_ramas(parser, _DOS_RAMAS)
    indice = {s.name: i for i, s in enumerate(proc.stages)}

    assert siguiente_stage(proc, ramas, indice["ok"], None) == indice["mal"]


def test_dentro_de_una_rama_se_sigue_cayendo(parser):
    fuente = '''
    process "p" {
      input { a: string required }
      stage "decidir" {
        mode: decision
        steps []
        when a == "si" -> stage.ok_uno
        else -> stage.mal
      }
      stage "ok_uno" { mode: sequential steps [step.x] }
      stage "ok_dos" { mode: sequential steps [step.x] }
      stage "mal"    { mode: sequential steps [step.x] }
    }
    step "x" { type: automated retries: 1 }
    '''
    proc, ramas = _proc_y_ramas(parser, fuente)
    indice = {s.name: i for i, s in enumerate(proc.stages)}

    # La rama sigue: ok_uno -> ok_dos.
    assert siguiente_stage(proc, ramas, indice["ok_uno"], "decidir") == indice["ok_dos"]
    # Y se corta recién al llegar a la hermana.
    assert siguiente_stage(proc, ramas, indice["ok_dos"], "decidir") == len(proc.stages)


def test_la_ultima_rama_termina_por_fin_de_archivo(parser):
    """La rama de más abajo no tiene hermana adelante: termina porque se acaban los stages,
    no por la regla. Vale la pena fijarlo para que no dependa de un caso especial."""
    proc, ramas = _proc_y_ramas(parser, _DOS_RAMAS)
    indice = {s.name: i for i, s in enumerate(proc.stages)}

    assert siguiente_stage(proc, ramas, indice["mal"], "decidir") == len(proc.stages)
