---
description: Revision en solo lectura del cambio actual con el subagente revisor
argument-hint: <carpeta-feature> [tarea] [base-git, por defecto el working tree]
---

Usa el subagente `revisor` para revisar: $ARGUMENTS

Si no se indica base, revisa el working tree contra `HEAD`. Mostra el veredicto (APROBADO /
CAMBIOS REQUERIDOS) y los hallazgos ordenados por severidad, sin reescribir codigo.
