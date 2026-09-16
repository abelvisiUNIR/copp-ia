---
description: Etapa 3 SDD — el subagente desglosador-tareas escribe el tasks.md a partir del plan.md
argument-hint: <carpeta-feature> [nuevo|as-built] [jira_project] [jira_parent]
---

Usa el subagente `desglosador-tareas` para: $ARGUMENTS

Si la carpeta no tiene `plan.md`, no lo invoques: indica `/disenar` primero.

Cuando termine, mostra la cantidad de tareas y los criterios sin cubrir. Recorda que pasar el
`tasks.md` a `status: consolidada` lo decide una persona, y que eso dispara `/sync-jira` en
dry-run (nunca crea cards sin confirmacion).
