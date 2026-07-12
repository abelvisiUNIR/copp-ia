"""E2E: cadena event-driven de Ceibal.

entity nino + curso -> activar nino (regla prioridad_dispositivo dispara
asignacion_dispositivo) -> inscripcion + activar -> Vista 360.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e


async def test_entity_rule_process_y_vista_360(
    client: httpx.AsyncClient,
    count_instances: Callable[[str], Awaitable[int]],
    poll_count: Callable[..., Awaitable[int]],
) -> None:
    suf = uuid.uuid4().hex[:8]
    nino, curso = f"nino-e2e-{suf}", f"curso-e2e-{suf}"

    # baseline de instancias del proceso que dispara la regla
    antes = await count_instances("asignacion_dispositivo")

    # 1. Crear entidades
    r = await client.post("/entities/nino", json={"entity_id": nino, "fields": {
        "ci": f"e2e-{suf}", "nombre": "Juan E2E", "fecha_nac": "2014-03-01",
        "departamento": "Montevideo", "nivel": "primaria"}})
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "REGISTRADO"

    r = await client.post("/entities/curso", json={"entity_id": curso, "fields": {
        "nombre": "Robotica E2E", "area": "robotica"}})
    assert r.status_code == 201, r.text

    # 2. Activar nino -> emite nino.activado -> regla prioridad_dispositivo
    r = await client.post(f"/entities/nino/{nino}/transition", json={"via": "activar"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ACTIVO"

    # 3. Crear y activar la inscripcion
    r = await client.post("/relations/inscripcion", json={
        "from_id": nino, "to_id": curso,
        "fields": {"fecha_inscripcion": "2026-06-10", "modalidad": "virtual"}})
    assert r.status_code == 201, r.text
    rid = r.json()["relation_id"]
    r = await client.post(f"/relations/inscripcion/{rid}/transition", json={"via": "activar"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ACTIVA"

    # 4. La regla event-driven disparó (async) un proceso asignacion_dispositivo
    await poll_count("asignacion_dispositivo", antes + 1)

    # 5. Vista 360 agregada
    r = await client.get(f"/entities/nino/{nino}/360")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["estado_actual"] == "ACTIVO"
    inscripciones = [rel for rel in v["relaciones_activas"] if rel["tipo"] == "inscripcion"]
    assert len(inscripciones) == 1
    assert inscripciones[0]["curso"]["id"] == curso
    eventos = {e["evento"] for e in v["timeline"]}
    assert {"nino.activado", "inscripcion.activada"} <= eventos
