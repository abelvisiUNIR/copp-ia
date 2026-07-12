---
project: copp-ia
status: active
created: 2026-07-11
updated: 2026-07-11
tags: [fase-b, ci, github-actions, calidad]
---

# Fase B — CI (GitHub Actions)

## Goal
Red de seguridad automatizada: en cada push/PR a `desarrollo` y `devyos`, correr
`pytest` + `mypy --strict` (en **Python 3.11 real**) + `docker build`. Gate en PR a `desarrollo`.
Cierra la Fase B del [[roadmap]].

## Context
Rama `chore/ci-pipeline` desde `devyos`. Los 26 tests son unitarios (parser/validador/
evaluador/DAG) → **no necesitan Postgres/Redis/RabbitMQ** (los de integración son Fase C).
La CI corre en 3.11 (target del proyecto); la sesión local usa 3.14, así que la validación
local es proxy y el 3.11 real recién corre en GitHub al pushear.

## ⏸ Retomar aquí (próxima sesión)
Fase B está **hecha del lado del código** (workflow commiteado en `chore/ci-pipeline`,
validado local). Falta **solo acción del owner en GitHub** (push + branch protection).
**Próximo trabajo real: Fase C** (tests de integración del runtime). Antes, decidir si
mergear `chore/ci-pipeline` → `devyos`.

## Current State
- **`.github/workflows/ci.yml` creado y validado localmente.** Dos jobs:
  - `quality`: setup Python 3.11 + `pip install -e .[dev]` + `mypy teleflow` + `pytest -q`.
  - `docker-build`: `docker build -t teleflow:ci .`.
- Validación local (proxy en 3.14): YAML OK, mypy 0, pytest 26/26, docker build OK (345MB).
- Falta: commit local (sin push). El 3.11 real y el gate corren en GitHub al pushear.

## Next Steps
- [x] `.github/workflows/ci.yml`: job quality (mypy+pytest en 3.11) + job docker-build.
- [x] Validar comandos localmente (venv 3.14, proxy).
- [ ] Commit local (sin push).
- [ ] (owner) al pushear: confirmar que corre verde en 3.11 y activar branch protection en `desarrollo`.

## Log
- 2026-07-11: creado. Rama `chore/ci-pipeline` desde `devyos`.
- 2026-07-11: workflow CI creado y validado (mypy 0, pytest 26/26, docker build OK).
