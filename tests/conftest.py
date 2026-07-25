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

    async def execute(self, *args, **kwargs):
        """Consultas de listado (p.ej. `GET /audit`): sin resultados."""
        return _ResultadoVacio()


class _ResultadoVacio:
    def scalars(self):
        return self

    def all(self):
        return []


class _RedisInerte:
    """Redis que no hace nada. El gateway lo usa para invalidar el cache de keys entre
    réplicas y para el rate limit; en los tests unitarios no hay Redis (el compose no publica
    el puerto) y cada intento de conexión costaba ~2 s.

    `incr` devuelve 1 siempre: en los tests unitarios nunca se busca el límite, y quien lo
    prueba de verdad inyecta su propio doble.
    """

    async def publish(self, canal, dato):
        return 0

    async def incr(self, clave):
        return 1

    async def expire(self, clave, segundos):
        return True

    async def aclose(self):
        return None

    def pubsub(self):
        return self

    async def subscribe(self, *canales):
        return None

    async def get_message(self, **kwargs):
        import asyncio

        await asyncio.sleep(3600)  # nunca llega nada; la tarea se cancela al cerrar

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def sink_auditoria(monkeypatch):
    """Aísla al gateway de la I/O real y captura los `AuditLog` que escribiría.

    Cubre las dos dependencias externas del gateway —Postgres y Redis—, que en los tests
    unitarios no están: sin esto cada request paga varios segundos en conexiones fallidas.
    """
    from teleflow.gateway import main

    filas: list[Any] = []
    monkeypatch.setattr(main, "get_sessionmaker", lambda: lambda: _SesionFalsa(filas))
    import redis.asyncio as aioredis

    # `main` hace `import redis.asyncio as aioredis`, así que alcanza con el módulo.
    monkeypatch.setattr(aioredis, "from_url", lambda *a, **k: _RedisInerte())
    return filas


@pytest.fixture(scope="session")
def ceibal_source() -> str:
    return (ROOT / "examples" / "ceibal.tflow").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def venta_source() -> str:
    return (ROOT / "examples" / "venta_internet_hogar.tflow").read_text(encoding="utf-8")
