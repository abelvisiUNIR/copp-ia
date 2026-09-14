---
description: Etapa 2 SDD — el subagente disenador-tecnico escribe el plan.md a partir del spec.md
argument-hint: <carpeta-feature> [nuevo|as-built]
allowed-tools: Bash(git rev-parse:*)
---

Provenance actual: copp-ia@!`git rev-parse --abbrev-ref HEAD`@!`git rev-parse --short HEAD`

Usa el subagente `disenador-tecnico` para: $ARGUMENTS

Pasale la provenance de arriba. Si la carpeta no tiene `spec.md`, no lo invoques: indica
`/especificar` primero.

Cuando termine, mostra archivos que tocaria, migraciones, candidatos a ADR y riesgos abiertos, y
recorda el siguiente paso: `/desglosar <carpeta>`.
