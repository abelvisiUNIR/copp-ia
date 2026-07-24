---
project: copp-ia
date: 2026-07-24
status: accepted
provenance: copp-ia@devyos@450c922
tags: [adr, mypy, tipado, calidad, ci, tooling]
---

# ADR (wiki): qué cubre el type check y qué se le exige a cada parte del repo

> Provenance: `copp-ia@devyos@450c922` (commit `5df23ab`). Decisión tomada durante el
> work-stream `saneamiento-comando-tipado`. **No** es un ADR del arquitecto (los suyos son
> ADR-001..005): es una decisión del equipo sobre la red de seguridad del repo.

## Context
El README y `.claude/CLAUDE.md` mandaban `mypy .`; CI (`.github/workflows/ci.yml`) corría
`mypy teleflow`. No era lo mismo:

- **`mypy .` fallaba** con exit code 2:
  `Duplicate module named "conftest" (also at ".\tests\e2e\conftest.py")` seguido de
  `errors prevented further checking` — **cero archivos analizados**. Apareció cuando Fase C
  agregó `tests/e2e/conftest.py` (2026-07-12) y duró 12 días.
- **`mypy teleflow` pasaba**, 0 errores en 35 archivos, y era lo que gateaba.

El fallo era ruidoso, pero por un motivo que se lee como problema de herramientas, no de
código. El atajo razonable —correr el comando de CI, que anda— dejaba fuera del radar los 23
archivos de `tests/`, y eso no se notaba porque nada lo reportaba: el gate seguía verde.

Al destrabarlo aparecieron **355 errores**, casi todos `no-untyped-def`/`no-untyped-call`: los
tests nunca se anotaron. Sin exigir anotaciones quedaban **32 errores reales**, más 118 de
`gen_excalidraw.py`, un script de 412 líneas de la raíz que viene del commit inicial y genera
diagramas para `docs/`.

## Decision
**El type check cubre el repo entero (`mypy .`, 59 archivos) y es el mismo comando en CI, en
el README y en la doc del proyecto.** Con dos niveles de exigencia:

- **`teleflow/` — `strict = true` completo.** Sin cambios: es el código del producto.
- **`tests/*` y `gen_excalidraw`** — se chequean, pero con
  `disallow_untyped_defs`, `disallow_incomplete_defs` y `disallow_untyped_calls` en `false`
  (`[[tool.mypy.overrides]]` en `pyproject.toml`).

La colisión de `conftest` se resuelve con `explicit_package_bases = true` + `mypy_path = "."`,
**sin tocar el layout de `tests/`**.

Un test de contrato (`tests/test_tooling_contract.py`) fija que el comando de CI y el del
README sean el mismo y que cubra el repo entero.

## Rationale
- **Un gate que cubre menos de lo que dice la doc no es un gate, es una impresión.** El costo
  de que divergieran fue invisible y creciente: 23 archivos sin chequear durante 12 días, con
  errores reales adentro.
- **Anotar ~350 firmas de test es ruido mecánico y no encuentra nada.** Lo que sí vale de
  incluir los tests es que **un cambio de firma en `teleflow/` rompa el type check de sus
  tests** — eso se consigue chequeándolos, no anotándolos. Los 32 errores que aparecieron lo
  confirman: eran fakes pasados a funciones tipadas sin `cast`, ignores muertos y un
  `type: ignore[attr-defined]` que **no cubría el error real** (`assignment`).
- **`explicit_package_bases` sobre `__init__.py`:** ambos resuelven la ambigüedad, pero agregar
  `__init__.py` a `tests/` cambia cómo pytest importa los módulos de test. Misma solución, menos
  superficie de riesgo.
- **`gen_excalidraw.py` se chequea en vez de excluirse:** excluirlo lo sacaría del radar para
  siempre; con el override queda cubierto ante un error real sin exigirle un tipado que no
  aporta nada a un script de un solo uso.
- **El guard es un test y no una herramienta más lista.** Que CI y la doc manden comandos
  distintos no lo detecta ningún linter: cada comando, por separado, es válido. Solo un test
  que los compare puede verlo.

## Consequences
- **Al agregar un archivo Python fuera de `teleflow/` y `tests/`**, `mypy .` lo va a chequear en
  strict. Es lo deseado; si es un script de un solo uso, agregarle un override explícito (y no
  un `exclude`).
- **Cambiar el comando de mypy en CI obliga a cambiar el README** — `test_tooling_contract.py`
  falla si no. Es a propósito: la divergencia entre ambos es exactamente lo que este ADR evita.
- **Tipar los tests de verdad sigue siendo posible** más adelante: sacar el override y anotar
  las ~350 firmas. Queda como work-stream aparte, de valor dudoso.
- `docs/teleflow-deployment.typ:241,262` sigue diciendo "mypy --strict en todos los servicios":
  es cierto y no contradice esto, así que no se tocó.

## Alternatives
- **Excluir `tests/` del chequeo** (`exclude = ["^tests/"]`) — descartada: `mypy .` pasaría en
  verde sin mirar los tests. Es la misma cobertura que había, mejor peinada y por lo tanto peor:
  el problema dejaría de verse.
- **Dejar `mypy teleflow` y corregir la doc para que lo diga** — descartada: es lo más barato y
  deja los tests sin cobertura de tipos para siempre. Corrige el síntoma (la divergencia)
  aceptando la pérdida.
- **`__init__.py` en `tests/` y `tests/e2e/`** — descartada por tocar el import mode de pytest
  sin necesidad.
- **Parsear la salida de mypy para verificar que chequeó > 0 archivos** — descartada: ataca un
  caso puntual (este) en vez de la causa (dos fuentes que pueden divergir).

## Sources
`pyproject.toml` (`[tool.mypy]`, overrides `tests.*` y `gen_excalidraw`) ·
`.github/workflows/ci.yml` (paso *Type check*) · `README.md` (§ Desarrollo) ·
`tests/test_tooling_contract.py` · work-streams `saneamiento-comando-tipado` y
`saneamiento-mypy-strict` (el de 2026-07-09, 236→0) ·
[[2026-07-09-mypy-networkx-override]] · [[fallas-silenciosas]] · [[roadmap]]
