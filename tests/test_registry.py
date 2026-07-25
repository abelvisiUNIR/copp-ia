"""registry-service: el orden de versiones, que decide a dónde apunta `latest`.

El servicio promete que "una versión registrada nunca cambia" y que `latest` avanza al
registrar una versión **mayor**. Lo primero lo sostiene un UniqueConstraint (se prueba contra
Postgres real en `tests/e2e/test_registry_e2e.py`); lo segundo depende enteramente de
`_semver_key`, que es lo que se fija acá.

Los dos casos que motivaron estos tests eran bugs reales: un prerelease se ordenaba **por
encima** de su release, así que registrar `1.0.0-rc1` después de `1.0.0` movía `latest` al
candidato y el executor pasaba a disparar procesos con él.
"""
from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.registry_service.main import RegisterRequest, _semver_key, register_flow


def _mayor(a: str, b: str) -> bool:
    return _semver_key(a) > _semver_key(b)


# ------------------------------------------------- prereleases (los bugs)

@pytest.mark.parametrize("prerelease", ["1.0.0-rc1", "1.0.0-beta", "1.0.0-alpha.2"])
def test_un_prerelease_nunca_supera_a_su_release(prerelease):
    """`1.0.0-rc1` daba (1,0,1) contra (1,0,0): el candidato quedaba arriba del estable."""
    assert not _mayor(prerelease, "1.0.0")
    assert _mayor("1.0.0", prerelease)


def test_un_prerelease_no_empata_con_su_release():
    """`1.0.0-beta` empataba en (1,0,0), y con el `>=` de entonces también movía el pointer."""
    assert _semver_key("1.0.0-beta") != _semver_key("1.0.0")


def test_un_prerelease_supera_al_release_anterior():
    """Ordenarlos abajo de *su* release no puede hundirlos abajo de todo."""
    assert _mayor("2.0.0-rc1", "1.9.9")


@pytest.mark.parametrize("menor,mayor", [
    ("1.0.0-alpha", "1.0.0-beta"),
    ("1.0.0-beta", "1.0.0-rc1"),
    ("1.0.0-rc1", "1.0.0-rc2"),
])
def test_los_prereleases_se_ordenan_entre_si(menor, mayor):
    assert _mayor(mayor, menor)


# ------------------------------------------------- orden numérico

def test_la_comparacion_es_numerica_y_no_alfabetica():
    """El clásico: como texto, "1.10.0" < "1.9.0"."""
    assert _mayor("1.10.0", "1.9.0")
    assert _mayor("2.0.0", "1.99.99")


@pytest.mark.parametrize("menor,mayor", [
    ("1.0.0", "1.0.1"),
    ("1.0.9", "1.1.0"),
    ("1.9.0", "2.0.0"),
    ("1.2", "1.2.1"),
])
def test_orden_entre_releases(menor, mayor):
    assert _mayor(mayor, menor)


def test_una_version_con_prefijo_se_ordena_por_sus_numeros():
    """`v1.2.3` aparece en la práctica; que no caiga al fondo por la 'v'."""
    assert _mayor("v1.2.3", "1.2.2")


def test_una_version_sin_numeros_queda_al_fondo():
    """No se valida el formato en la API: que al menos no se cuele arriba de un release."""
    assert _mayor("0.0.1", "banana")
    assert _mayor("1.0.0", "")


# ------------------------------------------------- la carrera

class _SesionQueChoca:
    """Simula el registro concurrente: el `SELECT` no ve nada, el `INSERT` choca.

    Es la ventana real entre leer y escribir. La garantía la sostiene el
    `UniqueConstraint(name, version)`; lo que se prueba acá es que el cliente reciba el mismo
    409 que en el caso secuencial, y no un 500.
    """

    def __init__(self):
        self.rollback_llamado = False

    async def scalar(self, *args, **kwargs):
        return None  # nadie registró esa versión... todavía

    async def get(self, *args, **kwargs):
        return None

    def add(self, obj):
        return None

    async def commit(self):
        raise IntegrityError("INSERT", {}, Exception("uq_flow_name_version"))

    async def rollback(self):
        self.rollback_llamado = True


async def test_una_carrera_da_409_y_no_500():
    sesion = _SesionQueChoca()

    with pytest.raises(HTTPException) as exc:
        await register_flow(
            "alta_socio",
            RegisterRequest(source="entity \"a\" { }", version="1.0.0"),
            session=cast(AsyncSession, sesion),
        )

    assert exc.value.status_code == 409
    assert "inmutable" in str(exc.value.detail)
    assert sesion.rollback_llamado, "sin rollback la sesión queda inutilizable"


def test_el_orden_es_total_y_estable():
    """`list_versions` ordena con esta clave: no puede reventar ni empatar todo."""
    versiones = ["1.0.0", "1.0.0-rc1", "1.10.0", "1.9.0", "2.0.0-beta", "2.0.0", "0.1"]
    ordenadas = sorted(versiones, key=_semver_key, reverse=True)

    assert ordenadas == [
        "2.0.0", "2.0.0-beta", "1.10.0", "1.9.0", "1.0.0", "1.0.0-rc1", "0.1",
    ]
