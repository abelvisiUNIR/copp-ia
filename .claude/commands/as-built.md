---
description: Escribe o refresca la linea base as-built de un modulo (spec, plan, tasks, validacion, seguridad)
argument-hint: <modulo, ej. lenguaje-tflow> [alcance: rutas de codigo]
allowed-tools: Bash(git rev-parse:*)
---

Provenance actual: copp-ia@!`git rev-parse --abbrev-ref HEAD`@!`git rev-parse --short HEAD`

Modulo: $ARGUMENTS

Carpeta destino: `spec/features/base-<modulo>/` (crearla si no existe). Todos los archivos con
`status: implementada` y la provenance de arriba. Si falta el alcance en rutas de codigo, deducilo
de `spec/README.md` y de la estructura del repo, y decilo antes de empezar.

En orden, pasando a cada uno el modo **as-built**, la carpeta, el alcance y la provenance:

1. `analista-requisitos` → `spec.md` (criterios derivados de los tests existentes).
2. `disenador-tecnico` → `plan.md` (como esta resuelto hoy).
3. `desglosador-tareas` → `tasks.md` (capacidades `[x]` con evidencia).
4. `validador-spec` → `validacion.md` (cobertura de la spec por tests).
5. `seguridad-infra` → `seguridad.md`.

Los pasos 4 y 5 pueden ir en paralelo. Al final mostra: criterios totales, SIN TEST, huecos de
seguridad por severidad e inferencias abiertas. Nada de esto se sincroniza con Jira.
