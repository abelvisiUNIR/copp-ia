"""Política de reintentos de steps: qué se reintenta, qué falla ya, y con qué backoff.

Sin DB ni broker: `_run_step` solo usa `self._settings`, así que el engine se construye
con dependencias nulas y se mockea el adapter.
"""
import random

import pytest

from teleflow.common.config import Settings
from teleflow.dsl.ast_nodes import StepDef
from teleflow.executor_service import adapters
from teleflow.executor_service.adapters import RetryableStepError, StepExecutionError
from teleflow.executor_service.engine import ExecutionEngine, StepFailed


def make_engine(**overrides) -> ExecutionEngine:
    settings = Settings(step_retry_base_delay=0, step_retry_max_delay=0, **overrides)
    return ExecutionEngine(None, None, None, None, settings)  # type: ignore[arg-type]


def _install_automated_que_falla(monkeypatch, exc, intentos):
    async def _fake(step, integration, ctx):
        intentos.append(1)
        raise exc

    monkeypatch.setattr(adapters, "run_automated", _fake)


async def test_error_transitorio_agota_los_reintentos(monkeypatch):
    """503 → se reintenta hasta gastar `retries` y recién ahí falla la instancia."""
    intentos: list[int] = []
    _install_automated_que_falla(
        monkeypatch, RetryableStepError("503 upstream caído"), intentos)
    step = StepDef(name="crear", type="automated", retries=2)

    with pytest.raises(StepFailed) as exc_info:
        await make_engine()._run_step(step, {}, {"payload": {}, "steps": {}}, "flow")

    assert len(intentos) == 3           # intento inicial + 2 reintentos
    assert "agotó 3 intentos" in str(exc_info.value)


async def test_error_permanente_no_gasta_reintentos(monkeypatch):
    """400 → falla al primer intento: reintentar el mismo request malo es tirar tiempo."""
    intentos: list[int] = []
    _install_automated_que_falla(
        monkeypatch, StepExecutionError("400 payload inválido"), intentos)
    step = StepDef(name="crear", type="automated", retries=5)

    with pytest.raises(StepFailed) as exc_info:
        await make_engine()._run_step(step, {}, {"payload": {}, "steps": {}}, "flow")

    assert len(intentos) == 1           # NO reintentó pese a retries=5
    assert "error permanente" in str(exc_info.value)


async def test_transitorio_que_se_recupera_devuelve_ok(monkeypatch):
    """Falla el 1er intento con 503 y anda el 2do: el step sale bien."""
    intentos: list[int] = []

    async def _fake(step, integration, ctx):
        intentos.append(1)
        if len(intentos) == 1:
            raise RetryableStepError("503")
        return {"ok": True}

    monkeypatch.setattr(adapters, "run_automated", _fake)
    step = StepDef(name="crear", type="automated", retries=3)

    out = await make_engine()._run_step(step, {}, {"payload": {}, "steps": {}}, "flow")

    assert out == {"ok": True}
    assert len(intentos) == 2


async def test_bug_inesperado_falla_ya(monkeypatch):
    """Una excepción no clasificada (bug) es permanente: no se reintenta 3 veces."""
    intentos: list[int] = []
    _install_automated_que_falla(monkeypatch, KeyError("campo"), intentos)
    step = StepDef(name="crear", type="automated", retries=3)

    with pytest.raises(StepFailed):
        await make_engine()._run_step(step, {}, {"payload": {}, "steps": {}}, "flow")

    assert len(intentos) == 1


# ------------------------------------------------------------------- backoff

def test_backoff_exponencial_con_jitter_y_tope(monkeypatch):
    """Full jitter: el delay es uniforme en [0, techo], con techo exponencial topeado."""
    techos: list[tuple[float, float]] = []

    def fake_uniform(low: float, high: float) -> float:
        techos.append((low, high))
        return high

    # Se parchea el módulo `random` directamente: es el mismo objeto que importa el engine,
    # y llegar a él por `engine.random` sería un re-export implícito (mypy strict lo rechaza).
    monkeypatch.setattr(random, "uniform", fake_uniform)
    eng = ExecutionEngine(
        None, None, None, None,  # type: ignore[arg-type]
        Settings(step_retry_base_delay=1.0, step_retry_max_delay=10.0))

    assert eng._retry_delay(0) == 1.0      # 1 * 2^0
    assert eng._retry_delay(1) == 2.0      # 1 * 2^1
    assert eng._retry_delay(2) == 4.0
    assert eng._retry_delay(9) == 10.0     # topeado por step_retry_max_delay
    assert all(low == 0 for low, _ in techos)   # jitter desde 0
