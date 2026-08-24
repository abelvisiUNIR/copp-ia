---
project: copp-ia
date: 2026-06-30
status: accepted
provenance: copp-ia@main@6046648
tags: [adr, executor, durable-sleep, redis, postgres]
---

# ADR-002: Durable sleep vía Redis pub/sub + Postgres

> Provenance: `copp-ia@main@6046648`. Fuente: `docs/teleflow-adr.typ:111-124`,
> `TeleFlow-Arquitectura-v1.0.md:841-848`. Implementación: `teleflow/executor_service/`.

## Context
Los procesos pueden esperar un `human_task` días o semanas. Hay que sobrevivir reinicios
del executor sin perder instancias en espera ni consumir recursos con polling.

## Decision
Las instancias en `WAITING_SIGNAL` persisten su contexto completo en **Postgres**
(`context._cursor`). **Redis pub/sub** las reactiva en milisegundos. La señal es
**idempotente** por `signal_key` UNIQUE.

## Rationale
El estado durable en Postgres garantiza que el executor puede reiniciarse sin perder
instancias dormidas. Redis pub/sub da reactivación de ms sin polling. Modelo
conceptualmente idéntico a Temporal.io pero con componentes estándar ya en el stack. La
idempotencia (`signal_key` UNIQUE) garantiza exactamente-una-ejecución con reintentos.

## Consequences
- El executor se suscribe a Redis al arrancar y recupera instancias dormidas desde Postgres
  (`_recover()`).
- En networking inestable (Docker Desktop) el listener usa `get_message` con polling suave
  en lugar de `listen()` bloqueante.
- (hecho) Cableado en el lifespan de `executor_service/main.py:39-66`
  (`ExecutionEngine.start()`); tabla `signals` con `signal_key UNIQUE`.

## Alternatives
Polling activo · timer externo (cron) · Temporal.io (requiere infra + licencia) ·
Celery+Redis (sin estado durable nativo).

## Sources
`docs/teleflow-adr.typ:111-124` · `teleflow/executor_service/engine.py` · `main.py:39-66`
