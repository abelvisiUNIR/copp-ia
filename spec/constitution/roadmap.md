---
project: copp-ia
type: roadmap-espejo
provenance: copp-ia@desarrollo@15185e9
fuente: wiki/Knowledge/roadmap.md
updated: 2026-09-13
---

# Roadmap — espejo a nivel epica

> ⚠️ **Este archivo NO es la fuente de verdad.** El roadmap real, con el detalle de cada item,
> su evidencia y sus limites conscientes, vive en `wiki/Knowledge/roadmap.md` y se actualiza
> ahi. Este espejo existe solo para mapear fases → epicas de Jira.
>
> Si los dos discrepan, gana el de la wiki. Si este quedo viejo, se regenera; no se "arregla"
> editando solo aca.

## Fases y su epica en Jira

La clave de epica la crea una persona en `bpfocus.atlassian.net` y se pega en la tabla. Mientras
la celda diga `—`, las features de esa fase no tienen padre y **no se pueden sincronizar**.

| Fase | Estado en la wiki | Epica Jira |
|---|---|---|
| A — Entender la app | ✅ cerrada 2026-07-11 | — |
| B — Red de seguridad: CI | 🔶 casi cerrada (pendiente accion del owner en GitHub) | — |
| C — Endurecer calidad | ✅ cerrada 2026-07-12 | — |
| D — Mejoras / ideas | en curso, selectiva | — |
| E — Produccion | ✅ cerrada 2026-08-18 | — |
| F — Futuro / opcional (Fase 4 del arquitecto) | no arrancada | — |

## Lo que queda abierto segun la wiki

Insumo para las proximas specs. Cada uno se verifica contra `wiki/Knowledge/roadmap.md` antes de
convertirse en feature — pueden haberse cerrado despues de la fecha de este espejo.

- **Fase B**: branch protection en `desarrollo` exigiendo el check `CI / quality` (accion del
  owner en GitHub, no es codigo).
- **Fase C**: tests de adapters (rest/amqp/smtp) con mocks; actualizar README/docs con las
  discrepancias pendientes.
- **Fase D**: mejores mensajes de error del parser; validacion semantica extra en
  `validator.py` (refs a process/step inexistentes); coleccion `.http`; hardening del prompt
  del composer y templates TMForum; circuit breaker en REST; UI operativa minima.
- **Fase E**: TLS interno entre servicios (escrito como decision, no omitido).
- **Fase F**: plugin VS Code (Tree-sitter + highlighting); 6 templates TMForum; multiples
  instancias por linea de negocio.
- **Transversal**: `wiki/Knowledge/backlog-hardening.md` (auditoria persistida,
  `registry-service` sin tests, rate limit por proceso, `/execute` sin idempotencia,
  `review-ui` sin red de seguridad).

## Regla de orden

De `wiki/Knowledge/roadmap.md:224-225`: `A → B → C → D → E`. No se pasa a Produccion sin C + D
estables, y D siempre despues de tener CI.
