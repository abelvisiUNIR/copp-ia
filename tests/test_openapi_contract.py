"""El contrato OpenAPI del gateway: ids estables, únicos y agrupados.

Sin `operation_id` explícito, FastAPI lo deriva del nombre de la función + path + método
(`flow_version_flows__name___version__get`), así que renombrar un handler renombra el método
del cliente generado. Y `api_route(methods=[...])` con varios métodos hace que todas las
operaciones hereden el mismo id — que en un cliente colisiona.
"""
from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute

from teleflow.gateway.main import app

FAMILIAS = {"keys", "flows", "instances", "entities", "composer"}


def _operaciones() -> list[tuple[str, str, dict[str, Any]]]:
    spec = app.openapi()
    return [(path, metodo, op)
            for path, item in spec["paths"].items()
            for metodo, op in item.items()]


def test_toda_ruta_declara_operation_id_explicito() -> None:
    """Mirado sobre las rutas, no sobre el documento.

    En el documento `operationId` siempre viene relleno (FastAPI lo autogenera si falta), así
    que chequearlo ahí no probaría nada. En la ruta, `operation_id` es `None` si no se declaró.
    """
    sin_id = [f"{sorted(r.methods)} {r.path}" for r in app.routes
              if isinstance(r, APIRoute) and r.include_in_schema and r.operation_id is None]
    assert not sin_id, f"rutas sin operation_id explícito: {sin_id}"


def test_los_operation_id_son_unicos() -> None:
    ids = [op["operationId"] for _, _, op in _operaciones()]
    duplicados = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicados, f"operation_id duplicados (colisionan en un cliente): {duplicados}"


def test_los_operation_id_no_son_los_autogenerados() -> None:
    """Los derivados por FastAPI arrastran el path: `..._flows__name___version__get`."""
    autogenerados = [op["operationId"] for _, m, op in _operaciones()
                     if op["operationId"].endswith(f"_{m.lower()}")]
    assert not autogenerados, f"parecen autogenerados: {autogenerados}"


def test_toda_ruta_esta_agrupada_en_una_familia_conocida() -> None:
    sueltas = [f"{m.upper()} {p}" for p, m, op in _operaciones()
               if not set(op.get("tags", [])) & FAMILIAS]
    assert not sueltas, f"rutas sin tag de familia (Swagger las lista planas): {sueltas}"
