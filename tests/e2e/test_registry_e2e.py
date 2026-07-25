"""E2E del versionado inmutable, contra Postgres real.

El invariante que da sentido al `registry-service` —"una versión registrada nunca cambia"— lo
sostiene un `UniqueConstraint(name, version)`, así que probarlo de verdad exige la base: un
fake diría que sí sin verificar nada. Requiere `docker compose up -d` (si no, se saltan).
"""
import uuid

import httpx
import pytest

pytestmark = pytest.mark.e2e

GATEWAY = "http://localhost:8000"
H = {"X-TeleFlow-API-Key": "dev-key-change-me", "Content-Type": "application/json"}

FUENTE_V1 = 'entity "socio" {\n  fields { nombre: string required }\n}\n'
FUENTE_V2 = 'entity "socio" {\n  fields { nombre: string required\n    email: string }\n}\n'


@pytest.fixture
def flow(gateway_up: None) -> str:
    """Un flow nuevo por test: el registro es inmutable, así que no se puede reutilizar."""
    nombre = f"e2e_registry_{uuid.uuid4().hex[:8]}"
    r = httpx.post(f"{GATEWAY}/flows/{nombre}", headers=H, timeout=30,
                   json={"source": FUENTE_V1, "version": "1.0.0"})
    assert r.status_code == 201, r.text
    return nombre


def test_una_version_registrada_no_se_puede_pisar(flow):
    """El invariante: reintentar la misma versión con otro contenido no cambia lo guardado."""
    r = httpx.post(f"{GATEWAY}/flows/{flow}", headers=H, timeout=30,
                   json={"source": FUENTE_V2, "version": "1.0.0"})

    assert r.status_code == 409
    assert "inmutable" in r.text

    guardado = httpx.get(f"{GATEWAY}/flows/{flow}/1.0.0", headers=H, timeout=20).json()
    assert guardado["source"] == FUENTE_V1, "el rechazo dio 409 pero el contenido cambió"


def test_registrar_una_version_mayor_mueve_latest(flow):
    httpx.post(f"{GATEWAY}/flows/{flow}", headers=H, timeout=30,
               json={"source": FUENTE_V2, "version": "1.1.0"}).raise_for_status()

    latest = httpx.get(f"{GATEWAY}/flows/{flow}/latest", headers=H, timeout=20).json()
    assert latest["version"] == "1.1.0"


def test_registrar_una_version_menor_no_mueve_latest(flow):
    """Publicar un parche viejo no puede hacer retroceder lo que sirve `latest`."""
    httpx.post(f"{GATEWAY}/flows/{flow}", headers=H, timeout=30,
               json={"source": FUENTE_V2, "version": "2.0.0"}).raise_for_status()
    httpx.post(f"{GATEWAY}/flows/{flow}", headers=H, timeout=30,
               json={"source": FUENTE_V2, "version": "1.0.1"}).raise_for_status()

    latest = httpx.get(f"{GATEWAY}/flows/{flow}/latest", headers=H, timeout=20).json()
    assert latest["version"] == "2.0.0"


def test_un_release_candidate_no_se_vuelve_latest(flow):
    """El bug que motivó esto: `1.0.0-rc1` se ordenaba por encima de `1.0.0`, así que el
    executor pasaba a disparar procesos con el candidato."""
    r = httpx.post(f"{GATEWAY}/flows/{flow}", headers=H, timeout=30,
                   json={"source": FUENTE_V2, "version": "1.0.0-rc1"})
    assert r.status_code == 201, r.text

    latest = httpx.get(f"{GATEWAY}/flows/{flow}/latest", headers=H, timeout=20).json()
    assert latest["version"] == "1.0.0", "latest quedó apuntando a un release candidate"


def test_el_listado_de_versiones_viene_de_mayor_a_menor(flow):
    for version in ("1.2.0", "1.10.0", "1.9.0"):
        httpx.post(f"{GATEWAY}/flows/{flow}", headers=H, timeout=30,
                   json={"source": FUENTE_V2, "version": version}).raise_for_status()

    detalle = httpx.get(f"{GATEWAY}/flows/{flow}", headers=H, timeout=20).json()
    versiones = [v["version"] for v in detalle["versions"]]

    assert versiones == ["1.10.0", "1.9.0", "1.2.0", "1.0.0"]
    assert detalle["latest"] == "1.10.0"


def test_una_version_inexistente_da_404(flow):
    r = httpx.get(f"{GATEWAY}/flows/{flow}/9.9.9", headers=H, timeout=20)
    assert r.status_code == 404
