---
project: copp-ia
type: tasks
status: borrador
jira_site: bpfocus.atlassian.net
jira_project: <CLAVE>
jira_parent: <CLAVE-N>
synced:
---

# Desglose de tareas — <CLAVE-N> <Nombre de la feature>

<!--
  status: borrador → consolidada → sincronizada
          implementada = linea base as-built (carpetas base-*): no se sincroniza nunca

  Pasar a `consolidada` es el acto deliberado que dispara la creacion de cards.
  Mientras diga `borrador`, el hook no hace nada.
  Lo escribe el subagente `desglosador-tareas` (comando /desglosar).

  Una tarea con [CLAVE-N] ya tiene su card y NO se vuelve a crear nunca.
  Esa marca es la unica proteccion contra duplicar el backlog: no borrarla a mano.
  El texto de una tarea ya sincronizada tampoco se reescribe: tiene que seguir
  matcheando el summary que quedo en Jira.
-->

- [ ] Primera tarea, en imperativo y en español
- [ ] Segunda tarea
