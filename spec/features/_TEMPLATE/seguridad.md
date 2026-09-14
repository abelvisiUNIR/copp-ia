---
project: copp-ia
type: seguridad
status: borrador
feature: <slug-kebab-case>
provenance: copp-ia@<rama>@<sha-corto>
reviewed: <YYYY-MM-DD>
---

# Seguridad e infraestructura — <Nombre de la feature>

<!--
  status: borrador | implementada (linea base as-built)
  Lo escribe el subagente `seguridad-infra`. Nunca copia un secreto, ni siquiera de ejemplo:
  si aparece uno en el codigo, se cita la ruta y se escribe [REDACTED].
-->

## Superficie expuesta

Endpoints, colas, puertos o archivos que la feature abre o consume. Con ruta y scope.

| Superficie | Quien puede llegar | Control | Fuente |
|---|---|---|---|
| `METODO /ruta` | | scope `x:y` | `archivo.py:linea` |

## Controles existentes

Lo que ya protege, con cita. Solo lo comprobado en el codigo.

-

## Huecos

Lo que falta o es riesgo. Cada uno con evidencia (o marcado `(inferencia)`) y severidad.

| Hueco | Severidad | Evidencia |
|---|---|---|
| | alta / media / baja | |

## Datos personales

Que datos personales toca la feature, donde se persisten (tabla), a donde viajan (bus, logs, LLM
externo) y si quedan en `audit_log`.

## Secretos y configuracion

Variables de entorno que usa, defaults inseguros, como llegan en el chart (`existingSecret`) y en
el compose.

## Impacto en despliegue

Cambios en `docker-compose.yml`, `helm/teleflow/`, migraciones Alembic, CI. Si la feature sigue
siendo instalable por organismo sin overrides (`spec/constitution/mission.md`).
