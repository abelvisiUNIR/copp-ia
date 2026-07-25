import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teleflow.dsl.parser import TeleFlowParser  # noqa: E402


@pytest.fixture(scope="session")
def parser() -> TeleFlowParser:
    return TeleFlowParser()


# --- auditoría ---------------------------------------------------------------
# El gateway escribe un registro por acción de escritura y por intento denegado. En los tests
# unitarios no hay Postgres (el compose no publica el puerto al host), y sin esto cada request
# auditado paga ~4 s en intentos de conexión fallidos. Además de acelerar, deja las filas a
# mano para poder afirmar qué se registró.

class _SesionFalsa:
    def __init__(self, sink):
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        self._sink.append(obj)

    async def commit(self):
        return None

    async def scalar(self, *args, **kwargs):
        """El gateway también consulta `api_keys` acá: sin fila = key no encontrada."""
        return None


@pytest.fixture
def sink_auditoria(monkeypatch):
    """Captura en memoria los `AuditLog` que el gateway escribiría."""
    from teleflow.gateway import main

    filas: list[Any] = []
    monkeypatch.setattr(main, "get_sessionmaker", lambda: lambda: _SesionFalsa(filas))
    return filas


@pytest.fixture(scope="session")
def ceibal_source() -> str:
    return (ROOT / "examples" / "ceibal.tflow").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def venta_source() -> str:
    return (ROOT / "examples" / "venta_internet_hogar.tflow").read_text(encoding="utf-8")
