"""Autorización del gateway: scopes por endpoint.

La **autenticación** (¿la key es válida?) la hace el middleware de `main.py`. Acá vive la
**autorización** (¿esa key puede hacer *esto*?), porque el permiso depende de la ruta.

Un scope es una familia de acciones, no una ruta: `flows:deploy` cubre el deploy sin importar
cuántos endpoints lo expongan. El comodín `*` significa "todos", y es el default de la key
global para no romper instalaciones existentes.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request

# --- catálogo de scopes -------------------------------------------------------
# Separados por lo que un tercero podría necesitar por separado. La distinción que
# motiva todo esto: leer una vista 360 (entities:read) NO debe habilitar desplegar
# código en el organismo (flows:deploy).

FLOWS_READ = "flows:read"          # listar flows y ver sus versiones (incluye /parse)
FLOWS_DEPLOY = "flows:deploy"      # registrar una versión nueva = ejecutar código nuevo
INSTANCES_READ = "instances:read"  # ver instancias y su estado
INSTANCES_TRIGGER = "instances:trigger"  # disparar un proceso
INSTANCES_SIGNAL = "instances:signal"    # resolver un human_task
INSTANCES_RETRY = "instances:retry"      # reintentar una instancia FAILED (operativo)
ENTITIES_READ = "entities:read"    # entidades, relaciones y vista 360
ENTITIES_WRITE = "entities:write"  # crear entidades/relaciones y transicionarlas
COMPOSE_READ = "compose:read"      # ver borradores generados por IA
COMPOSE_WRITE = "compose:write"    # generar/aprobar borradores

ALL_SCOPES = frozenset({
    FLOWS_READ, FLOWS_DEPLOY,
    INSTANCES_READ, INSTANCES_TRIGGER, INSTANCES_SIGNAL, INSTANCES_RETRY,
    ENTITIES_READ, ENTITIES_WRITE,
    COMPOSE_READ, COMPOSE_WRITE,
})

WILDCARD = "*"


class UnknownScopeError(ValueError):
    """Scope inexistente en la config: se falla al arrancar, no en runtime."""


def parse_scopes(raw: str) -> frozenset[str]:
    """`"*"` → todos. `"flows:read, entities:read"` → esos dos. Vacío → ninguno.

    Un scope desconocido es un error de configuración (un typo en `TELEFLOW_API_KEY_SCOPES`
    silenciado daría *menos* permisos de los que el operador cree, o lo dejaría preguntándose
    por qué su key no anda).
    """
    partes = [p.strip() for p in raw.split(",") if p.strip()]
    if WILDCARD in partes:
        return frozenset(ALL_SCOPES)
    desconocidos = sorted(set(partes) - ALL_SCOPES)
    if desconocidos:
        raise UnknownScopeError(
            f"scope(s) desconocido(s): {', '.join(desconocidos)}. "
            f"Válidos: {', '.join(sorted(ALL_SCOPES))} (o '{WILDCARD}')"
        )
    return frozenset(partes)


def scopes_de(request: Request) -> frozenset[str]:
    """Scopes que el middleware resolvió para la key de este request."""
    scopes: frozenset[str] | None = getattr(request.state, "scopes", None)
    return scopes if scopes is not None else frozenset()


def require(scope: str) -> Callable[[Request], None]:
    """Dependencia FastAPI: 403 si la key no tiene el scope."""
    def _check(request: Request) -> None:
        if scope not in scopes_de(request):
            raise HTTPException(
                status_code=403,
                detail=f"la API key no tiene el scope '{scope}'",
            )
    return _check


def require_por_metodo(por_metodo: dict[str, str]) -> Callable[[Request], None]:
    """Igual, para rutas que exponen varios métodos (GET lee, POST/PATCH escriben)."""
    def _check(request: Request) -> None:
        scope = por_metodo.get(request.method)
        if scope is None:
            raise HTTPException(status_code=405, detail="método no permitido")
        if scope not in scopes_de(request):
            raise HTTPException(
                status_code=403,
                detail=f"la API key no tiene el scope '{scope}'",
            )
    return _check
