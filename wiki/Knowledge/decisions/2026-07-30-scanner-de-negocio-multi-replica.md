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
> no *quién* lo publica cuando hay más de un executor. **Aceptado por el owner el 2026-07-30.**

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
**Elegir un publicador por ciclo con un advisory lock de Postgres, y que los que no publican
bajen sus gauges a 0.**

En cada ciclo del scanner, la réplica intenta `pg_try_advisory_lock` sobre una clave fija del
colector. La que lo obtiene hace el `GROUP BY` y publica; las que no, ponen sus propios gauges en
**0** (usando el registro de labels del ciclo anterior que el colector ya mantiene, por la regla 3
de [[2026-07-24-metricas-de-negocio-gauges]]) y sueltan. El lock se libera al terminar el ciclo,
así que no hay líder permanente ni lógica de failover.

Los `sum(...)` del dashboard **no se tocan**: siguen siendo correctos porque solo una réplica
aporta valores y las demás aportan 0.

## Rationale
- **Funciona igual en Kubernetes y en `docker compose`.** Es la razón que descarta la elección de
  líder por Lease de k8s: el producto se instala por organismo
  ([[2026-06-30-adr-005-aislamiento-instancia]]) y el compose es un modo de despliegue soportado,
  no solo el entorno de dev. Una solución que solo funcione en k8s deja el bug vivo en la mitad
  de las instalaciones.
- **Postgres ya es la dependencia compartida por todos los modos de despliegue**, y ya es el
  árbitro de la verdad en el resto del repo: `UNIQUE` + `IntegrityError` en registry, auditoría,
  idempotencia y en los timers de rules. Esto es el mismo criterio con la primitiva que
  corresponde a "solo uno hace esto ahora" en vez de "solo uno gana esta fila".
- **Bajar a 0 en vez de no publicar** es la misma decisión —y por la misma razón— que la regla 3
  del ADR original: un gauge conserva su último valor, así que una réplica que simplemente deja de
  refrescar seguiría exportando el número viejo y el `sum` seguiría inflado. "Sin datos" y "cero"
  no se leen igual, y acá además hay una tercera lectura peor: "dato viejo que parece actual".
- **Elección por ciclo, sin líder persistente**, evita tener que escribir detección de caída y
  failover. Si la réplica que tenía el lock muere, el próximo ciclo lo toma otra; el peor caso es
  un intervalo (30 s) sin refresco, que es exactamente el peor caso que ya acepta el diseño.
- **Efecto secundario bueno:** el costo de la query agregada deja de multiplicarse por la cantidad
  de réplicas. Con 3 executores hoy se hacen 3 `GROUP BY` cada 30 s para publicar el mismo dato.
- **Contra, y hay que decirlo:** las series migran de pod en pod entre ciclos, así que un panel que
  mire una serie **por instancia** en vez del `sum` va a ver saltos. Ningún panel actual lo hace,
  pero es una trampa para el próximo que agregue uno.

## Consequences
- **Se necesita un test que falle hoy.** El caso es "dos colectores contra la misma base": uno
  publica, el otro queda en 0. Sin eso, el arreglo es indistinguible del bug en la suite verde —
  que es precisamente lo que pasó hasta ahora. `(inferencia)` va contra Postgres real, como los
  e2e del registry, porque la garantía la sostiene el lock de la base y un doble diría que sí sin
  verificar nada — mismo criterio de [[registry-cobertura]].
- **La verificación honesta es con réplicas reales**, como se hizo en
  [[2026-07-25-estado-compartido-gateway]]: dos executores contra el mismo Postgres, y el `sum` en
  Prometheus dando el número real y no el doble. Se puede hacer en el cluster de kind que dejó el
  Chunk 1.
- **El dashboard queda intacto**, así que no hay riesgo de regresión en los paneles.
- **Regla que sale de acá, y es la tercera vez:** todo componente que arranque un loop de fondo
  en el lifespan de un servicio tiene que declarar qué pasa con N réplicas, **en el mismo commit
  que lo agrega**. Los tres casos (rate limit, purga de keys, este) se escribieron sin decidirlo
  y se descubrieron después. Candidato a entrar como pregunta fija en la checklist de
  [[fallas-silenciosas]].
- **Queda por revisar si hay otros loops con el mismo problema.** Los conocidos son
  `_consume_forever` y `_timer_loop` de `rules.py` (el segundo ya está cubierto por
  `RuleTimerLog`; el primero es un consumer de RabbitMQ, donde tener N consumidores es el
  comportamiento deseado) y `_signal_listener` de `engine.py:87`, **que no se auditó en este
  chunk**. Verificarlo antes de dar el tema por cerrado.

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
- **Sacar el scanner a un componente propio de 1 réplica** (misma imagen, otro comando, como ya
  hace el chart con los 5 servicios) — descartada, pero es la segunda mejor y quedaría bien si el
  advisory lock resulta incómodo. A favor: elimina el problema por construcción, sin locks. En
  contra: suma un Deployment más a operar, hay que replicarlo en el compose, y crea un punto
  único de fallo para las métricas donde hoy hay tres. También conviene mirarla de nuevo si algún
  día se le agregan más loops de este tipo al executor.
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
