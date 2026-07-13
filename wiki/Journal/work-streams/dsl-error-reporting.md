---
project: copp-ia
status: completed
created: 2026-07-13
updated: 2026-07-13
tags: [fase-d, dsl, parser, validator, error-reporting, dx]
---

# DSL error reporting — mensajes del parser + gaps semánticos

## Goal
Primer ítem de **Fase D** ([[roadmap]]): mejorar el reporte de errores del DSL `.tflow`.
Foco primario en **mensajes del parser** (hoy pobres) y, secundario, cerrar **gaps
semánticos puntuales** que aún faltan en `validator.py`. Cada mejora con tests de casos
inválidos.

## Context
- Rama: `devyos`. Se creará rama `feat/dsl-error-reporting` desde `devyos`.
- Fase B (CI) sigue pendiente del owner (push + branch protection) — no bloquea trabajo de
  código; se asume verde por lo local (mypy 0, 39 tests).
- **Estado real del DSL al abrir** (`repo copp-ia@devyos@3e229f8`):
  - `validator.py` ya es robusto: cubre lifecycle, entity events, invariantes, relations,
    triggers de rule, `process/stage → step` inexistente (**error**), branch a stage/end,
    decision sin branches, notification channel, views. 7 tests en `test_validator.py`.
    ⇒ El ítem del roadmap "refs a process/step inexistentes" **ya está** en su mayor parte.
  - `parser.py` es el gap real:
    - `parse()` (`parser.py:39-57`) da línea/columna + `get_context`, pero **no dice qué se
      esperaba**; `except Exception: pass` (`:46-49`) traga el error de contexto en silencio.
    - `parse_expr()` (`parser.py:59-69`) **descarta el contexto** → solo
      `"Expresión inválida: '<repr>'"`.
    - No distingue `UnexpectedToken` / `UnexpectedCharacters` / `UnexpectedEOF`.
    - Test de sintaxis: 1 solo caso (`test_parser.py:106`, verifica `line is not None`).

## Current State
**Foco primario y secundario HECHOS** en rama `feat/dsl-error-reporting`. Falta solo commit
(pendiente OK owner). mypy 0, suite 50/50.

### Foco primario (mensajes del parser)
`parser.py` reescrito: helper `_raise_syntax_error` centraliza el reporte para `parse` y
`parse_expr`; distingue `UnexpectedToken` / `UnexpectedCharacters` / `UnexpectedEOF`; añade
pista "se esperaba (uno de): …" traduciendo terminales a su literal (`_describe_terminal`
vía `get_terminal`) o etiqueta amigable; `TeleFlowSyntaxError` ahora expone `.expected`
(nombres de terminal, para tooling/tests). `parse_expr` ya da línea/columna/contexto (antes
solo `repr`). Quitado el `except Exception: pass` mudo (context se arma de forma segura).
4 tests nuevos en `test_parser.py`. **mypy 0, suite 43/43 verde (antes 39).** Sin commit aún.

## Next Steps
### Primario — mensajes del parser ✅
- [x] Distinguir los 3 tipos de `UnexpectedInput` y usar `.accepts`/`.expected`
      → "se esperaba uno de: …".
- [x] Arreglar `parse_expr` para que dé línea + contexto como `parse`; quitar el
      `except Exception: pass` mudo.
- [~] `match_examples()` para mensajes canónicos: **diferido** — el enfoque de terminales
      esperados ya da mensajes deterministas y útiles; `match_examples` re-parsea ejemplos y
      puede clasificar mal. Candidato de segunda iteración si aparece un caso frecuente feo.

### Secundario — gaps semánticos ✅
- [x] **Nombres duplicados** (error): el `start()` del transformer sobrescribía en silencio.
      Ahora registra `FlowFile.duplicates` (campo transitorio, `metadata={"transient": True}`,
      excluido de `to_jsonable`) y `validate_flow` emite **error** por cada uno.
- [x] **Triggers de rule con refs inexistentes** (warning, consistente con estilo cross-file):
      `on_event`/`on_timer.since` contra el universo de eventos emitibles (`_emitted_events`:
      emits de entities/relations + `on_complete` de procesos/steps + sintéticos
      `.transitioned`/`relation.*.created`); `on_relation` contra `flow.relations`; `on_state`
      con forma `'<entidad|relación>.<estado>'` validada contra el lifecycle del subject.
      Semántica confirmada leyendo `executor_service/rules.py:74-81,172`.

### Transversal ✅
- [x] Tests de casos inválidos: +4 en `test_parser.py`, +7 en `test_validator.py`.
- [x] **mypy 0 (33 archivos), suite 50/50** (antes 39). Sin falsos positivos en ceibal/venta.
- [ ] Commit (código + wiki) y merge a `devyos` — pendiente de OK del owner (sin push).

## Decisions
- Vehículo: **mini-work-stream, no ADR** — es mejora incremental, no decisión arquitectónica.
- Scope acordado con el owner: parser-first + los 2 gaps semánticos a confirmar.

## Sources
- `teleflow/dsl/parser.py`, `teleflow/dsl/validator.py`, `teleflow/dsl/transformer.py`
- `tests/test_parser.py`, `tests/test_validator.py`
- [[roadmap]] (Fase D)

## Log
- 2026-07-13: creado. Fase D arranca por DSL error reporting. Exploración del DSL registrada
  en Context; gap real = mensajes del parser (validator ya robusto).
- 2026-07-13: rama `feat/dsl-error-reporting` desde `devyos`. **Foco primario hecho**:
  `parser.py` reescrito (mensajes por tipo de error + terminales esperados + `parse_expr` con
  contexto). 4 tests nuevos. mypy 0, 43/43. `match_examples` diferido. Falta: gaps semánticos
  (triggers de rule con refs inexistentes, nombres duplicados) + commit.
- 2026-07-13: **foco secundario hecho**. Duplicados → error (`FlowFile.duplicates` transitorio +
  detección en transformer + validator). Triggers de rule → warnings (`_emitted_events` +
  `_check_rule_trigger_refs`, semántica confirmada en `executor_service/rules.py`). +7 tests de
  validator. mypy 0, **50/50**. Ambos focos cerrados; falta solo commit (OK owner).
- 2026-07-13: commiteado (2 commits: `0a5c9ae` código, `8909fc3` wiki) en
  `feat/dsl-error-reporting` y **mergeado a `devyos`** con `--no-ff` (`03ff11a`). Verde
  post-merge (mypy 0, 50/50). **CERRADO** (`status: completed`).

## Cierre

**Qué se logró:** primer ítem de Fase D. (1) Mensajes del parser reescritos: distingue los 3
tipos de `UnexpectedInput`, traduce terminales a su literal/etiqueta y sugiere "se esperaba uno
de: …", `parse_expr` ahora da contexto, y se quitó el `except: pass` mudo. (2) Validación
semántica extra: nombres duplicados en el mismo archivo → **error** (antes se sobrescribían en
silencio); refs de triggers de rule (`on_event`/`on_timer.since`/`on_relation`/`on_state`) →
**warning**. +11 tests (parser 4, validator 7). mypy 0, suite 39→50. Mergeado a `devyos`
(`03ff11a`), sin push.

**Aprendizajes:**
- El `validator.py` ya era robusto: gran parte del ítem "refs a process/step inexistentes" del
  roadmap ya estaba; el gap real era el **parser**. Lección: verificar el estado real del código
  antes de dimensionar un ítem del roadmap.
- La semántica de los triggers de rule vive en `executor_service/rules.py` (`on_state` =
  `"<subject>.<state>"`, `on_relation` = nombre de relación, `on_event`/`since` = nombre de
  evento). Validar contra el consumidor real evita codificar suposiciones.
- Patrón de validación del proyecto: **error** para refs intra-archivo estructurales, **warning**
  para refs que podrían resolverse en otro flow del dominio (cross-file). Se respetó.
- `metadata={"transient": True}` en un campo de dataclass + skip en `to_jsonable` = forma limpia
  de llevar metadata de parseo sin ensuciar el AST serializado del registry.
- `match_examples()` de Lark quedó **diferido**: el enfoque de terminales esperados ya da
  mensajes deterministas; `match_examples` re-parsea ejemplos y puede clasificar mal.
