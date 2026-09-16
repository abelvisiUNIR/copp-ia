---
description: Etapa 1 SDD — el subagente analista-requisitos escribe o itera el spec.md de una feature
argument-hint: <carpeta-feature> [nuevo|as-built] [descripcion o pedido]
allowed-tools: Bash(git rev-parse:*)
---

Provenance actual: copp-ia@!`git rev-parse --abbrev-ref HEAD`@!`git rev-parse --short HEAD`

Usa el subagente `analista-requisitos` con este pedido: $ARGUMENTS

Pasale la provenance de arriba. Si el pedido no dice la carpeta o el modo (`nuevo` o
`as-built`), preguntalo antes de invocarlo.

Cuando termine, mostra el resumen que devuelva (criterios, inferencias abiertas, preguntas) y
recorda el siguiente paso: `/disenar <carpeta>` una vez respondidas las preguntas.
