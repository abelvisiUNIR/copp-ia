"""E2E: listar las entidades de un tipo.

El listado se agregó porque faltaba la pregunta más básica del dominio: se podía crear una
entidad, buscarla **por id** y transicionarla, pero no preguntar "¿qué niños hay?". Sin eso,
cualquier interfaz obliga a saberse los ids de memoria — que es justo lo que una interfaz
viene a evitar.

Va como e2e y no como unitario porque lo que hay que fijar es el filtro contra Postgres real
(el `WHERE estado = ...` y el orden), no el reparto de un diccionario.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e


async def _crear_nino(client: httpx.AsyncClient, eid: str, suf: str) -> None:
    r = await client.post("/entities/nino", json={"entity_id": eid, "fields": {
        "ci": f"e2e-{suf}", "nombre": f"Nino {suf}", "fecha_nac": "2014-03-01",
        "departamento": "Montevideo", "nivel": "primaria"}})
    assert r.status_code == 201, r.text


async def test_el_listado_devuelve_las_entidades_del_tipo(
    client: httpx.AsyncClient, deployed: None
) -> None:
    suf = uuid.uuid4().hex[:8]
    eid = f"nino-list-{suf}"
    await _crear_nino(client, eid, suf)

    r = await client.get("/entities/nino?limit=200")
    assert r.status_code == 200, r.text
    encontrados = {e["entity_id"] for e in r.json()}
    assert eid in encontrados

    # Y trae lo que una interfaz necesita para mostrar una fila sin pedir el detalle.
    fila = next(e for e in r.json() if e["entity_id"] == eid)
    assert fila["estado"] == "REGISTRADO"
    assert fila["campos"]["nombre"] == f"Nino {suf}"
    assert fila["entity_type"] == "nino"


async def test_el_filtro_por_estado_separa_lo_activo_de_lo_recien_registrado(
    client: httpx.AsyncClient, deployed: None
) -> None:
    """El filtro es la razón de ser del listado en una bandeja: 'qué hay en este estado'."""
    suf = uuid.uuid4().hex[:8]
    quieto, activado = f"nino-quieto-{suf}", f"nino-activo-{suf}"
    await _crear_nino(client, quieto, f"q{suf}")
    await _crear_nino(client, activado, f"a{suf}")

    r = await client.post(f"/entities/nino/{activado}/transition", json={"via": "activar"})
    assert r.status_code == 200, r.text

    activos = {e["entity_id"] for e in (await client.get(
        "/entities/nino?estado=ACTIVO&limit=200")).json()}
    assert activado in activos
    assert quieto not in activos

    registrados = {e["entity_id"] for e in (await client.get(
        "/entities/nino?estado=REGISTRADO&limit=200")).json()}
    assert quieto in registrados
    assert activado not in registrados


async def test_un_tipo_sin_entidades_devuelve_lista_vacia_y_no_404(
    client: httpx.AsyncClient, deployed: None
) -> None:
    """Preguntar por algo que todavía no existe no es un error: es una bandeja vacía.

    Un 404 acá obligaría a cada interfaz a distinguir "no hay ninguno" de "el tipo no
    existe", y en una bandeja las dos cosas se dibujan igual.
    """
    r = await client.get(f"/entities/no_existe_{uuid.uuid4().hex[:6]}")
    assert r.status_code == 200, r.text
    assert r.json() == []
