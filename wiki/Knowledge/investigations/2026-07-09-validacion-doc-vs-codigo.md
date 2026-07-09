---
project: copp-ia
type: investigation
date: 2026-07-09
status: closed
provenance: copp-ia@main@6046648
tags: [validacion, doc-vs-codigo, mypy, tests, onboarding]
---

# Validación doc vs. código — onboarding copp-ia

> Provenance: `copp-ia@main@6046648`. Parte del work-stream [[onboarding-copp-ia]].
> Objetivo: resolver ambigüedades de la doc leyendo el código real.

## Método
Lectura de `docker-compose.yml`, `.env.example`, `gateway/main.py`,
`composer_service/providers.py`, `executor_service/main.py`; conteo y ejecución de tests;
`mypy --strict`. Entorno: `.venv` con **Python 3.14** (el proyecto pinea 3.11), deps `[dev]`.

## Hallazgos (hechos comprobados)

### 1. Tests → 26/26 passed ✅
`pytest -q` → **26 passed en 2.20s**. Coincide con la afirmación de la doc
(`teleflow-deployment.typ:241`). Distribución: `test_parser`=10, `test_evaluator`=7,
`test_validator`=7, `test_dag`=2.

> **Actualización (2026-07-09):** los 236 errores fueron **saneados a 0** en el work-stream
> [[saneamiento-mypy-strict]] (pytest sigue 26/26). Lo de abajo es el diagnóstico inicial.

### 2. `mypy --strict` → 236 errores ❌ (discrepancia — ya resuelta)
La doc declara "mypy --strict, sin `Any` sin justificar" como convención vigente
(`teleflow-deployment.typ:261`, `.md` §10), pero **el código no pasa hoy**:

| Categoría | Nº |
|---|---|
| `type-arg` | 202 (180 en `dsl/transformer.py`) |
| `no-any-return` | 13 |
| `no-untyped-def` | 12 |
| `attr-defined` | 4 (`executor_service/rules.py:137-141`) |
| `arg-type` | 2 (`rules.py:132`) |
| otros | 3 (`import-untyped`: falta `types-networkx`, etc.) |

Caveat: corrió con mypy actual sobre Python 3.14, no el 3.11 pineado. Pero el grueso
(`type-arg`, `no-untyped-def`) no depende de versión/stubs → gaps de anotación reales.
**Conclusión sólida: no pasa `mypy --strict`.**

### 3. Grafana escucha en host 3001, no 3000
`docker-compose.yml:152` → `"${GRAFANA_PORT:-3001}:3000"` con comentario explícito.
El `.md` §9.2 y `README.md:33` dicen 3000 (obsoletos). El `.typ` y el código coinciden en 3001.

### 4. rule engine / view360 viven en executor-service, no en gateway
El gateway es proxy puro: `/entities/{rest:path}` (incluye `.../360`) y `/relations/*` →
`executor_url` (`gateway/main.py:198-207`). `RuleEngine`, `EntityService`, `View360Service`
se instancian en `executor_service/main.py:45-57`. El diagrama `.md` §7.1 es vista lógica,
no ubicación física. `README.md:15` es correcto.

### 5. `stub` es el 4º proveedor LLM oficial (y default del compose)
`composer_service/providers.py` implementa las 4 clases; `get_provider()` cae a Stub sin
API key. Default anthropic model = **`claude-fable-5`**. La tabla `.md` §9.3 omite `stub`.

## Lead investigado → RESUELTO: falso positivo, no es bug (hecho comprobado 2026-07-09)
`executor_service/rules.py:132-141` (`_build_context`). Los 5 errores de mypy
(`arg-type` + `attr-defined`) son **artefacto de reusar la variable local `row` para dos
modelos ORM distintos** en ramas mutuamente excluyentes:
- rama entity (`:121-128`): `row = session.scalar(select(EntityState)…)` → mypy fija
  `row: EntityState | None`;
- rama relation (`:129-142`): `row = session.get(RelationState, rid)` → reasigna, pero mypy
  ya clavó el tipo a `EntityState` y se queja de `.from_id`/`.to_id`.

**A runtime es correcto:** `subject_kind` es un único string ("entity" | "relation"), las
ramas nunca coexisten; en la rama relation `get(RelationState, …)` devuelve un `RelationState`
y `.from_id/.to_id/.campos/.estado/.id` existen en ese modelo (`common/models.py:119-130`).

Caminos adyacentes verificados y correctos: `on_relation` (evento sintético
`relation.{tipo}.created` en `entities.py:290-291` ↔ matcher `rules.py:79-82`), `on_timer`
sobre relations (`_check_timer_event` → `subject_kind="relation"`), binding consumer `#`
(`events.py:63`).

**Fix sugerido (higiene, prioridad baja):** renombrar a `entity_row`/`relation_row`.
Elimina 5/236 errores. Va dentro del work-stream de `mypy --strict`, no uno propio.

## Conclusión
La doc es fiel en arquitectura y comportamiento (tests verdes confirman el motor), pero:
- **sobre-declara el estado de typing** (mypy no pasa),
- el **`.md`/PDF consolidado y el README están más desactualizados** que los `.typ` y el
  código (Grafana port, `stub`, ubicación lógica de view360).

**Regla práctica derivada:** ante conflicto, **código > `.typ` > `.md`/README**.

## Próximos pasos sugeridos
- [ ] Decidir si se arregla `mypy --strict` (empezar por `dsl/transformer.py`; incluir el
      rename `row`→`entity_row`/`relation_row` en `rules.py`).
- [x] ~~Investigar el lead de `rules.py:132-141`~~ → falso positivo (ver arriba).
- [ ] Correr la suite en Python 3.11 real para descartar ruido de versión.

## Sources
`docker-compose.yml` · `.env.example` · `teleflow/gateway/main.py` ·
`teleflow/composer_service/providers.py` · `teleflow/executor_service/main.py` ·
`teleflow/executor_service/rules.py` · salida de `pytest` y `mypy` (sesión 2026-07-09)
