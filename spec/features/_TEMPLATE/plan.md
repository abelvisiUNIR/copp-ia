---
project: copp-ia
type: plan
status: borrador
feature: <slug-kebab-case>
provenance: copp-ia@<rama>@<sha-corto>
created: <YYYY-MM-DD>
---

<!-- status: borrador | consolidada | implementada (linea base as-built) -->
<!-- Lo escribe el subagente `disenador-tecnico` (comando /disenar). En as-built, "Enfoque" y
     "Archivos que toca" describen como esta resuelto hoy, con cita. -->


# Plan de implementacion — <Nombre de la feature>

## Enfoque

Como se va a resolver, en 3-5 lineas. Si se descarto otro enfoque, decir cual y por que — eso
despues puede convertirse en un ADR.

## Archivos que toca

| Archivo | Cambio |
|---|---|
| `teleflow/...` | |

## Reutiliza

Lo que ya existe y no hay que volver a escribir (con ruta). Es la parte del plan que mas ahorra:
buscar antes de proponer codigo nuevo.

-

## Migraciones

Alembic si / no. Si si: que tabla, y si el cambio es compatible hacia atras (los pods viejos
conviven con el schema nuevo durante un upgrade).

## Tests

- Unitarios:
- e2e (`-m e2e`):

Sin tests el gate no alcanza: `mypy` no ve comportamiento.

## Riesgos

| Riesgo | Mitigacion |
|---|---|
| | |

## Verificacion

Como se comprueba end-to-end que quedo bien. Comandos concretos, ejecutables.

```
mypy .
pytest -m "not e2e" -q
```
