---
project: copp-ia
type: mission
provenance: copp-ia@desarrollo@15185e9
fuente: README.md:1-9, docs/teleflow-vision.typ, docs/TeleFlow-Arquitectura-v1.0.md
updated: 2026-09-13
---

# Mision — TeleFlow Platform

> Espejo de `README.md` y `docs/teleflow-vision.typ`. Ante conflicto, manda el codigo y
> despues el `.typ`. Este archivo existe para dar contexto de producto al agente cuando
> redacta specs y cards; no es la fuente de verdad.

## Que es

**Business & Software as Code.** Plataforma de orquestacion empresarial que permite modelar,
desplegar y ejecutar procesos de negocio como codigo declarativo (`.tflow`), con el mismo rigor
con que Terraform gestiona infraestructura (`README.md:3`).

## Que no es

**No es SaaS.** Se instancia por organismo (ADR-005): el mismo `docker-compose.yml` y los mismos
Helm charts sirven a todos (`README.md:7`). Esa decision condiciona todo: no hay multi-tenancy,
la capa de datos puede ser del organismo, y el criterio de salida de una feature incluye que
siga siendo instalable sin overrides.

## Objetivos del owner, en orden de madurez

Tomados de `wiki/Knowledge/roadmap.md:16-21`:

1. Entender y aprender la app.
2. Endurecer la calidad del codigo.
3. Proponer mejoras que la mejoren.
4. Llevar a produccion cuando haya un producto estable y de calidad.

## Criterios que una feature tiene que respetar

- **El deploy sigue siendo reproducible por organismo**, con el checklist de
  `docs/checklist-instalacion.md` en verde.
- **Los limites se escriben, no se omiten.** Lo que queda afuera a proposito va documentado como
  decision consciente, no como silencio. Es el patron de todos los items cerrados del roadmap.
- **Nada llega a produccion sin CI en verde**: `mypy .` strict en 0 y `pytest` completo.
