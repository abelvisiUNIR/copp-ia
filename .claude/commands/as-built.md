---
description: Escribe o refresca la linea base as-built de un modulo (spec.md y seguridad.md)
argument-hint: <modulo, ej. lenguaje-tflow> [alcance: rutas de codigo]
allowed-tools: Bash(git rev-parse:*)
---

Provenance actual: copp-ia@!`git rev-parse --abbrev-ref HEAD`@!`git rev-parse --short HEAD`

Modulo: $ARGUMENTS

Las lineas base se escriben **bajo demanda**: cuando una feature nueva toca el modulo, no en tanda.
Si el pedido es "todas las bases" o mas de un modulo, no lo ejecutes: pedi a la persona que elija
uno.

Carpeta destino: `spec/features/base-<modulo>/` (crearla si no existe), `status: implementada` y
la provenance de arriba. Si falta el alcance en rutas de codigo, deducilo de la estructura del
repo y decilo antes de empezar.

**De a un subagente, en este orden, esperando que termine cada uno** (nunca en paralelo):

1. `analista-requisitos` en modo **as-built** → `spec.md` (criterios derivados de los tests
   existentes).
2. `seguridad-infra` en modo **as-built** → `seguridad.md`.

Pasale a cada uno solo la carpeta, el alcance en rutas y la provenance. No les pidas leer otras
lineas base enteras como referencia.

Para codigo existente no se escriben `plan.md`, `tasks.md` ni `validacion.md`: esos son del ciclo
de una feature nueva. Si una persona los pide explicitamente para un modulo, se agregan de a uno.

Al final mostra en pocas lineas: criterios totales, cuantos `(sin test)` y huecos de seguridad por
severidad. Nada de esto se sincroniza con Jira.
