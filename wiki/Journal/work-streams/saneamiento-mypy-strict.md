---
project: copp-ia
status: completed
created: 2026-07-09
updated: 2026-07-09
tags: [mypy, typing, deuda-tecnica, calidad]
---

# Saneamiento mypy --strict

## Goal
Llevar `mypy teleflow` (strict) a **0 errores**, cumpliendo la convención declarada en la doc
(`teleflow-deployment.typ:261`) que hoy no se cumple: **236 errores en 15 archivos**.

## Context
Derivado del onboarding ([[onboarding-copp-ia]]). Diagnóstico en
[[2026-07-09-validacion-doc-vs-codigo]]. Distribución de los 236 errores:
- `type-arg` 202 (180 en `dsl/transformer.py` — métodos del Transformer de Lark sin tipar).
- `no-any-return` 13, `no-untyped-def` 12, `attr-defined` 4 (`rules.py`), `arg-type` 2, otros 3.

El `.venv` de la sesión es Python 3.14; el proyecto pinea 3.11 (`mypy python_version=3.11`).
Parte de los errores podría ser ruido de versión → validar contra 3.11 real en algún punto.

## Current State
- **OBJETIVO ALCANZADO** (2026-07-09): `mypy teleflow` (strict) → **0 errores** (33 archivos);
  pytest **26/26** verde. 16 archivos de código modificados. **Sin commitear aún** (pendiente OK).
  - Chunk 1: rename `row`→`entity_row`/`relation_row` en `rules.py` (-5).
  - Chunk 2: `dsl/transformer.py` 180→0 (`c: list`→`list[Any]`, `-> tuple`→`tuple[Any,...]`,
    `Transformer[Token, Any]`, 4 `no-any-return` con cast).
  - Chunk 3: 51→0 — genéricos `dict/list/tuple/Task` parametrizados; lifespans
    `-> AsyncIterator[None]`; `no-any-return` con `bool()`/`cast`; firmas de `view360`
    tipadas; `false()` en vez de `False` en `or_()`; ignore no usado quitado en `entities.py`.
  - networkx: no publica stubs compatibles con py3.11 (arrastran numpy 3.12). Resuelto con
    `[[tool.mypy.overrides]] module="networkx.*" ignore_missing_imports=true` en pyproject.

## Next Steps
- [x] Chunk 1/2/3 → 0 errores, verificado. pytest 26/26.
- [x] Commit local `13f2907` en rama `chore/mypy-strict-clean` (17 archivos, sin push).
- [ ] (owner) push cuando corresponda — nunca automático.
- [ ] (opcional) Correr `mypy` en Python 3.11 real (esta sesión usó 3.14) para confirmar sin
      ruido de versión.
- [ ] (al cerrar) marcar el work-stream como `completed` con resumen y aprendizajes.

## Decisions
- Se ataca por chunks incrementales, verificando `pytest` verde tras cada uno.
- networkx queda como `ignore_missing_imports` — ver [[2026-07-09-mypy-networkx-override]].

## Sources
- Diagnóstico: [[2026-07-09-validacion-doc-vs-codigo]].
- `teleflow/dsl/transformer.py`, `teleflow/executor_service/rules.py`, `teleflow/common/models.py`.

## Log
- 2026-07-09: creado (derivado del onboarding).
- 2026-07-09: chunk 1 — rename en `rules.py`; mypy 236→231; pytest 26/26.
- 2026-07-09: chunk 2 — `transformer.py` 180→0; mypy total 231→51; pytest 26/26.
- 2026-07-09: chunk 3 — 51→0; override networkx en pyproject; **mypy strict 0 errores**; pytest 26/26.
- 2026-07-09: commit local `13f2907` en rama `chore/mypy-strict-clean` (17 archivos código; sin push).
- 2026-07-09: **CERRADO** (`status: completed`).

## Cierre

**Qué se logró (hechos):**
- `mypy teleflow` (strict) **236 → 0 errores** (33 archivos); `pytest` **26/26** verde en cada chunk.
- 16 archivos de código + `pyproject.toml` modificados, **sin cambios de comportamiento**.
- Commit local `13f2907` en rama `chore/mypy-strict-clean` (sin push, sin trailer de IA).

**Cómo (por chunks incrementales, verificando pytest tras cada uno):**
- Genéricos parametrizados (`dict[str, Any]`, `list[Any]`, `tuple[Any, ...]`, `asyncio.Task[Any]`).
- Transformer de Lark tipado (`Transformer[Token, Any]`, `c: list[Any]`) — 180 errores de un solo archivo.
- `no-any-return` con `bool()`/`cast`; lifespans `-> AsyncIterator[None]`; firmas de `view360` tipadas.
- `false()` en vez de `False` dentro de `or_()`; ignore obsoleto quitado en `entities.py`.
- networkx: `[[tool.mypy.overrides]] ignore_missing_imports` (sus stubs arrastran numpy 3.12).

**Aprendizajes:**
- El grueso de la deuda de tipado estaba concentrado (180/236 en `transformer.py`, patrón único
  `c: list` → `list[Any]`): un saneamiento aparentemente enorme fue en realidad muy mecánico.
- Instalar stubs de terceros puede romper más de lo que arregla (types-networkx → numpy 3.12
  incompatible con el target 3.11); el override de mypy fue la vía limpia.
- La verificación se hizo con Python 3.14 (venv de sesión); el target es 3.11. No se esperan
  diferencias, pero confirmarlo en 3.11 real quedó como paso opcional pendiente.

**Trabajo derivado / pendiente (fuera de este work-stream):**
- (owner) push de la rama cuando corresponda — nunca automático.
- (opcional) correr `mypy` en Python 3.11 real.
- (opcional) considerar un hook/CI que corra `mypy --strict` para que no vuelva a degradarse.
