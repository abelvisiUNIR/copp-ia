"""Construcción del DAG de stages (networkx) en el executor."""
import networkx as nx

from teleflow.executor_service.engine import build_stage_dag


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
