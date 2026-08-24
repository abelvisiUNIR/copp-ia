---
project: copp-ia
date: 2026-06-30
status: accepted
provenance: copp-ia@main@6046648
tags: [adr, rabbitmq, eventos, deployment]
---

# ADR-004: RabbitMQ incluido en el stack

> Provenance: `copp-ia@main@6046648`. Fuente: `docs/teleflow-adr.typ:140-152`,
> `TeleFlow-Arquitectura-v1.0.md:858-864`. Implementación: `docker-compose.yml`, `teleflow/executor_service/events.py`.

## Context
El bus de eventos de dominio permite que sistemas externos se suscriban sin acoplamiento.
Depender del broker del organismo bloquearía el onboarding inicial.

## Decision
RabbitMQ se incluye como **servicio propio** en docker-compose y Helm. No se depende del
broker del organismo para la instalación inicial.

## Rationale
`docker compose up` funciona sin config externa. Los organismos con broker propio pueden
apuntar `RABBITMQ_URL` al externo — migración = cambio de config, no de código.

## Consequences
- Stack autosuficiente desde el primer día.
- (hecho) `rabbitmq:3.13-management-alpine` en `docker-compose.yml:44-55`, management UI en
  `:15672`. El executor usa **aio-pika**; **topic exchange** con routing key = nombre del
  evento (`nino.activado`, `inscripcion.activada`, …) — `executor_service/events.py`.

## Alternatives
Kafka (sobre-dimensionado) · broker del organismo (bloquea onboarding) · sin broker
(Postgres NOTIFY, limita integración externa).

## Sources
`docs/teleflow-adr.typ:140-152` · `docker-compose.yml:44-55` · `teleflow/executor_service/events.py`
