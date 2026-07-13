"""Serialización del AST a JSON (para registry y consumidores de API)."""
from __future__ import annotations

import dataclasses
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        data: dict[str, Any] = {"_node": type(obj).__name__}
        for f in dataclasses.fields(obj):
            if f.metadata.get("transient"):
                continue
            data[f.name] = to_jsonable(getattr(obj, f.name))
        return data
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    return obj
