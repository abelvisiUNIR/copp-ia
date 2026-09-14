# Especificaciones — Spec-Driven Development

Este directorio es donde se especifica **cada funcionalidad del producto**, con el mismo formato
para lo que ya esta en el codigo y para lo que va a hacerse. Cada etapa del ciclo tiene un archivo,
un subagente que lo escribe y un comando que lo invoca.

## Que hay en `spec/features/`

| Carpeta | `status` | Que es | Jira |
|---|---|---|---|
| `base-<modulo>/` | `implementada` | **Linea base as-built**: lo que hoy hace el codigo, derivado del codigo y sus tests | Nunca se sincroniza |
| `<CLAVE-PADRE>-<slug>/` | `borrador` → `consolidada` → `sincronizada` | **Feature futura** | Cards via `/sync-jira` |
| `_TEMPLATE/` | — | Plantillas de los cinco archivos | — |

La linea base existe para que una feature nueva parta de lo que el codigo realmente hace y no de
la memoria de alguien. Envejece como cualquier doc: **al cambiar el codigo de un modulo, se
actualiza su `base-*` en el mismo commit**. Ante conflicto, manda el codigo.

## Deslinde con `wiki/`

| | `spec/` | `wiki/Knowledge/` |
|---|---|---|
| Que | Que hace cada funcionalidad y que va a hacer | Por que se decidio asi |
| Formato | spec → plan → tasks → validacion → seguridad | ADRs, roadmap, conceptos, guias |

Una decision de diseño que sobrevive a la feature **no se queda en `spec/`**: se promueve a un
ADR en `wiki/Knowledge/decisions/`. El roadmap real sigue siendo `wiki/Knowledge/roadmap.md`.

## Etapas del ciclo

| Etapa | Archivo | Subagente (`.claude/agents/`) | Comando |
|---|---|---|---|
| Analisis de requisitos | `spec.md` | `analista-requisitos` | `/especificar` |
| Diseño / plan tecnico | `plan.md` | `disenador-tecnico` | `/disenar` |
| Desglose de tareas | `tasks.md` | `desglosador-tareas` | `/desglosar` |
| Implementacion IA | codigo + tests | `implementador` | `/implementar` |
| Revision | informe | `revisor` (solo lectura) | `/revisar` |
| Testing: validacion contra spec | `validacion.md` | `validador-spec` | `/validar` |
| Seguridad e infraestructura (transversal) | `seguridad.md` | `seguridad-infra` | `/seguridad` |

`/as-built <modulo>` encadena analista, diseñador, desglosador, validador y seguridad en modo
as-built para escribir o refrescar una carpeta `base-*`.

```
spec.md   ── que se quiere y como se sabe que esta bien (criterios de aceptacion)
   ↓
plan.md   ── como se va a implementar, que archivos toca, que riesgos tiene
   ↓
tasks.md  ── desglose en tareas chicas y verificables
   ↓
status: consolidada     → el hook avisa que hay tareas sin card
   ↓
/sync-jira (dry-run)    → se revisa el listado y se confirma
   ↓
status: sincronizada    → cada linea lleva su [CLAVE-N] de Jira
   ↓
por cada tarea: implementador → revisor → validador   (tope 3 vueltas, despues se escala)
   ↓
validacion.md + seguridad.md en verde → PR
```

**El ciclo se autocorrige, pero no se engaña.** Un hallazgo del revisor o un criterio NO CUMPLE
vuelve al implementador con el informe. Nadie "arregla" bajando un criterio, borrando un test o
relajando una validacion: eso es una falla silenciosa
(`wiki/Knowledge/concepts/fallas-silenciosas.md`) y el revisor la rechaza por regla.

## Crear una feature

```bash
cp -r spec/features/_TEMPLATE spec/features/BPF-12-autenticacion
```

El nombre de la carpeta es `<CLAVE-PADRE>-<slug-kebab-case>`. La epica o historia padre la crea
una persona en Jira: el agente nunca crea Epics. Mientras no exista, la carpeta puede llamarse
solo `<slug>` con `jira_parent: <pendiente>`, y se renombra cuando llega la clave.

Mientras se itera, el `tasks.md` queda en `status: borrador`. Pasarlo a `consolidada` es el acto
deliberado que dice "esto ya no se discute mas, convertilo en tickets".

## Contrato del `tasks.md`

Lo lee `.claude/hooks/spec_consolidada.py` y lo escribe la skill `sync-jira`:

- Una tarea es una linea de lista con checkbox: `- [ ] Texto`.
- Una tarea **sin** `[CLAVE-N]` no tiene card todavia.
- Una tarea **con** `[CLAVE-N]` ya se sincronizo y no se vuelve a crear nunca. Esa marca es la
  unica proteccion contra duplicar el backlog: no se borra a mano.
- El texto de una tarea ya sincronizada no se reescribe: tiene que seguir matcheando el summary
  que esta en Jira.
- En la linea base (`implementada`) cada tarea es `- [x]` y lleva su evidencia: la cita al codigo
  y el test que la prueba.

## Estados

| `status` | Significado |
|---|---|
| `borrador` | Todavia se esta iterando. El hook no hace nada. |
| `consolidada` | Cerrada funcionalmente. Falta crear las cards. |
| `sincronizada` | Todas las tareas tienen su clave de Jira. |
| `implementada` | Linea base as-built. El hook y `/sync-jira` la ignoran. |
