---
project: copp-ia
date: 2026-07-14
status: accepted
provenance: copp-ia@devyos@ef7af86
tags: [adr, executor, adapters, resiliencia, errores, retry]
---

# ADR (wiki): clasificar los errores de integración en transitorios vs permanentes

> Provenance: `copp-ia@devyos@ef7af86`. Decisión tomada durante el work-stream
> `resiliencia-executor` (Chunk 2). **No** es un ADR del arquitecto (los suyos son
> ADR-001..005): es una decisión del equipo sobre el comportamiento del executor.

## Context
`ExecutionEngine._run_step` reintentaba **cualquier** excepción del adapter hasta agotar
`step.retries` (el número lo declara el DSL). Consecuencias medidas:

- Un `400`/`401`/`422` de una API REST (`adapters._run_rest`) consumía la ventana completa de
  reintentos **más el backoff** — verificado en vivo: un step con `retries: 5` tardaba ~30 s en
  fallar por un request que nunca iba a andar.
- Un bug del propio código (un `KeyError`) se reintentaba tres veces antes de rendirse.
- El caso legítimo (un `503` o un timeout del upstream) es indistinguible del anterior para el
  engine, así que no se podía ser agresivo con uno sin serlo con el otro.

Reintentar es caro (ocupa un worker del semáforo, retrasa la instancia) y no es gratis para el
otro lado (amplifica la carga sobre un servicio que ya está sufriendo).

## Decision
El **adapter** clasifica; el **engine** solo obedece.

- `adapters.RetryableStepError` (subclase de `StepExecutionError`) marca lo **transitorio**:
  5xx, 408, 429, errores de red de httpx (timeout, DNS, conexión rechazada, TLS), broker AMQP
  caído, y SMTP con código 4xx.
- Todo lo demás es **permanente**: 4xx (salvo 408/429), SMTP 5xx, integración/canal mal
  configurado, y cualquier excepción no clasificada (un bug).
- `_run_step` reintenta **solo** `RetryableStepError`. Lo permanente falla en el primer intento
  con `StepFailed("error permanente: ...")`.
- El backoff es exponencial con **full jitter** (`random.uniform(0, techo)`), con base y tope en
  `Settings` (`step_retry_base_delay`, `step_retry_max_delay`).

**Regla para adapters futuros:** un adapter nuevo *debe* clasificar sus fallos. Si levanta una
excepción cruda, el engine la trata como permanente (falla al primer intento) — que es el
default seguro, pero probablemente no el deseado para un fallo de red.

## Rationale
- **La clasificación es conocimiento del protocolo, no del motor.** Solo el adapter sabe que un
  429 es "probá más tarde" y un 422 es "tu payload está mal". Poner esa lógica en el engine lo
  obligaría a conocer HTTP, SMTP y AMQP.
- **Fallar rápido ante lo permanente es una feature**, no una degradación: el operador ve el
  error real en segundos en vez de esperar el backoff completo.
- **Default seguro:** lo no clasificado se trata como permanente. Reintentar un bug desconocido
  no lo arregla y multiplica sus efectos secundarios (si el step ya escribió en un sistema
  externo antes de reventar, el reintento lo escribe de nuevo).
- **El jitter no es cosmético:** sin él, N steps que fallan por el mismo upstream caído
  reintentan al unísono y lo martillan justo cuando intenta levantarse.

## Consequences
- **Trampa a evitar:** envolver un fallo de red en un `StepExecutionError` genérico (o dejar
  escapar la excepción cruda de la librería) hace que **no se reintente nunca**. Es un cambio
  silencioso: el flow "funciona", solo que se rinde al primer hipo de la red.
- `step.retries` del DSL cambió de significado en la práctica: ya no es "cuántas veces reintento
  pase lo que pase", sino "cuántas veces reintento **si el fallo es transitorio**". La
  documentación del DSL debería reflejarlo.
- Los tiempos son configurables por entorno, pero **cuántos** reintentos sigue siendo decisión
  del autor del flow (`retries:`), no del operador.

## Alternatives
- **Clasificar en el engine** (mirar el status code del resultado) — descartada: obliga al motor
  a conocer cada protocolo y se rompe con cada adapter nuevo.
- **Reintentar todo (statu quo)** — descartada: gasta la ventana de reintentos en errores que
  nunca van a resolverse, y retrasa el diagnóstico.
- **No reintentar nada y delegar al `/retry` manual** — descartada: un timeout de red es
  justamente lo que el sistema puede resolver solo, sin despertar a nadie.
- **Circuit breaker** — no es alternativa sino complemento; queda **fuera de scope** hasta que
  haya un upstream que se caiga seguido (`resiliencia-executor`).

## Sources
`teleflow/executor_service/adapters.py` (`RetryableStepError`, `is_retryable_status`,
`_run_rest`, `_run_amqp`, `_send_email`, `_send_sms`) ·
`teleflow/executor_service/engine.py` (`_run_step`, `_retry_delay`) ·
`teleflow/common/config.py` (`step_retry_base_delay`, `step_retry_max_delay`) ·
`tests/test_engine_retry.py` · `resiliencia-executor` · [[roadmap]] (Fase D)
