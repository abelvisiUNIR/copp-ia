---
project: copp-ia
date: 2026-07-30
status: accepted
provenance: copp-ia@devyos@c42f13f
tags: [adr, fase-e, executor, engine, multi-replica, idempotencia, integridad]
---

# ADR (wiki): quién es dueño de una instancia en vuelo cuando el executor tiene varias réplicas

> Sale del work-stream [[fase-e-helm-kind]] (Fase E, hallazgo 15), al auditar los loops de fondo
> del executor con el criterio de [[2026-07-30-scanner-de-negocio-multi-replica]].
> **Aceptado por el owner el 2026-07-30.** Se escribió en `proposed` porque es el cambio más
> invasivo de la serie: toca el motor de ejecución y necesita migración.
>
> **Cuarta aparición del supuesto no escrito "esto corre en un solo proceso"**, después del
> contador del rate limit, la purga de keys ([[2026-07-25-estado-compartido-gateway]]) y los
> gauges de negocio. Las tres primeras eran del gateway o de métricas. **Esta es del motor de
> ejecución**, así que el daño no es un número mal leído: es un step de negocio ejecutado de más.

## Context
`ExecutionEngine._recover()` (`teleflow/executor_service/engine.py:112-129`) corre en el
`start()` de **cada** réplica y hace `self._spawn(self._drive(instance_id))` para **todas** las
instancias en `TRIGGERED`, `IN_PROGRESS` o `RETRYING`. Su razón de ser es legítima: retomar
expedientes que quedaron a mitad de camino cuando el proceso anterior murió.

El problema es que en ese camino **nadie reclama la instancia**:

- `_load` (`:573`) es un `session.get` pelado, sin `with_for_update`.
- `_run` (`:254-257`) solo corta si el estado es `COMPLETED` o `COMPENSATED`.
- `_set_status` (`:611-623`) es un `UPDATE` **incondicional**: no lleva
  `WHERE status = from_status`, así que tampoco funciona como compare-and-swap donde una de las
  réplicas perdería.

**La mitad que sí estaba bien, y conviene registrarla:** el path de **señales** es seguro para N
réplicas y a propósito. El pub/sub de Redis es broadcast, así que las tres réplicas reciben el
mismo mensaje, pero `_apply_signals_and_resume` (`:520-525`) abre la instancia con
`session.get(..., with_for_update=True)` y corta si el estado ya no es `WAITING_SIGNAL`. La que
gana el lock aplica las señales; las otras se bloquean, ven el estado nuevo y se van. Igual que
los timers de rules con su `UNIQUE`. El hueco está solo en la recuperación al arrancar.

### Reproducido en el cluster (2026-07-30)
No es inferencia. Los flows de ejemplo terminan en milisegundos y no dejan ventana, así que se
fabricó una: un flow de sonda con un step REST a un host que no resuelve y `retries: 20`, que
mantiene la instancia en vuelo durante el backoff. Con esa instancia viva, un
`kubectl rollout restart` del executor (3 réplicas).

Resultado:

```
teleflow-executor-service-...-8k5bp  recover_in_flight de la instancia: 1  intentos del step: 21
teleflow-executor-service-...-bxpxp  recover_in_flight de la instancia: 1  intentos del step: 21
teleflow-executor-service-...-lphcv  recover_in_flight de la instancia: 1  intentos del step: 21
```

**Las tres réplicas recuperaron la misma instancia y cada una ejecutó el step completo: 63
requests donde correspondían 21.** Y el rastro quedó corrupto: `instance_transitions` pasó de 2
filas a **5**, con **tres** `IN_PROGRESS → FAILED` del mismo step, a los 13:57:08, 13:57:13 y
13:57:23. El mismo expediente "falló" tres veces.

En la sonda el step era un host inexistente y el daño fue solo ruido. Con una integración real
—un POST que crea un expediente, un SMTP que notifica al ciudadano, un alta en un LMS— son
**tres** altas, tres correos, tres registros. Es exactamente el daño que
[[2026-07-25-idempotencia-execute]] existe para evitar, pero **desde adentro**: la idempotencia
protege del doble disparo del **cliente**, no del doble drive del propio executor.

### Por qué es urgente y no teórico
**La condición de disparo es cada deploy.** Un `kubectl rollout restart` o un `helm upgrade`
levanta réplicas nuevas a la vez; si hay un expediente en vuelo, lo recuperan todas. No hace
falta una caída ni una partición de red: alcanza con desplegar mientras el sistema trabaja, que
es lo normal.

Hoy está **latente** porque el `docker-compose.yml` corre un solo executor: no se manifiesta en
dev ni en CI. Se manifiesta al desplegar el chart con las 3 réplicas que el chart declara y que
la doc de arquitectura recomienda (`docs/teleflow-deployment.typ:78`, §10.2).

## Decision
**Una instancia en vuelo tiene un dueño con vencimiento (lease), y solo el dueño la ejecuta.**

Dos columnas nuevas en `process_instances` (migración): el dueño actual y el vencimiento del
lease. Tres reglas:

1. **Reclamo atómico.** Antes de ejecutar, la réplica hace un `UPDATE ... WHERE id = ? AND
   (dueño IS NULL OR lease vencido)` y **solo sigue si el `UPDATE` afectó una fila**. La garantía
   la sostiene la base, no el orden en que arrancan los pods — mismo criterio que el `UNIQUE` en
   registry, auditoría, idempotencia y los timers de rules.
2. **Renovación mientras trabaja.** El drive renueva el lease periódicamente. Un proceso vivo
   nunca pierde su instancia; un proceso muerto deja de renovar y el lease vence.
3. **`_recover()` solo toma lo que nadie tiene.** Deja de ser "recupero todo lo que esté en
   vuelo" y pasa a ser "tomo lo que quedó huérfano", que es lo que siempre quiso decir.

El lease vencido es lo que hace correcta la recuperación tras una caída real: es el único momento
en que otra réplica **debe** tomar el trabajo. Sin vencimiento, un pod que muere deja su
expediente trabado para siempre.

**De paso, y aunque el lease ya lo cubre:** `_set_status` pasa a llevar
`WHERE status = from_status`. Un cambio de estado que no verifica de dónde viene no puede
detectar que alguien se le adelantó, y hoy ni lo intenta.

## Rationale
- **La garantía va donde puede sostenerse.** Es el mismo criterio del resto del repo: chequeo
  previo para el caso normal y una operación atómica de la base como garantía real. Acá el
  chequeo previo es el `WHERE`, y lo que decide es el rowcount.
- **Un lease y no un lock sostenido.** `SELECT ... FOR UPDATE` mantenido durante todo el drive
  ataría una conexión y una transacción de Postgres por expediente en vuelo, durante minutos si
  el step reintenta. El lease es un dato, no una transacción abierta: sobrevive a un reinicio del
  pool y no bloquea a nadie.
- **Un lease y no "que recupere un solo componente".** Es lo que resolvió el caso de los gauges
  ([[2026-07-30-scanner-de-negocio-multi-replica]]) y acá **no alcanza**: aunque recuperara una
  sola réplica, podría tomar un expediente que otra está ejecutando **ahora**, porque el drive
  normal —el de `trigger()`— tampoco reclama nada. El problema no es solo quién recupera, es que
  nadie es dueño.
- **Renovar es imprescindible, y es el costo real.** Sin renovación hay que elegir entre un lease
  corto (otra réplica roba el expediente a mitad de ejecución) o uno largo (una caída deja el
  expediente trabado ese tiempo). Con renovación no hay que elegir, a cambio de un loop más.
- **La guarda en `_set_status` es barata y ortogonal.** Aunque el lease se implemente mal alguna
  vez, un `UPDATE` guardado convierte una carrera silenciosa en algo detectable.

## Consequences
- **Necesita migración de Alembic** (dos columnas). Es la sexta; el patrón está.
- **Implementado y verificado con el mismo experimento que lo encontró (2026-07-30).** Instancia
  en vuelo + `rollout restart` con 3 réplicas, y los tres números dieron exacto:

  | | antes | después |
  |---|---|---|
  | pods que recuperaron la instancia | 3 | **1** |
  | intentos del step, sumando los 3 pods | 63 | **21** |
  | transiciones `IN_PROGRESS → FAILED` | 3 | **1** |

  El lease quedó tomado con el nombre del pod (`teleflow-executor-service-...-8v7zv:1`) y en
  `NADIE` al terminar el drive. Total de transiciones: 3, las que corresponden.
- **Y hay que probar el caso que el lease habilita:** matar el pod que tiene una instancia y
  verificar que otra la toma **después** del vencimiento y no antes. Eso es lo que distingue un
  lease de un candado, y es la parte que un test apurado se saltearía.
- **Ojo con el test que se escriba.** Aprendizaje directo de
  [[2026-07-30-scanner-de-negocio-multi-replica]]: la verificación por mutación prueba que el test
  mira el mecanismo, **no** prueba que el escenario ocurra en producción. Un test que fuerce el
  solapamiento de dos drives probaría exclusión mutua, no que la recuperación al arrancar dejó de
  duplicar. El escenario tiene que ser el real: dos arranques con una instancia en vuelo.
- **El compose sigue sin poder mostrar el bug** (un solo executor), así que la verificación
  honesta es en el cluster. `(inferencia)` vale evaluar si el job e2e de CI puede levantar dos
  executors, como se hizo con los dos gateways en
  [[2026-07-25-estado-compartido-gateway]].
- **Queda una pregunta abierta que este ADR no cierra:** las instancias que ya quedaron
  duplicadas por este bug en un entorno real. Hoy no hay instalación productiva, así que no hay
  nada que reparar — otra vez la ventana barata es **ahora**, igual que en
  [[2026-07-25-idempotencia-execute]].
- **Regla, y es la cuarta vez:** todo loop de fondo o tarea de arranque que se lance en el
  lifespan de un servicio tiene que declarar qué pasa con N réplicas, **en el mismo commit que lo
  agrega**. Las cuatro apariciones se escribieron sin decidirlo y se descubrieron después.

## Alternatives
- **`SELECT ... FOR UPDATE` sostenido durante el drive** — descartada: ata una transacción de
  Postgres por expediente en vuelo mientras dure la ejecución, que con reintentos son minutos.
  Además un reinicio del pool suelta el lock sin que el código se entere, que es la misma trampa
  que descartó el advisory lock sostenido en el ADR de los gauges.
- **Que solo un componente de una réplica haga la recuperación** — descartada, y es importante
  por qué: resolvió el caso de los gauges pero acá **no alcanza**, porque el drive normal tampoco
  reclama la instancia. Arreglaría el disparador más frecuente dejando el hueco abierto.
- **Quitar `_recover()`** — descartada. Es lo que hace que un expediente sobreviva a la muerte del
  proceso que lo ejecutaba; sacarlo cambia un bug de duplicación por uno de pérdida, que es peor.
- **Bajar el executor a 1 réplica** — descartada por lo mismo que en el ADR de los gauges:
  esconde el bug detrás de una configuración, contradice §10.2 (que pide 3 con un motivo:
  `WORKER_CONCURRENCY` es por réplica) y le saca al executor la capacidad de escalar.
- **Idempotencia a nivel de step** (que cada step declare una clave y el engine deduplique) —
  descartada **como reemplazo**, no como complemento. Es más robusta en el límite —protege incluso
  de dos drives legítimos— pero exige que cada step declare su clave y cambia el DSL. El lease
  arregla la causa; esto sería una segunda red, y vale reconsiderarla si aparece otro camino de
  doble ejecución.

## Sources
`teleflow/executor_service/engine.py:112-129` (`_recover`), `:242-257` (`_drive`/`_run`),
`:520-525` (`_apply_signals_and_resume`, el caso que sí está protegido), `:573` (`_load`),
`:611-623` (`_set_status`) · `teleflow/common/models.py` (`ProcessInstance`,
`InstanceTransition`) · `docs/teleflow-deployment.typ:78` · [[fase-e-helm-kind]] (hallazgo 15) ·
[[2026-07-30-scanner-de-negocio-multi-replica]] · [[2026-07-25-estado-compartido-gateway]] ·
[[2026-07-25-idempotencia-execute]] · [[fallas-silenciosas]]
