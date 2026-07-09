---
project: copp-ia
status: completed
created: 2026-06-30
updated: 2026-07-09
tags: [onboarding, arquitectura, roadmap, contexto-base]
---

# Onboarding copp-ia

## Goal
Asimilar la visión y la arquitectura del arquitecto de copp-ia (TeleFlow Platform),
fijar el contexto base del proyecto y planificar un roadmap de trabajo.

## Context
copp-ia / TeleFlow Platform — "Business & Software as Code": orquestación empresarial para
modelar, desplegar y ejecutar procesos de negocio como código declarativo (`.tflow`).
Se instancia por organismo (no es SaaS). Single-repo en GitHub.

Stack: Python 3.11, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, Pydantic v2, structlog,
Redis, RabbitMQ (aio-pika), Prometheus. Parser DSL con Lark (LALR). `review-ui` en React.
CLI `tflow`.

Servicios (docker-compose): api-gateway (8000), parser-service (8001),
executor-service (8002), registry-service (8003), composer-service (8004), review-ui (3100).

Estado inicial: vault y repo recién creados (Initial commit). Sin historial previo de trabajo.

## Current State
- Visión y arquitectura asimiladas y **validadas contra código** (`copp-ia@main@6046648`).
- Knowledge poblado: [[teleflow-plataforma]], 5 ADRs, e investigación
  [[2026-07-09-validacion-doc-vs-codigo]].
- Hechos clave: código de Fases 1-3 presente y cableado; **pytest 26/26 ✅**;
  **mypy --strict falla (236 errores) ❌**; 4 discrepancias doc↔código registradas.
- Regla derivada: ante conflicto, **código > `.typ` > `.md`/README**.

## Next Steps
- [ ] Decidir si se ataca `mypy --strict` (empezar por `dsl/transformer.py`, 180/236 errores;
      incluir rename `row`→`entity_row`/`relation_row` en `rules.py`).
- [x] Investigar el lead de `executor_service/rules.py:132-141` → **falso positivo**, no bug
      (ver [[2026-07-09-validacion-doc-vs-codigo]]).
- [ ] Correr la suite en Python 3.11 real (el `.venv` de esta sesión es 3.14) para descartar
      ruido de versión en mypy.
- [ ] (opcional) Registrar la actualización pendiente del `.md`/README (Grafana 3001, `stub`).

## Decisions
- Volcado a Knowledge hecho de forma deliberada tras validar contra código (no solo doc).

## Sources
- `docs/TeleFlow-Arquitectura-v1.0.md`, `docs/teleflow-{vision,adr,dsl-reference,deployment}.typ`
- `README.md`, `docker-compose.yml`, `.env.example`
- `teleflow/{gateway,composer_service,executor_service}/…`
- Salida de `pytest` (26 passed) y `mypy` (236 errores), sesión 2026-07-09.

## Log
- 2026-06-30: creado
- 2026-07-09: leída y asimilada la doc del arquitecto; validado código vs doc; poblado
  Knowledge (plataforma + 5 ADRs + investigación). Tests 26/26, mypy strict falla.
- 2026-07-09: investigado el lead de `rules.py` → falso positivo de mypy, no bug.
- 2026-07-09: **CERRADO** (`status: completed`).

## Cierre

**Qué se logró (hechos):**
- Asimilada la visión/arquitectura de TeleFlow y **validada contra código** (`copp-ia@main@6046648`).
- Conocimiento durable en `Knowledge\`: [[teleflow-plataforma]], los 5 ADRs, e investigación
  [[2026-07-09-validacion-doc-vs-codigo]]. Índice actualizado.
- Verificado en sesión: `pytest` **26/26 passed**; `mypy --strict` **falla (236 errores)**.
- Resueltas 4 discrepancias doc↔código (Grafana 3001, rule engine/view360 en executor,
  `stub` como 4º provider LLM, mypy no pasa strict) + 1 dato (`claude-fable-5`).
- El único hilo con potencial de bug (`rules.py:132-141`) quedó **descartado con evidencia**
  como falso positivo de tipado.

**Aprendizajes:**
- Regla operativa para este repo: ante conflicto, **código > `.typ` > `.md`/README**
  (los docs consolidados están más viejos que el código).
- El "verde" de los tests no cubre el rule engine con DB; una afirmación de la doc
  ("mypy --strict, sin `Any`") resultó no cumplirse — conviene validar, no asumir.
- La estructura de Fases 1-3 está completa y cableada; Fase 4 en progreso.

**Trabajo nuevo derivado (fuera de este work-stream):** saneamiento `mypy --strict`
(empezar por `dsl/transformer.py`; incluir rename `row`→`entity_row`/`relation_row`),
correr suite en Python 3.11 real, y patch opcional de `.md`/README.
