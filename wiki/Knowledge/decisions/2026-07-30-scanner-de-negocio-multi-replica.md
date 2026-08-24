---
project: copp-ia
date: 2026-07-30
status: accepted
provenance: copp-ia@devyos@54f3f23
tags: [adr, fase-e, observabilidad, prometheus, grafana, executor, negocio, multi-replica]
---

# ADR (wiki): quién publica los gauges de negocio cuando el executor tiene varias réplicas

> Sale del work-stream [[fase-e-helm-kind]] (Fase E, hallazgo 10). **Enmienda a
> [[2026-07-24-metricas-de-negocio-gauges]]**, que decidió *qué* se mide y *cómo* se deriva, pero
> no *quién* lo publica cuando hay más de un executor. **Aceptado el 2026-07-30 y
> CORREGIDO el mismo día**: la decisión original (advisory lock por ciclo) se implementó, se
> verificó en un cluster real y **no funcionaba**. La decisión vigente es la que estaba listada
> como segunda mejor: sacar el scanner a un componente de una sola réplica. El error de
> razonamiento queda escrito en *Decisión corregida* en vez de reescribir la historia: es lo
> más útil de esta página.

## Context
`BusinessMetricsCollector` (`teleflow/executor_service/business_metrics.py`) hace un `GROUP BY`
sobre `process_instances` cada 30 s y publica el **valor absoluto** en tres gauges. Se arranca en
el lifespan del executor **sin condición ni flag** (`executor_service/main.py:56,71`), así que
corre **en cada réplica**.

El dashboard suma entre pods: `observability/grafana/dashboards/teleflow-negocio.json` usa
`sum(teleflow_human_task_backlog)` (línea 28), `sum(teleflow_instances_current)` (65),
`sum by (status) (...)` (133) y `sum by (flow_name) (...)` (157).

**Con `replicas: 3` — el valor que trae el chart (`values.yaml`) y el que recomienda la doc
(`docs/teleflow-deployment.typ:78`, §10.2) — todo número de negocio del dashboard se lee 3×.**
Tres réplicas leen la misma tabla, publican el mismo número, y Prometheus scrapea cada pod por
separado.

Dos cosas hacen que esto importe más que un bug de métricas cualquiera:

- **No falla: miente con un número plausible.** Un backlog de 30 donde hay 10 no se distingue de
  un backlog real de 30. No hay excepción, no hay log, y el panel se ve sano. Es la familia de
  [[fallas-silenciosas]], en la variante "la función que nunca falla" que ya apareció en
  [[registry-cobertura]].
- **Hoy está latente.** El `docker-compose.yml` corre **un** executor, así que no se manifiesta
  en dev ni en CI. Se manifiesta al desplegar el chart, que es justo lo que la doc manda hacer en
  producción.

**Tercera aparición del mismo supuesto no escrito** — "esto corre en un solo proceso" — después
del contador del rate limit y de la purga de keys, ambos cerrados en
[[2026-07-25-estado-compartido-gateway]]. Ahí quedó escrito que el supuesto se paga en cuotas;
esta es otra cuota.

Contraste que vale registrar, porque es la mitad que sí estaba bien: **los timers de rules ya
están preparados para multi-réplica.** `rules.py:_check_timer_event` inserta en `RuleTimerLog` y
atrapa `IntegrityError` con el comentario "otro worker ya lo disparó", sostenido por
`UniqueConstraint("rule_name", "subject_key")` (`teleflow/common/models.py:194`). Es el patrón del
repo —chequeo previo para el caso normal, `UNIQUE` como garantía real— y funciona. El scanner de
métricas se escribió después, en otro work-stream, y no lo heredó.

## Decision
**El colector vive en un componente propio, `metrics-service`, que se despliega con una sola
réplica.** El `executor-service` (3 réplicas) ya no lo arranca. Misma imagen, otro comando —el
mismo patrón con el que el chart corre los 5 servicios—, y en `docker-compose.yml` es un servicio
más.

No hay lock, no hay líder, no hay failover: **la garantía es topológica**. La contracara, y hay
que decirla, es que ahora la garantía es que este componente *no se escale*. Está fijado en
`replicas: 1` en el chart con el motivo al lado, y hay tests que lo sostienen.

Los `sum(...)` del dashboard **no se tocan**: con un solo publicador vuelven a ser correctos.

## Decisión corregida — por qué el advisory lock no servía
**La primera decisión de este ADR fue un error de diseño, y conviene dejar escrito cuál.**

Decía: "elección **por ciclo**; el lock se libera al terminar el ciclo, así no hay líder
permanente ni lógica de failover". Suena prudente y es falso: un lock que se toma y se suelta
dentro del ciclo **solo excluye a réplicas cuyos ciclos se solapan en el tiempo**. El ciclo dura
milisegundos y el intervalo es de 30 s, con los pods arrancados en momentos distintos: no se
solapan nunca. Cada réplica pedía el lock cuando ninguna otra lo tenía, lo obtenía, publicaba y
lo soltaba. Las tres eran "la que publica", cada una en su horario.

Medido en el cluster: los tres pods reportando el mismo valor, y el conteo de `pg_locks` con
`locktype` advisory en **0** en 6 muestras seguidas. El lock jamás estaba tomado.

**El test lo tapaba, y es la parte más instructiva.** El e2e forzaba el solapamiento con un
`await asyncio.sleep(0.5)` dentro del `_collect` de las dos réplicas. Con solapamiento forzado la
exclusión mutua funciona y el test daba `TURNOS=1`. O sea: verificaba una condición que en
producción no ocurre. **Y pasó la verificación por mutación**, porque la mutación quitaba el
chequeo del lock y el test con solapamiento forzado sí detecta eso.

**Regla que sale de acá, distinta de las que ya están en [[fallas-silenciosas]]:** la mutación
prueba que el test *mira el mecanismo*; **no prueba que el escenario del test ocurra en
producción**. Cuando un test necesita construir la condición que lo hace fallar —esperas
inyectadas, concurrencia forzada, relojes movidos— hay que preguntarse si esa condición existe
sola afuera. Si no existe, el test no cubre lo que dice cubrir.

## Rationale
- **Elimina el problema por construcción.** No hay coordinación que pueda estar mal: ni lock que
  se suelte antes de tiempo, ni líder que se crea líder sin serlo, ni ventana de solapamiento que
  razonar. Después de equivocarme razonando justamente sobre solapamiento de ciclos, el argumento
  decisivo es que esta opción **no tiene una segunda forma de fallar**.
- **Funciona igual en Kubernetes y en `docker compose`.** Es lo que descartaba el Lease de k8s y
  sigue valiendo: el producto se instala por organismo
  ([[2026-06-30-adr-005-aislamiento-instancia]]) y el compose es un modo soportado.
- **La garantía queda en la capa que puede sostenerla.** Mismo criterio que el resto del repo,
  sólo que acá la capa no es la base de datos sino el despliegue: cuántos procesos corren no es
  algo que el código pueda decidir, y ahora tampoco necesita decidirlo.
- **El costo de la query deja de multiplicarse.** Con 3 executores se hacían 3 `GROUP BY` cada
  30 s para publicar el mismo dato.
- **Contra, y es el precio real:** un componente más que operar, y un punto único de fallo para
  las métricas donde antes había tres procesos publicando (mal, pero publicando). Si
  `metrics-service` se cae, los paneles de negocio quedan sin datos hasta que vuelva — y "sin
  datos" en un panel de backlog se lee como "no hay trabajo pendiente". Vale una alerta sobre el
  `up` del servicio; **no está hecha**.

## Consequences
- **Verificado en el cluster, que es lo que faltó la primera vez.** Con 3 instancias vivas en
  `WAITING_SIGNAL`: los **tres** pods del executor reportan `no-publica` y el único pod de
  `metrics-service` reporta **3.0**, contra un backlog real de **3** según la API. El `sum(...)`
  vuelve a dar el número verdadero.
- **Cuatro tests de contrato** sostienen la topología, los cuatro verificados por mutación: que el
  executor no arranque el colector, que el chart siga en `replicas: 1`, que el compose tenga el
  servicio y que Prometheus lo scrapee. Más un e2e que afirma **de qué target** vienen los gauges
  (`metrics-service:8005` y nadie más), verificado devolviendo el colector al executor.
- **Hubo que agregar `metrics-service:8005` al scrape config de Prometheus**, y faltó en el primer
  intento: el servicio nuevo quedó fuera de la lista de targets y los paneles de negocio se
  habrían quedado sin datos. Los e2e siguieron verdes un rato porque Prometheus **retiene las
  series viejas** dentro de su ventana de staleness. De ahí sale el cuarto test de contrato.
- **Gotcha de compose descubierto en el camino:** el contenedor de Prometheus tiene un **volumen
  anónimo** en `/prometheus` que `docker compose up --force-recreate` **reutiliza**, así que las
  series de un despliegue anterior sobreviven y pueden hacer pasar —o fallar— una verificación de
  observabilidad por motivos que no tienen que ver con el código. Para arrancar limpio hace falta
  `docker compose rm -sfv prometheus`. Es el espejo del hallazgo de RabbitMQ en
  [[2026-07-25-que-se-respalda]]: allá faltaba un volumen, acá hay uno que nadie declaró.
- **Regla que sale de acá, y es la tercera vez:** todo componente que arranque un loop de fondo
  en el lifespan de un servicio tiene que declarar qué pasa con N réplicas, **en el mismo commit
  que lo agrega**.
- **Queda por revisar `_signal_listener` de `engine.py:87`** con este criterio: es el otro loop de
  fondo del executor y no se auditó.

## Alternatives
- **Cambiar el dashboard a `max(...)` en vez de `sum(...)`** — descartada, y es la más tentadora
  porque no toca una línea de código de la app. Falla en dos formas: (a) una réplica que quedó con
  un valor viejo más alto que la realidad *gana* el `max`, así que el número puede quedar inflado
  igual, solo que de forma intermitente y más difícil de explicar; (b) deja el supuesto sin
  resolver — el próximo panel o la próxima alerta que alguien escriba con `sum` reintroduce el bug,
  y esta vez con la excusa de que "ya se había arreglado". Arregla el síntoma en el lugar
  equivocado.
- **Elección de líder con un `Lease` de Kubernetes** — descartada: ata la corrección al modo de
  despliegue en k8s y deja el bug vivo en `docker compose`, que es un modo soportado. Además
  mete una dependencia de la API de k8s en el executor, que hoy no la tiene.
- **Advisory lock de Postgres por ciclo** — era la decisión original de este ADR. **Descartada
  después de verificarla en un cluster: no funciona.** Ver *Decisión corregida*.
- **Advisory lock sostenido (líder persistente)** — descartada. Funcionaría, pero tiene una trampa
  de corrección: una reconexión transparente del cliente deja la sesión nueva sin el lock y la
  réplica se cree líder sin serlo. Habría que detectar la reconexión comparando
  `pg_backend_pid()`. Más código y más maneras de equivocarse para una garantía que la topología
  da gratis.
- **Un exporter aparte que consulte Postgres** (postgres_exporter con query custom) — ya estaba
  descartada en [[2026-07-24-metricas-de-negocio-gauges]] y sigue: dejaría la definición del
  negocio ("qué estados están vivos") fuera del código que la implementa.
- **Bajar `replicas` del executor a 1 en el chart** — descartada. Es esconder el bug detrás de una
  configuración, contradice la doc §10.2 (que pide 3 con un motivo: `WORKER_CONCURRENCY` es por
  réplica) y le saca al executor la capacidad de escalar, que es lo único que se le pide a un
  servicio sin estado.

## Sources
`teleflow/executor_service/business_metrics.py` · `teleflow/executor_service/main.py:56,71` ·
`teleflow/executor_service/rules.py` (`_check_timer_event`, `_timer_loop`) ·
`teleflow/executor_service/engine.py:87` · `teleflow/common/models.py:194` ·
`observability/grafana/dashboards/teleflow-negocio.json:28,65,133,157` ·
`helm/teleflow/values.yaml` · `docs/teleflow-deployment.typ:78` ·
[[2026-07-24-metricas-de-negocio-gauges]] · [[2026-07-25-estado-compartido-gateway]] ·
[[fase-e-helm-kind]] (hallazgo 10) · [[fallas-silenciosas]] · [[registry-cobertura]]
