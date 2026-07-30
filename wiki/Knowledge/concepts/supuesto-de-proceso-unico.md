---
project: copp-ia
type: concept
provenance: copp-ia@devyos@74a0002
created: 2026-07-30
updated: 2026-07-30
tags: [concepto, multi-replica, concurrencia, despliegue, patron]
---

# "Esto corre en un solo proceso" — el supuesto que nadie escribió y apareció cuatro veces

> Provenance: `copp-ia@devyos@74a0002`. Sintetizado de dos work-streams
> ([[estado-compartido-gateway]] y [[fase-e-helm-kind]]) y cuatro apariciones verificadas.
> Emparentado con [[fallas-silenciosas]] pero **no es lo mismo**: allá el mecanismo de aviso
> existe y no corta; acá **no hay ningún mecanismo**, porque nadie decidió que hiciera falta.

## Qué es
Código que funciona perfecto con un proceso y se degrada con dos, escrito por alguien que nunca
se preguntó cuántos iban a correr. No es un error de razonamiento: es una **pregunta que no se
hizo**, y por eso no dejó rastro — ni un comentario, ni un `TODO`, ni una nota de "límite
conocido".

Se paga en cuotas. Cada feature nueva que toca estado compartido lo re-descubre, y como no está
escrito, lo re-descubre desde cero.

**Por qué sobrevive tanto:** el entorno de desarrollo corre **una** réplica de todo. El
`docker-compose.yml` levanta un gateway, un executor. Así que ningún caso de esta lista se
manifiesta en dev ni en CI: aparecen al desplegar el chart, que declara 2 gateways y 3
executors — los números que **recomienda la doc de arquitectura** (§10.2). El código y el
despliegue documentado se contradecían, y la contradicción vivía en dos archivos que nadie leía
juntos.

## Las cuatro apariciones

| # | Dónde | Con 1 proceso | Con N procesos | Cómo se resolvió |
|---|---|---|---|---|
| 1 | Rate limit del gateway (`_buckets`, dict en memoria) | límite exacto | límite efectivo = **N × rpm** | contador en Redis ([[2026-07-25-estado-compartido-gateway]]) |
| 2 | Purga del cache de API keys | una key revocada deja de servir ya | la réplica que no atendió la revocación **sigue aceptando la key** hasta que vence el TTL | invalidación por pub/sub (mismo ADR) |
| 3 | Scanner de métricas de negocio | el backlog es el que es | cada réplica publica el **valor absoluto** y el dashboard suma: **3× el negocio**, sin que nada falle | el colector se mudó a un componente de **una sola réplica** ([[2026-07-30-scanner-de-negocio-multi-replica]]) |
| 4 | `_recover()` del executor | retoma lo que quedó a mitad | **cada réplica ejecuta el mismo expediente**: 63 requests donde iban 21, y 3 transiciones a `FAILED` del mismo caso | **lease** con dueño y vencimiento en la base ([[2026-07-30-propiedad-de-instancia-en-el-executor]]) |

Y una que **sí** estaba bien, que es la que más enseña: los timers de rules
(`_check_timer_event`) insertan en `RuleTimerLog` y atrapan el `IntegrityError` con el comentario
*"otro worker ya lo disparó"*, sostenido por un `UNIQUE`. Alguien **sí** se hizo la pregunta, en
2026-07-14. El scanner de métricas se escribió después, en otro work-stream, y no lo heredó: el
conocimiento no viajó solo.

## No hay una sola solución, y elegir mal cuesta caro
Las cuatro se resolvieron distinto **a propósito**, según qué garantía hacía falta:

- **Estado compartido** (casos 1 y 2) — cuando N procesos necesitan ver lo mismo. Va a un almacén
  común (Redis acá). Es el más obvio y el menos interesante.
- **Un solo proceso, por topología** (caso 3) — cuando la tarea *no debe* hacerse dos veces y no
  hay nada que compartir. Un componente de una réplica lo dice sin lógica ninguna: no hay lock que
  pueda estar mal, ni líder que se crea líder sin serlo. **La contracara es que la garantía pasa a
  ser que nadie lo escale**, así que hay que fijarlo en el chart y protegerlo con un test.
- **Propiedad con vencimiento** (caso 4) — cuando N procesos pueden hacer la tarea pero solo uno
  debe hacerla *a la vez*, y si el que la tiene muere, otro debe tomarla. Un candado no alcanza
  (deja el trabajo trabado para siempre); hace falta un **lease**.

**El intento fallido vale más que los tres aciertos.** El caso 3 se intentó primero con un
advisory lock de Postgres tomado y soltado **dentro de cada ciclo**, razonando que así no hacía
falta un líder permanente ni lógica de failover. Es falso: un lock que se toma y se suelta dentro
del ciclo solo excluye a procesos cuyos ciclos **se solapan en el tiempo**, y con un ciclo de
milisegundos cada 30 s no se solapan nunca. Las tres réplicas obtenían el lock, cada una en su
horario. Medido: `pg_locks` con `locktype='advisory'` en **0** en seis muestras seguidas.

## Cómo detectarlo antes
**La regla, que ya costó cuatro veces:** todo componente que arranque un loop de fondo o una
tarea de arranque en el lifespan de un servicio tiene que **declarar qué pasa con N réplicas, en
el mismo commit que lo agrega**. Un comentario alcanza. Lo que no alcanza es no preguntárselo.

Tres preguntas concretas al escribir algo así:

1. **¿Esto acumula estado en memoria del proceso?** Un dict, un contador, un cache. Si dos
   procesos tienen su propia copia, ¿el resultado sigue siendo correcto?
2. **¿Esto publica un número absoluto o un incremento?** Un gauge con el valor absoluto se
   multiplica al sumar entre instancias; un counter de eventos no.
3. **¿Esto toma trabajo de una cola o tabla compartida?** Si dos lo toman, ¿el trabajo se hace dos
   veces? Un broadcast (pub/sub) llega a **todos**, no a uno.

## Cómo verificarlo, que es donde se falla
**Con réplicas reales, no con un doble.** Los cuatro casos se verificaron levantando dos o tres
procesos de verdad contra la misma base:

- Gateway: dos pods con port-forward **individual** (al Service, el balanceo elige y no se puede
  afirmar nada sobre "la otra"), y confirmando que son procesos distintos por
  `process_start_time_seconds` — sin eso, la prueba pasa trivialmente si los dos túneles van al
  mismo pod.
- Executor: una instancia en vuelo y un `rollout restart`, contando recuperaciones, intentos del
  step y transiciones.

**Y ojo con el test que se escriba.** Un test que **fuerza** la condición de carrera —esperas
inyectadas, concurrencia provocada— prueba exclusión mutua, no que el problema real desaparezca.
En el caso 3 ese test pasó **con el bug puesto**, y además pasó la verificación por mutación. El
escenario del test tiene que ser el que el sistema produce solo: arranques desfasados, ciclos que
no se solapan. Ver [[fallas-silenciosas]], que recoge la regla general.

## Sources
`teleflow/gateway/main.py` (rate limit, cache de keys) ·
`teleflow/executor_service/business_metrics.py` · `teleflow/metrics_service/main.py` ·
`teleflow/executor_service/engine.py` (`_recover`, `_tomar_lease`, `_apply_signals_and_resume`) ·
`teleflow/executor_service/rules.py` (`_check_timer_event`, el que sí estaba bien) ·
`teleflow/common/models.py` (`RuleTimerLog`, `ProcessInstance.driven_by`) ·
`helm/teleflow/values.yaml` · `docs/teleflow-deployment.typ` §10.2 ·
[[2026-07-25-estado-compartido-gateway]] · [[2026-07-30-scanner-de-negocio-multi-replica]] ·
[[2026-07-30-propiedad-de-instancia-en-el-executor]] · [[fallas-silenciosas]] ·
[[fase-e-helm-kind]]
