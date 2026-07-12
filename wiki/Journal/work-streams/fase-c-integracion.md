---
project: copp-ia
status: active
created: 2026-07-12
updated: 2026-07-12
tags: [fase-c, tests, integracion, e2e, calidad]
---

# Fase C — Tests de integración del runtime

## Goal
Cubrir el runtime (engine, durable sleep, entities/relations, rules, view360) que hoy no
tienen tests. Cierra el hueco #1 de calidad del [[roadmap]].

## Context
Rama `test/fase-c-integracion` (desde `devyos`, que ya trae Fase B/CI). Enfoque del primer
chunk: **e2e contra el gateway** (httpx), automatizando los 2 flujos de [[flujos-negocio]].

## Current State
- **Chunk 1 hecho:** suite e2e en `tests/e2e/` (auto-skip si no hay stack).
  - `test_durable_sleep_e2e.py`: WAITING_SIGNAL → signal approve → COMPLETED; y señal sobre
    instancia completada rechazada.
  - `test_event_driven_e2e.py`: entity→activar→(regla dispara proceso)→inscripción→Vista 360.
  - `conftest.py`: fixtures `client`, `deployed` (deploy + espera cache 30s si nuevo),
    `poll_status`, `count_instances`, `poll_count`.
- Marker `e2e` registrado en `pyproject.toml`.
- CI extendida: job `quality` corre `pytest -m "not e2e"`; **nuevo job `e2e`** levanta el stack
  (`docker compose up -d`), espera readiness y corre `pytest -m e2e`.
- **Verificado local (stack arriba):** e2e 3/3, unit 26/26, full 29/29, mypy 0, YAML OK.

## Next Steps
- [x] Chunk 1: e2e de los 2 flujos + CI job e2e.
- [x] Chunk 3: adapters (rest/smtp/noop/notification) con mocks + casos de error.
      `tests/test_adapters.py` (10 tests, unitarios, sin infra). unit 36, full 39, mypy 0.
- [ ] Chunk 2 (propuesto): tests de componente con testcontainers (engine/entities/rules
      contra Postgres/Redis reales, sin HTTP) — más hermético.

## Log
- 2026-07-12: creado. Rama `test/fase-c-integracion` desde `devyos`.
- 2026-07-12: chunk 1 — suite e2e + CI job e2e; e2e 3/3, unit 26/26, mypy 0.
- 2026-07-12: chunk 3 — tests de adapters con mocks (10). unit 36, full 39, mypy 0.
