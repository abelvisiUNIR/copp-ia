---
project: copp-ia
date: 2026-07-09
status: accepted
provenance: copp-ia@chore/mypy-strict-clean@13f2907
tags: [adr, mypy, typing, networkx, deuda-tecnica]
---

# ADR (wiki): networkx como `ignore_missing_imports` en mypy

> Provenance: `copp-ia@chore/mypy-strict-clean@13f2907`. Decisión tomada durante el
> work-stream [[saneamiento-mypy-strict]]. **No** es un ADR del arquitecto (los suyos son
> ADR-001..005); es una decisión del equipo sobre el tooling.

## Context
Al llevar `mypy --strict` a 0 errores, quedaba 1 error `import-untyped` en
`teleflow/executor_service/engine.py:19` (`import networkx as nx`): networkx no trae tipos
inline (`py.typed`).

La vía "obvia" —instalar el stub `types-networkx`— **empeora las cosas**: ese paquete
depende de los stubs de numpy, y `numpy/__init__.pyi` usa la sentencia `type` (PEP 695),
soportada solo en Python 3.12+. Con el `python_version = "3.11"` que el proyecto fija en
mypy, eso dispara un error de sintaxis en el stub de numpy que **aborta el chequeo completo**
(`Type statement is only supported in Python 3.12 and greater`).

## Decision
Tratar networkx como librería **sin tipos**, con un override en `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "networkx.*"
ignore_missing_imports = true
```

No instalar `types-networkx`.

## Rationale
- El uso de networkx en el repo es **acotado** (construcción/validación del DAG en
  `engine.py`); perder su tipado no compromete la seguridad de tipos del dominio.
- El override es local a mypy, no toca el código ni el runtime.
- Evita acoplar el type-checking a una cadena de stubs (numpy) incompatible con el target 3.11.

## Consequences
- **Trampa a evitar:** si alguien "arregla" el `import-untyped` instalando `types-networkx`,
  el chequeo se rompe de nuevo por numpy 3.12. Este ADR existe para que no se repita.
- `nx.*` se ve como `Any` para mypy; si en el futuro se sube el target a 3.12+, se puede
  reconsiderar instalar los stubs y quitar el override.

## Alternatives
- `# type: ignore[import-untyped]` en la línea del import — más local, pero repite el ignore
  si networkx se importa en otro módulo y no documenta el porqué.
- Instalar `types-networkx` — descartada: rompe por numpy 3.12 vs target 3.11.
- Subir `python_version` de mypy a 3.12 — fuera de alcance; el proyecto declara 3.11.

## Sources
`pyproject.toml` (`[tool.mypy]` + override) · `teleflow/executor_service/engine.py:19` ·
[[saneamiento-mypy-strict]] · [[2026-07-09-validacion-doc-vs-codigo]]
