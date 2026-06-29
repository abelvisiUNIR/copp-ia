"""Evaluador de expresiones del DSL.

Evalúa condiciones de rules, branches, filtros de view360 e invariantes
contra un contexto dict. Resolución de refs con puntos: event.entity.campo.

Semántica null-safe: cualquier comparación con None devuelve False
(excepto == y !=), de modo que `x >= 30 OR x == null` funciona como
se espera en el documento de arquitectura.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping

from teleflow.dsl.ast_nodes import BoolOp, Cmp, Expr, Func, Not, Ref, When


class EvaluationError(Exception):
    pass


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _days_since(value: Any) -> float | None:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _years_since(value: Any) -> float | None:
    days = _days_since(value)
    return None if days is None else days / 365.25


BUILTIN_FUNCS: dict[str, Callable[..., Any]] = {
    "days_since": _days_since,
    "years_since": _years_since,
    "now": lambda: datetime.now(timezone.utc).isoformat(),
    "len": lambda x: len(x) if x is not None else 0,
}


def resolve_ref(parts: tuple[str, ...], ctx: Mapping[str, Any]) -> Any:
    """Resuelve a.b.c contra el contexto. Si un nombre simple no existe,
    se interpreta como literal string (permite `estado == ACTIVA`)."""
    current: Any = ctx
    for i, part in enumerate(parts):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif hasattr(current, part) and not isinstance(current, Mapping):
            current = getattr(current, part)
        else:
            if i == 0 and len(parts) == 1:
                return part  # nombre suelto → literal (estados, enums)
            return None
    return current


def evaluate(node: Any, ctx: Mapping[str, Any],
             funcs: Mapping[str, Callable[..., Any]] | None = None) -> Any:
    fns = {**BUILTIN_FUNCS, **(funcs or {})}

    def _eval(n: Any) -> Any:
        if not isinstance(n, Expr):
            if isinstance(n, list):
                return [_eval(item) for item in n]
            return n  # literal Python
        if isinstance(n, Ref):
            return resolve_ref(n.parts, ctx)
        if isinstance(n, Func):
            fn = fns.get(n.name)
            if fn is None:
                raise EvaluationError(f"Función desconocida: {n.name}")
            return fn(*[_eval(a) for a in n.args])
        if isinstance(n, Cmp):
            left = _eval(n.left)
            right = _eval(n.right)
            return _compare(n.op, left, right)
        if isinstance(n, BoolOp):
            if n.op == "AND":
                return all(bool(_eval(o)) for o in n.operands)
            return any(bool(_eval(o)) for o in n.operands)
        if isinstance(n, Not):
            return not bool(_eval(n.operand))
        if isinstance(n, When):
            # invariante condicional: si la condición no aplica, es válido
            if bool(_eval(n.condition)):
                return bool(_eval(n.value))
            return True
        raise EvaluationError(f"Nodo no evaluable: {type(n).__name__}")

    return _eval(node)


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "in":
        return right is not None and left in right
    if left is None or right is None:
        return False
    try:
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
    except TypeError:
        return False
    raise EvaluationError(f"Operador desconocido: {op}")
