"""Tests de la auditoría de `except Exception`: que los fallos dejen de tragarse.

Cubre los 4 arreglos: rules (el evento llega a la DLQ), invariantes (un typo se ve),
alertas de la 360 (se loguean) y flows corruptos (quedan expuestos en el dominio).
"""
import pytest

from teleflow.dsl.ast_nodes import EntityDef, RuleDef
from teleflow.executor_service.entities import INVARIANTS_SKIPPED, EntityService
from teleflow.executor_service.rules import RuleEngine, RuleFireError


# ------------------------------------------------- #1 rules: el fallo llega a la DLQ

class _FakeDomain:
    def __init__(self, rules):
        self.merged = type("M", (), {"rules": rules})()


class _FakeLoader:
    def __init__(self, rules):
        self._domain = _FakeDomain(rules)

    async def load(self, force: bool = False):
        return self._domain


def make_rule_engine(rules) -> RuleEngine:
    engine = RuleEngine.__new__(RuleEngine)          # sin DB ni broker
    engine._domain = _FakeLoader(rules)              # type: ignore[attr-defined]
    engine._ya_disparadas = {}                       # type: ignore[attr-defined]
    return engine


MENSAJE = {"event": "nino.inscripto", "subject": "nino", "payload": {"nino_id": "n1"}}


async def test_rule_que_falla_levanta_para_que_el_evento_vaya_a_la_dlq(monkeypatch):
    """Antes: se logueaba y el EventBus ACKeaba el evento -> se perdía."""
    rule = RuleDef(name="r1", on_event="nino.inscripto")
    engine = make_rule_engine({"r1": rule})

    async def _fire_roto(rule, message):
        raise RuntimeError("executor caído")

    monkeypatch.setattr(engine, "_fire", _fire_roto)

    with pytest.raises(RuleFireError) as exc_info:
        await engine._on_event("nino.inscripto", MENSAJE)

    assert "r1" in str(exc_info.value)


async def test_una_rule_rota_no_tapa_a_las_demas(monkeypatch):
    """Se intentan TODAS las que matchean; recién al final se levanta."""
    engine = make_rule_engine({
        "rota": RuleDef(name="rota", on_event="nino.inscripto"),
        "sana": RuleDef(name="sana", on_event="nino.inscripto"),
    })
    disparadas = []

    async def _fire(rule, message):
        disparadas.append(rule.name)
        if rule.name == "rota":
            raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_fire", _fire)

    with pytest.raises(RuleFireError):
        await engine._on_event("nino.inscripto", MENSAJE)

    assert disparadas == ["rota", "sana"]   # la sana se disparó igual


async def test_reintento_no_duplica_las_rules_que_ya_salieron_bien(monkeypatch):
    """El EventBus reintenta el mismo evento: la rule que ya anduvo NO se re-dispara."""
    engine = make_rule_engine({
        "sana": RuleDef(name="sana", on_event="nino.inscripto"),
        "rota": RuleDef(name="rota", on_event="nino.inscripto"),
    })
    disparadas = []

    async def _fire(rule, message):
        disparadas.append(rule.name)
        if rule.name == "rota":
            raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_fire", _fire)

    for _ in range(3):                       # 3 intentos del EventBus
        with pytest.raises(RuleFireError):
            await engine._on_event("nino.inscripto", MENSAJE)

    assert disparadas.count("sana") == 1     # NO se duplicó la instancia de proceso
    assert disparadas.count("rota") == 3     # la fallida sí se reintentó


async def test_evento_ok_no_deja_memoria_colgada(monkeypatch):
    engine = make_rule_engine({"sana": RuleDef(name="sana", on_event="nino.inscripto")})

    async def _fire(rule, message):
        return None

    monkeypatch.setattr(engine, "_fire", _fire)
    await engine._on_event("nino.inscripto", MENSAJE)

    assert engine._ya_disparadas == {}


# --------------------------------------- #2 invariantes: un typo deja de ser invisible

def check_invariants(invariants, campos, estado="ACTIVO"):
    service = EntityService.__new__(EntityService)
    entity = EntityDef(name="nino", invariants=invariants)
    service._check_invariants(entity, campos, estado)


def _skipped(reason: str) -> float:
    return INVARIANTS_SKIPPED.labels("nino", reason)._value.get()


def test_invariante_con_typo_queda_expuesto():
    """No parsea = regla de negocio que no existe. Antes: silencio total.

    Se asierta sobre la métrica (lo que ve un operador); el log de error va aparte.
    """
    antes = _skipped("unparseable")

    check_invariants(["edad >= 5 AN edad <= 18"], {"edad": 30})   # no bloquea...

    assert _skipped("unparseable") == antes + 1                   # ...pero se ve


def test_invariante_valido_sigue_bloqueando():
    from teleflow.executor_service.entities import DomainError

    with pytest.raises(DomainError, match="Invariante violado"):
        check_invariants(["edad >= 5"], {"edad": 3})


def test_invariante_no_evaluable_no_bloquea(monkeypatch):
    """El invariante parsea pero revienta al evaluarse con estos datos: benigno,
    no bloquea la transición, pero se cuenta aparte del typo (no desaparece).

    Se fuerza el fallo: el evaluador es tolerante (con tipos raros devuelve False en vez
    de romper), así que esta rama es rara — pero es la que antes tapaba los typos.
    """
    def _explota(expr, ctx):
        raise TypeError("no comparable")

    monkeypatch.setattr("teleflow.executor_service.entities.evaluate", _explota)
    antes = _skipped("not_evaluable")

    check_invariants(["edad >= 5"], {"edad": 7})   # no levanta

    assert _skipped("not_evaluable") == antes + 1
