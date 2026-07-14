---
project: copp-ia
status: completed
created: 2026-07-14
updated: 2026-07-14
tags: [fase-d, resiliencia, errores, auditoria, rules, entities, view360, domain]
---

# Auditoría de `except Exception` — fallos que se tragan en silencio

## Goal
Derivado de [[resiliencia-executor]]: el bug más caro de ese work-stream estaba en un
`except` que *parecía* manejo de errores (logueaba y seguía) pero perdía el evento. Auditados
los 14 `except Exception` de `teleflow/`, aparecen **4 con el mismo vicio**. Este work-stream
los arregla.

## Context
Provenance: `copp-ia@devyos@b7c6a27`.

### Hallazgos (verificados leyendo el código)
1. **`rules.py:85-88` deja la DLQ recién hecha sin efecto.** El `try/except` que envuelve
   `self._fire(rule, message)` está **dentro del callback que consume el `EventBus`**: si
   disparar una rule falla (DB caída, `DomainError` del trigger, condición que revienta), la
   excepción muere ahí, `_on_event` retorna normal y `handle_message` **ACKea el evento**. O
   sea: el fallo *más probable* del consumer nunca llega a los reintentos ni a la DLQ del
   [[resiliencia-executor]] Chunk 1. Mismo anti-patrón, una capa más arriba.
2. **`entities.py:246-250`: un invariante con un typo nunca se aplica, y sin un solo log.**
   El `except Exception: continue` mezcla dos casos: el benigno (falta un campo opcional → no
   evaluable) y el malo (el invariante **no parsea** → la regla de negocio simplemente no
   existe). Un organismo podría correr meses creyendo que valida edades.
3. **`view360.py:208`: alertas que revientan desaparecen** (`except: continue`, sin log). La
   vista 360 muestra "todo bien" cuando en realidad no se pudo evaluar la condición.
4. **`domain.py:73-77`: un flow corrupto desaparece del dominio.** Sí loguea
   (`domain_parse_failed`), pero sus procesos/rules dejan de existir para el executor sin que
   nada falle explícitamente. Escenario real: un cambio del parser rompe un flow viejo.

### Los que están bien (no tocar)
`engine.py:206` (marca FAILED, no es silencioso), `engine.py:445` y `rules.py:61` (loops de
reconexión), `rules.py:157` (el scan de timers se reintenta al siguiente intervalo),
`observability.py:55` (readiness), `parser.py:121` (fallback cosmético), `composer/main.py:59`
(→ HTTP 502), `executor/main.py:58` (degradación RabbitMQ del ADR-004), `events.py` (los dos
nuevos, ya clasificados).

Caso aparte, **mitigado**: `engine.py:472` — si el listener no procesa el aviso de señal, la
señal igual está persistida en `SignalRecord` y `_recover()` la retoma **al reiniciar**. No se
pierde trabajo, pero la instancia puede quedar dormida hasta el próximo restart.

## Current State
**Los 4 arreglados** en `fix/except-swallow` (`2647198`). Suite 76→**83**, mypy 0, e2e 3/3.
**Verificado en vivo:** una rule que falla al dispararse (apunta a un process inexistente)
ahora manda el evento a `teleflow.rules.v1.dlq` tras los reintentos (DLQ 0→1). Antes se
ACKeaba y se perdía.

## Next Steps
- [x] #1 `rules.py`: `RuleFireError` — se intentan todas las rules que matchean, se acumulan
      los fallos y se levanta al final → el evento reintenta y termina en la DLQ. Las rules
      que ya salieron bien se saltean en los reintentos (sin instancias duplicadas).
- [x] #2 `entities.py`: separado "no parsea" (definición rota → `log.error`) de "no evaluable
      con estos datos" (benigno → `log.debug`), + métrica `teleflow_invariants_skipped_total`.
- [x] #3 `view360.py`: `log.warning("alert_not_evaluable")` en vez de `continue` mudo.
- [x] #4 `domain.py`: `Domain.broken_flows` + métricas `teleflow_domain_parse_failures_total`
      y `teleflow_domain_broken_flows`.
- [x] Mergear a `devyos`.

## Hallazgo lateral — ✅ arreglado (`74168c0`, rama `fix/validator-dangling-refs`)
`validator.py:68` solo avisaba de una rule que apunta a un process inexistente **si el flow
tenía al menos un process** (`if flow.processes and target not in flow.processes`). Un flow
**sin ningún process** con una rule colgada pasaba el deploy con `issues: []` — verificado en
vivo. La misma guarda estaba en 6 lugares (processes/entities/relations/rules/known_events) y
**no** en `step.integration`, que ya avisaba siempre.

Arreglado: se quitaron las 6 guardas. Para no ensuciar los flows que referencian otro archivo
del dominio alcanza con que sea **warning** (no bloquea el deploy) y que el mensaje lo diga.
Los 2 ejemplos del repo siguen en **0 issues**; el flow de la rule colgada ahora devuelve el
warning en el deploy (verificado en vivo). Suite 84 unit / 87 con e2e.

## Decisions
- **Riesgo asumido en #1 — duplicación:** re-lanzar hace que el evento se reintente, y el
  reintento volvería a disparar las rules **que ya habían salido bien** → instancias de
  proceso duplicadas. Se mitiga memorizando, por evento, qué rules ya se ejecutaron OK, y
  salteándolas en los reintentos. La memoria es *best-effort* (en proceso): si el executor se
  cae entre medio, RabbitMQ redelivera y puede haber duplicados — pero eso **ya pasa hoy**
  (semántica at-least-once del broker), no lo introduce este cambio.

## Sources
- `teleflow/executor_service/{rules,entities,view360,domain}.py`
- [[resiliencia-executor]] (de donde sale el aprendizaje)

## Cierre (2026-07-14)

**Resultado:** los 4 arreglados y mergeados a `devyos`. Suite 76→**83**, mypy **0**, e2e 3/3.

### Aprendizajes
- **Un arreglo de resiliencia puede quedar neutralizado por una capa de arriba.** La DLQ del
  [[resiliencia-executor]] estaba bien construida y aun así **no se activaba nunca** en el
  caso más común, porque `rules.py` se comía el error antes de que el bus lo viera. Moraleja:
  al agregar un mecanismo de error, hay que verificar el **camino completo** desde donde nace
  el fallo, no solo el componente nuevo. El test con fakes no lo detectó; el flujo real, sí.
- **"Se loguea y sigue" es una decisión de negocio disfrazada de detalle técnico.** En
  `entities.py` significaba *no aplicar una regla de negocio*; en `view360.py`, *mentirle al
  operador*. Ninguno de los dos autores quiso eso.
- **Una excepción tragada necesita más que un log: necesita una métrica.** Los logs se leen
  cuando ya sospechás; una métrica (`invariants_skipped`, `domain_broken_flows`) es lo que te
  hace sospechar.
- **Al re-lanzar para forzar un reintento, cuidado con lo ya hecho.** Reintentar el evento
  re-dispararía las rules que ya habían salido bien → instancias duplicadas. Se resolvió
  memorizando en memoria qué rules ya anduvieron (best-effort; la duplicación por redelivery
  tras un crash del broker ya existía por la semántica at-least-once, no la agrega este cambio).

## Log
- 2026-07-14: **CERRADO** (`status: completed`). Mergeado a `devyos`.
- 2026-07-14: los 4 arreglos hechos (`2647198`); verificado en vivo que la rule fallida
  aterriza el evento en la DLQ.
- 2026-07-14: creado. 14 `except Exception` auditados, 4 a arreglar.
