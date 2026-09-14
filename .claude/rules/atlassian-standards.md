# Reglas de formato para Jira y Confluence

Aplican a todo issue que el agente cree o modifique en `bpfocus.atlassian.net`.

## Sitio

- Sitio: `bpfocus.atlassian.net`
- cloudId: `0941e7ed-5a17-4467-8e47-9e0d04b3ca1d`
- Organizacion: `1e411df7-c7d0-42ef-ac44-efccc0051f41`
- Tools permitidas: **solo `mcp__atlassian__*`** (servidor de `.mcp.json`). Las
  `mcp__claude_ai_Atlassian__*` pertenecen a un conector logueado en otra organizacion y no se
  usan para este Jira.

El proyecto destino **no** se hardcodea aca: sale del `jira_project` del `tasks.md` de cada
feature. Un proyecto equivocado es un backlog ajeno contaminado, asi que si el campo falta la
sincronizacion se detiene en vez de elegir uno.

## Summary

- Español, imperativo, una sola accion por card, maximo 120 caracteres.
- Mismo estilo que los commits del repo: se describe el resultado, no la implementacion.
  - Bien: `Que el gateway declare su security scheme en OpenAPI`
  - Mal: `Modificar main.py para agregar APIKeyHeader`
- Sin la clave de Jira adentro del summary: la clave la asigna Jira.

## Descripcion

Se arma desde `spec.md`, nunca se inventa. Estructura fija:

1. **Contexto**: 2-3 lineas del `## Contexto` de la spec.
2. **Criterios de aceptacion**: copiados literales de la spec, como lista.
3. **Fuente**: ruta del archivo de spec en el repo mas la provenance
   `copp-ia@<rama>@<sha corto>`.

La regla de la wiki vale igual aca: nada inventado, y lo inferido se marca como inferencia
(ver `wiki/README.md:45`).

## Labels

Toda card creada por el agente lleva, sin excepcion:

- `copp-ia` — identifica el producto.
- `spec-driven` — identifica que la card **nacio de una spec del repo**.

`spec-driven` no es decorativa: es la marca de propiedad que autoriza al agente a tocar el
issue mas tarde.

## Lo que el agente no hace

- **No crea Epics.** La epica o historia padre la define una persona y llega por el campo
  `jira_parent`. Una epica creada por error reordena el board de todo el equipo.
- **No edita ni transiciona issues sin la label `spec-driven`.** Es un Jira compartido: lo que
  el agente no creo, no lo toca.
- **No borra issues.** Nunca. Si una card sobra, se cierra o se marca, y lo decide una persona.
- **No pone secretos en descripciones ni en comentarios** (misma regla que la wiki).
- **No crea nada sin confirmacion previa**, ni siquiera una card suelta. El dry-run no es
  opcional.
- **No sincroniza la linea base.** Un `tasks.md` con `status: implementada` (carpetas
  `spec/features/base-*`) documenta lo que ya esta en el codigo: no genera cards.

## Confluence

Si en algun momento se publican las specs a Confluence, la pagina es un **espejo** de la fuente
del repo, con la ruta y la provenance arriba de todo. La fuente de verdad sigue siendo el
archivo versionado: ante conflicto, manda el repo.
