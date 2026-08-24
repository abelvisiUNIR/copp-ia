---
project: copp-ia
date: 2026-06-30
status: accepted
provenance: copp-ia@main@6046648
tags: [adr, deployment, multi-tenant, aislamiento]
---

# ADR-005: Aislamiento por instancia — no multi-tenant

> Provenance: `copp-ia@main@6046648`. Fuente: `docs/teleflow-adr.typ:154-166`,
> `TeleFlow-Arquitectura-v1.0.md:866-872`.

## Context
Los organismos públicos requieren datos aislados. Multi-tenancy (RLS, schema switching)
agrega complejidad operativa y de seguridad.

## Decision
Cada organismo tiene su **propia instancia** de TeleFlow con su **propia base de datos**.
Sin row-level security ni schema switching. Aislamiento **físico, no lógico**.

## Rationale
Modelo más simple de operar para organismos con equipos IT propios. Imposible data leak
entre organismos por bug de aplicación. Templates y procesos se comparten vía Git, no vía
DB compartida.

## Consequences
- Actualizaciones vía `git pull` + `docker compose pull` + `up --build` en cada instancia.
  **No hay propagación automática** entre instancias.
- Organismos grandes pueden operar múltiples instancias (ej: una por línea de negocio).
- Refuerza el posicionamiento "no es SaaS, se instancia por organismo".

## Alternatives
Multi-tenant con RLS · multi-tenant con schemas separados · SaaS compartido (contradice el
requisito de datos aislados).

## Sources
`docs/teleflow-adr.typ:154-166` · `TeleFlow-Arquitectura-v1.0.md:866-872`
