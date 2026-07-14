---
project: copp-ia
status: active
created: 2026-07-14
updated: 2026-07-14
tags: [fase-d, executor, resiliencia, rabbitmq, dlq, backoff, adapters]
---

# Resiliencia del executor — DLQ + backoff

## Goal
Segundo ítem de **Fase D** ([[roadmap]], sección "Resiliencia"): que un fallo transitorio no
tumbe una instancia y que un fallo permanente **no se pierda en silencio**.

Dos chunks, una rama por chunk:
1. **DLQ en el event bus** — los eventos que fallan al procesarse hoy se descartan.
2. **Backoff inteligente en adapters** — hoy el reintento es ciego (reintenta un `400` igual
   que un `503`) y el backoff está hardcodeado.

## Context
Provenance: `copp-ia@devyos@1c9a7ea` (código leído en esa rama/commit).

### Huecos verificados (no inferidos)
1. **Eventos fallidos se pierden.** `teleflow/executor_service/events.py:64-71`: el consumer
   hace `async with message.process(ignore_processed=True)` y envuelve el callback en un
   `try/except` que solo loguea → el mensaje se **ACKea igual** y desaparece. La cola se
   declara en `events.py:62` como `declare_queue(queue_name, durable=True)`, **sin**
   `x-dead-letter-exchange`. No hay DLQ en ninguna parte del repo.
2. **Publish fallido también se pierde.** `events.py:54-55`: solo `log.error`, sin reintento.
3. **Backoff ciego y hardcodeado.** `teleflow/executor_service/engine.py:316-339`: el retry
   por step ya existe (`step.retries` del DSL, backoff `min(2 ** attempt, 30)`) pero reintenta
   **cualquier** excepción — un `400`/`422` de `adapters._run_rest:92` consume la ventana de
   reintentos igual que un `503` o un timeout. Sin jitter, sin config.

### Lo que YA está bien (no tocar)
- `engine._run_step` ya tiene la estructura de reintentos por step: el chunk 2 la refina, no
  la reescribe.
- `rules.py:55-63` (`_consume_forever`) ya reconecta el consumer si se cae.
- `engine._signal_listener` (`engine.py:423-432`) ya se auto-reinicia.

## Current State
**Chunk 1 (DLQ) ✅ hecho** en `feat/event-bus-dlq` (`c24ad87`), sin mergear todavía.
Suite 50→55, mypy strict 0, e2e 3/3. **Verificado contra RabbitMQ real** (no solo con fakes):
la declaración con DLX es aceptada, el evento que falla reintenta y aterriza en
`<queue>.dlq` con body intacto y header `x-death`. La management API confirma
`teleflow.rules.v1` con `x-dead-letter-exchange` + su `.dlq`.

Cola vieja `teleflow.rules` **borrada** (2026-07-14, HTTP 204): seguía bindeada al exchange
con `#` y sin consumer, o sea que iba a acumular todos los eventos para siempre.

**Chunk 2 (backoff) ✅ hecho** en `feat/adapters-backoff` (`fde7750`, sale de
`feat/event-bus-dlq`, así que al mergear entran los dos chunks). Suite 55→**76**, mypy 0,
e2e 3/3. **Verificado contra el executor real**: un step contra un host caído reintenta 3
veces (1 + `retries: 2`) con el backoff jitter visible entre intentos y recién ahí falla; un
4xx falla **al primer intento en 0.4s pese a `retries: 5`** (antes gastaba 6 intentos y ~30s
para nada).

Próximo: mergear a `devyos` y cerrar el work-stream.

## Next Steps
- [x] **Chunk 1 — DLQ** (rama `feat/event-bus-dlq`, `c24ad87`):
      DLX `teleflow.domain.events.dlx` + cola `teleflow.rules.v1` con `x-dead-letter-exchange`,
      `reject(requeue=False)` tras N intentos, body ilegible directo a DLQ, `publish` con
      reintentos, métricas `teleflow_events_{consumed,published}_total`, 8 tests.
- [x] **Chunk 2 — Backoff** (rama `feat/adapters-backoff`, `fde7750`):
      `RetryableStepError` + clasificación en adapters (transitorio: 5xx/408/429/red/AMQP
      caído/SMTP 4xx; permanente: 4xx, SMTP 5xx, config), `_run_step` reintenta solo lo
      transitorio, backoff exponencial con **full jitter** y base/tope en `Settings`.
- [ ] Mergear `feat/adapters-backoff` a `devyos` (`--no-ff`) — arrastra también el Chunk 1.
- [ ] Circuit breaker en REST: **fuera de scope**; evaluar como chunk 3 sólo si hace falta.
- [ ] Actualizar [[roadmap]] al cerrar.
- [ ] Limpieza dev: el flow `verify_backoff` quedó registrado en el registry del stack local
      (versionado inmutable, ADR); es inofensivo (sin rules ni triggers) pero ensucia el
      dominio de dev.

## Decisions
- **Cola nueva `teleflow.rules.v1` en vez de mutar `teleflow.rules`.** Agregar
  `x-dead-letter-exchange` a una cola ya declarada hace que RabbitMQ rechace la declaración
  (`PRECONDITION_FAILED` 406) hasta borrarla. Renombrar evita el paso manual y no rompe
  entornos ya levantados; la cola vieja queda huérfana y se borra a mano.
- **Reintentar N veces (default 3) antes de la DLQ**, contando entregas, en vez de mandar a
  DLQ al primer fallo: absorbe fallos transitorios (DB caída un segundo) y aísla los venenosos.
- Circuit breaker queda fuera de este work-stream (scope acotado).

## Sources
- `teleflow/executor_service/events.py`, `engine.py`, `adapters.py`, `rules.py`
- `teleflow/common/config.py`
- [[roadmap]] (Fase D), [[2026-06-30-adr-004-rabbitmq-en-stack]]

## Log
- 2026-07-14: **Chunk 2 (backoff) cerrado** (`fde7750`, rama `feat/adapters-backoff`).
  Clasificación transitorio/permanente + full jitter. Suite 76, mypy 0. Verificado en vivo.
- 2026-07-14: **Chunk 1 (DLQ) cerrado** (`c24ad87`, rama `feat/event-bus-dlq`). Verificado
  contra el broker real; cola vieja `teleflow.rules` borrada. Sigue Chunk 2 (backoff).
- 2026-07-14: creado. Huecos verificados en código; decididas cola `v1` + política DLQ (N=3).
