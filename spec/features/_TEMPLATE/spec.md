---
project: copp-ia
type: spec
status: borrador
feature: <slug-kebab-case>
jira_parent: <CLAVE-N>
created: <YYYY-MM-DD>
---

<!-- status: borrador | consolidada | implementada (linea base as-built, sin jira_parent) -->
<!-- Lo escribe el subagente `analista-requisitos` (comando /especificar). -->


# <Nombre de la feature>

## Problema

Que no funciona hoy, o que no se puede hacer. Con evidencia: ruta y linea del codigo, o el
comportamiento observado. Si es una inferencia, se marca como `(inferencia)`.

## Objetivo

Una frase. El resultado que se quiere, no la implementacion.

## Alcance

**Entra:**
-

**No entra (y por que):**
-

Los limites se escriben, no se omiten. Un "no entra" sin motivo es un pendiente disfrazado.

## Criterios de aceptacion

Cada uno tiene que ser verificable por alguien que no escribio el codigo. Estos criterios se
copian **literales** a la descripcion de las cards de Jira.

- [ ] Dado <contexto>, cuando <accion>, entonces <resultado observable>
- [ ] ...

## Impacto en lo existente

Que se rompe o cambia de comportamiento. Migraciones, cambios de contrato de API, cambios en el
DSL, cambios en el chart.

## Fuentes

- `archivo.py:linea` — que dice
- [[nota-de-la-wiki]]
