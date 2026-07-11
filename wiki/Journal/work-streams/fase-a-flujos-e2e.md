---
project: copp-ia
status: completed
created: 2026-07-11
updated: 2026-07-11
tags: [fase-a, onboarding, flujos, durable-sleep, demo]
---

# Fase A — Flujos de negocio end-to-end

## Goal
Correr y documentar los 2 flujos de negocio por API para cerrar el ítem pendiente de Fase A
del [[roadmap]]: (1) durable sleep + signal (`venta_internet_hogar`), (2) event-driven Ceibal
(entity→rule→process→360). Entregable: guía reproducible en `Knowledge/guides/`.

## Context
Stack Docker levantado. `ceibal` ya desplegado (v1.0.0). Falta `venta_internet_hogar`.
Cache de dominio del executor = 30 s tras cada deploy.

## Current State
- **Ambos flujos ejecutados en vivo y documentados** en [[flujos-negocio]].
  - Durable sleep (`venta_internet_hogar`): WAITING_SIGNAL → signal approve → COMPLETED ✅.
  - Ceibal event-driven: entities → reglas async → `asignacion_dispositivo` COMPLETED,
    `activacion_acceso_plataforma` FAILED (integración LMS sin env) + Vista 360 ✅.

## Next Steps
- [x] Durable sleep: deploy → execute → WAITING_SIGNAL → signal approve → COMPLETED → idempotencia.
- [x] Ceibal event-driven: entities → activar → inscripción → reglas → Vista 360.
- [x] Volcado a [[flujos-negocio]] y enlazado.
- [ ] (queda de Fase A, aparte) documentar módulos por servicio en `Knowledge/projects/`.

## Log
- 2026-07-11: creado. Objetivo: cerrar el ítem de flujos e2e de Fase A.
- 2026-07-11: corridos ambos flujos en vivo; creada guía [[flujos-negocio]]. Ítem de flujos de Fase A cerrado.
- 2026-07-11: **CERRADO** (`status: completed`) junto con el cierre de Fase A.

## Cierre

**Qué se logró:** ambos flujos de negocio ejecutados en vivo y documentados en [[flujos-negocio]]
(durable sleep + event-driven Ceibal/360). Con esto se cierra **Fase A** del [[roadmap]].

**Aprendizajes:** durable sleep confirmado (WAITING_SIGNAL ↔ reactivación por señal); reglas
async disparan procesos (una COMPLETED, otra FAILED por integración externa sin env — realista);
adapters noop/logged permiten demos sin servicios externos; cache de dominio 30 s; CLI necesita
utf-8 en Windows.

**Promoción a Knowledge:** ya hecha (la guía vive en `Knowledge/guides/`). El ítem de docs por
módulo queda **diferido on-demand** a Fase C, no como deuda abierta.
