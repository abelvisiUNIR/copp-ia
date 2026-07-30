---
project: copp-ia
date: 2026-07-24
status: accepted
provenance: copp-ia@devyos@1305d99
tags: [adr, observabilidad, prometheus, grafana, executor, negocio]
---

# ADR (wiki): las métricas de negocio de estado actual son gauges agregados desde la DB

> Provenance: `copp-ia@devyos@1305d99` (commits `c7b3682` + `eacc05d`). Decisión tomada
> durante el work-stream `observabilidad-negocio` (Fase D). **No** es un ADR del arquitecto
> (los suyos son ADR-001..005): es una decisión del equipo sobre cómo se mide el negocio.

> **Enmendado el 2026-07-30** por [[2026-07-30-scanner-de-negocio-multi-replica]]: este ADR
> decidió *qué* se mide y *cómo* se deriva, pero no *quién* lo publica cuando el executor tiene
> varias réplicas. El scanner corre en cada réplica publicando el valor absoluto y el dashboard
> suma entre pods, así que con `replicas: 3` todo número se lee **3×**. Lo que sigue vale; la
> enmienda agrega la elección de publicador.

## Context
La doc de arquitectura promete dashboards de negocio con "procesos completados y **backlog de
human_tasks**" (`docs/TeleFlow-Arquitectura-v1.0.md:123`,
`docs/teleflow-deployment.typ:243`). Lo que existía era otra cosa:

- `teleflow_instances_total{flow_name,status}` — counter, se incrementa cuando una instancia
  llega a un estado **final** (`executor_service/engine.py`).
- `teleflow_steps_total{flow_name,step_name,result}` — counter de steps ejecutados.
- Un dashboard `TeleFlow · Overview` con dos paneles alimentados por esos counters.

O sea: había paneles rotulados "de negocio", pero **ninguna métrica podía responder cuánto
trabajo hay pendiente ahora**. Un counter solo describe el pasado; el backlog es una pregunta
sobre el presente. La diferencia importa porque el consumidor real de esta métrica es alguien
que decide si hay que reclamarle a un área, no alguien que audita lo que ya pasó.

Los datos ya estaban en `process_instances` (`flow_name`, `status`, `current_step`,
`updated_at` — `teleflow/common/models.py`): una instancia dormida en un `human_task` queda en
`WAITING_SIGNAL` con `current_step` = el step que espera. No hacía falta schema nuevo.

## Decision
Un scanner en el executor (`teleflow/executor_service/business_metrics.py`,
`BusinessMetricsCollector`) hace **un `GROUP BY` sobre `process_instances`** cada
`BUSINESS_METRICS_INTERVAL` (default 30 s) y publica tres **gauges**:

- `teleflow_instances_current{flow_name,status}` — instancias vivas por estado.
- `teleflow_human_task_backlog{flow_name,step_name}` — el backlog, por step que espera.
- `teleflow_human_task_oldest_seconds{flow_name,step_name}` — antigüedad de la más vieja.

Con cuatro reglas que van juntas:

1. **Solo estados vivos** (`TRIGGERED`, `IN_PROGRESS`, `RETRYING`, `WAITING_SIGNAL`).
2. **Agregación por SQL**, no contadores incrementados en cada transición.
3. **Los labels que se vacían bajan a 0**, no se borran: el colector recuerda los labels del
   ciclo anterior para bajarlos explícitamente.
4. **Refresh inicial en el arranque**, antes de entrar al loop.

Las dos clases de métrica conviven y no se mezclan: los counters siguen midiendo eventos
(cuántos procesos terminaron y cómo), los gauges miden estado (cuánto falta).

## Rationale
- **Un counter no puede responder una pregunta sobre el presente.** Es la razón de fondo, y es
  la que hacía parecer cumplido un ítem que no lo estaba.
- **Solo estados vivos:** los terminales ya los cuenta `teleflow_instances_total` en el momento
  exacto en que ocurren. Agregarlos al gauge obligaría a escanear toda la historia de la tabla
  cada 30 s para reconstruir un número que solo crece — costo creciente para información que ya
  se tiene, y peor: costo que crece justo en las instalaciones más viejas y ocupadas.
- **SQL y no contadores en memoria:** incrementar/decrementar un gauge en cada transición se
  desincroniza de la DB ante un reinicio del executor, una corrección manual o cualquier
  escritura por otra vía. El `GROUP BY` siempre dice la verdad de lo persistido; el contador en
  memoria dice la verdad de lo que este proceso vio.
- **Bajar a 0 en vez de borrar:** un gauge conserva el último valor, así que un step que se
  vacía se quedaría marcando backlog fantasma para siempre. Pero borrar la serie deja un
  **hueco**, y "sin datos" no es lo mismo que "no hay backlog" — en un panel de SLA esas dos
  cosas se leen distinto y una de ellas es una mentira tranquilizadora.
- **Refresh inicial:** sin él, un executor recién reiniciado reporta cero trabajo pendiente
  hasta el primer intervalo. Justo después de un deploy, "no hay backlog" es exactamente lo que
  nadie debería creer sin mirar.

## Consequences
- **Costo:** una query agregada cada 30 s sobre el working set. Usa el índice de `status`. Si
  algún día pesa, el intervalo es configurable por entorno — pero bajarlo de 15 s no agrega
  resolución, porque ese es el `scrape_interval` de Prometheus.
- **Los labels se acumulan** mientras el proceso vive: un step que existió alguna vez sigue
  publicándose en 0. Es deliberado (ver arriba) y está acotado por flows × steps del dominio.
- **`current_step` es nullable**, así que el backlog puede reportar el label `desconocido`. Si
  aparece, es señal de un bug del engine — no de un caso de negocio.
- **Regla para métricas de negocio futuras:** antes de agregar una, decidir si la pregunta es
  sobre el pasado (counter, se incrementa donde ocurre el hecho) o sobre el presente (gauge,
  se deriva del estado persistido). Mezclarlas es lo que produjo este gap.

## Alternatives
- **Contadores en memoria incrementados en cada transición** — descartada: se desincroniza del
  estado real y no sobrevive a un reinicio.
- **Reconstruir el backlog desde `teleflow_instances_total` con PromQL** (entradas menos
  salidas) — descartada: no hay counter de "entró a WAITING_SIGNAL", y aunque se agregara, la
  resta acumula deriva y se rompe con cualquier corrección fuera del engine.
- **Un exporter aparte que consulte Postgres** (postgres_exporter con query custom) —
  descartada: sumaría un componente al stack para una query que el executor ya puede hacer, y
  dejaría la definición del negocio (qué estados están "vivos") fuera del código que la
  implementa.
- **Incluir los estados terminales en el gauge** — descartada por el costo creciente; los
  cuenta el counter.

## Sources
`teleflow/executor_service/business_metrics.py` · `teleflow/executor_service/main.py`
(lifespan) · `teleflow/common/config.py` (`business_metrics_interval`) ·
`teleflow/common/models.py` (`ProcessInstance`) ·
`observability/grafana/dashboards/teleflow-negocio.json` · `tests/test_business_metrics.py` ·
`tests/e2e/test_business_metrics_e2e.py` · work-stream `observabilidad-negocio` ·
[[roadmap]] (Fase D) · [[fallas-silenciosas]]
