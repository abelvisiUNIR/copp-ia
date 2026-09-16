---
project: copp-ia
type: validacion
status: borrador
feature: <slug-kebab-case>
provenance: copp-ia@<rama>@<sha-corto>
validated: <YYYY-MM-DD>
---

# Validacion contra la spec — <Nombre de la feature>

<!--
  status: borrador | implementada (linea base as-built)
  Lo escribe el subagente `validador-spec`. No escribe tests: un criterio sin test vuelve al
  implementador. Un criterio NO CUMPLE nunca se "arregla" editando la spec para que calce.
-->

## Gates ejecutados

| Comando | Resultado | Fecha | Commit |
|---|---|---|---|
| `mypy .` | | | |
| `pytest -m "not e2e" -q` | | | |
| `pytest -m e2e -q` | no ejecutado / resultado | | |

Si un gate no se corrio (por ejemplo, e2e sin el stack levantado), se escribe "no ejecutado" y el
motivo. Nunca se da por verde lo que no se corrio.

## Matriz criterio → evidencia

Un renglon por cada criterio de aceptacion de `spec.md`, copiado literal.

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 1 | | `tests/test_x.py::test_y` | CUMPLE / NO CUMPLE / SIN TEST |

## Criterios sin test

Lo que la spec promete y ningun test comprueba. Cada uno es trabajo pendiente, no un detalle.

-

## Comportamiento observado que la spec no menciona

Tests que prueban algo que ningun criterio pide. Puede ser un criterio que falta en la spec o un
test que sobra: se anota, no se decide aca.

-
