"""E2E del respaldo: que el restore devuelva los datos, no que el backup produzca un archivo.

Un backup "funciona" siempre —genera un archivo— así que probarlo no dice nada. Lo que puede
estar roto es lo otro. Este test escribe un dato reconocible, respalda, **restaura en una base
aparte** y lo busca ahí.

Contra otra base y no sobre la de trabajo: un test que restaura encima de la base real sería
un test capaz de destruir el entorno de quien lo corre.

Requiere `docker compose up -d` (si no, se salta).
"""
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

GATEWAY = "http://localhost:8000"
H = {"X-TeleFlow-API-Key": "dev-key-change-me", "Content-Type": "application/json"}
ROOT = Path(__file__).resolve().parents[2]
BASE_PRUEBA = "teleflow_restore_test"


def _correr(comando: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(comando, cwd=ROOT, capture_output=True, timeout=180)


def _psql(base: str, sql: str) -> str:
    r = _correr(["docker", "compose", "exec", "-T", "postgres",
                 "psql", "-U", "teleflow", "-d", base, "-tAc", sql])
    assert r.returncode == 0, r.stderr.decode(errors="replace")
    salida: str = r.stdout.decode(errors="replace").strip()
    return salida


@pytest.fixture
def dump_path(gateway_up: None):
    """Ruta **relativa al repo** para el dump, y limpieza al terminar.

    Relativa a propósito: en Windows, bash (MSYS) recibe un `C:/...` desde un llamador que no
    es bash y lo trata como ruta relativa — el dump termina en un directorio literal `C:`
    dentro del repo, con `exit 0`. Una ruta relativa se comporta igual en todos lados.
    """
    r = _correr(["docker", "compose", "ps", "-q", "postgres"])
    if r.returncode != 0 or not r.stdout.strip():
        pytest.skip("docker compose no disponible: el respaldo se prueba con el stack")

    relativa = f"backups/test-{uuid.uuid4().hex[:8]}.dump"
    yield relativa
    (ROOT / relativa).unlink(missing_ok=True)


def test_el_restore_devuelve_los_datos(dump_path):
    """El viaje completo, con un dato que solo puede venir del respaldo."""
    nombre = f"backup_probe_{uuid.uuid4().hex[:8]}"
    r = httpx.post(f"{GATEWAY}/flows/{nombre}", headers=H, timeout=30,
                   json={"source": 'entity "socio" { fields { nombre: string required } }',
                         "version": "1.0.0"})
    assert r.status_code == 201, r.text

    respaldo = _correr(["bash", "scripts/backup.sh", dump_path])
    assert respaldo.returncode == 0, respaldo.stderr.decode(errors="replace")
    assert (ROOT / dump_path).stat().st_size > 1024, "un dump de pocos bytes no es un respaldo"

    restore = _correr(["bash", "scripts/restore.sh", dump_path, BASE_PRUEBA])
    assert restore.returncode == 0, restore.stderr.decode(errors="replace")

    try:
        # El dato tiene que estar en la base restaurada, no en la de trabajo.
        encontrado = _psql(
            BASE_PRUEBA,
            f"SELECT count(*) FROM flow_definitions WHERE name = '{nombre}';")
        assert encontrado == "1", f"el flow '{nombre}' no sobrevivió al respaldo"

        # Y el schema completo, no solo esa tabla: si faltara alguna, el restore quedó a medias.
        tablas = int(_psql(BASE_PRUEBA,
                           "SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema = 'public';"))
        assert tablas >= 12, f"solo {tablas} tablas en la base restaurada"

        # Las migraciones también viajan: sin esto, la base restaurada no sabría en qué
        # versión está y el próximo `alembic upgrade` haría cualquier cosa.
        version = _psql(BASE_PRUEBA, "SELECT version_num FROM alembic_version;")
        assert version, "la base restaurada no tiene versión de alembic"
    finally:
        _psql("postgres", f'DROP DATABASE IF EXISTS "{BASE_PRUEBA}" WITH (FORCE);')


def test_restaurar_sobre_la_base_en_uso_pide_confirmacion(dump_path):
    """La guarda que importa: restaurar es la operación que destruye datos."""
    _correr(["bash", "scripts/backup.sh", dump_path])

    r = _correr(["bash", "scripts/restore.sh", dump_path, "teleflow"])

    assert r.returncode != 0
    assert "es la base en uso" in r.stderr.decode(errors="replace")
