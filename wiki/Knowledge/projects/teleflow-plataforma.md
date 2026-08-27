---
project: copp-ia
type: project-overview
provenance: copp-ia@devyos@fad74e4
updated: 2026-08-25
tags: [arquitectura, vision, dsl, overview]
---

# TeleFlow Platform — visión y arquitectura

> Provenance: `copp-ia@devyos@fad74e4` (2026-08-25). Fuentes: `docs/TeleFlow-Arquitectura-v1.0.md`,
> `docs/teleflow-{vision,adr,dsl-reference,deployment}.typ`, `README.md` y código en `teleflow/`.
> Validado contra código → ver [[2026-07-09-validacion-doc-vs-codigo]].
>
> **Esta página describía la plataforma tal como estaba en el commit inicial** (`@main@6046648`,
> 2026-07-09) y se quedó atrás de dos meses de trabajo: faltaba un servicio entero, dos tablas y
> el traslado del colector de negocio. Se detectó al usarla como fuente para un informe, no al
> leerla — que es la forma en que este repo ya documentó que envejece la doc
> ([[fallas-silenciosas]], caso 17). Al tocar el código que esta página describe, **actualizarla
> en el mismo commit.**

## Qué es (hecho)

Plataforma de orquestación empresarial basada en **Business & Software as Code**: los
organismos modelan, despliegan y ejecutan sus procesos de venta y post-venta como código
declarativo (`.tflow`), con el mismo rigor con que Terraform gestiona infraestructura
(`docs/teleflow-vision.typ:71-74`).

**No es SaaS.** Se instancia por organismo (OSE, Antel, Ceibal, Min. Economía), con datos
físicamente aislados, como GitLab self-hosted. El mismo `docker-compose.yml` y Helm charts
sirven a todos; los templates se comparten vía Git (ADR-005, [[2026-06-30-adr-005-aislamiento-instancia]]).

## Ciclo de vida del producto (hecho — `TeleFlow-Arquitectura-v1.0.md:30-34`)

1. Analista describe el proceso en lenguaje natural.
2. LLM configurable genera el borrador `.tflow`.
3. Desarrollador lo revisa/aprueba en UI tipo pull-request.
4. El motor lo registra (versión inmutable) y lo ejecuta.
5. Ejecución confiable, observable y recuperable — dure segundos o semanas.

## Servicios (hecho — `docker-compose.yml`, `README.md:11-20`)

| Servicio | Puerto | Rol |
|---|---|---|
| `api-gateway` | 8000 | Único punto de entrada. Auth (`X-TeleFlow-API-Key`), rate limit (token bucket), routing. **Proxy puro, sin lógica de dominio** |
| `parser-service` | 8001 | `.tflow` → AST JSON validado (sintáctica + semántica). Nunca ejecuta |
| `executor-service` | 8002 | DAG engine async, durable sleep, **rule engine, entities/relations, view360**, adapters |
| `registry-service` | 8003 | Versionado inmutable de flows; `latest` = pointer mutable |
| `composer-service` | 8004 | Abstracción LLM; borradores `.tflow` desde lenguaje natural |
| `metrics-service` | 8005 | **Agregado 2026-07-24.** Publica los gauges de estado actual del trabajo en curso. **Una sola réplica, por diseño** |
| `review-ui` | 3100 | UI React de revisión PR-style |

Infra: `postgres:5432`, `redis:6379`, `rabbitmq:5672`, `prometheus:9090`,
`grafana` (host **3001** por defecto, no 3000 — ver validación).

Los **6** servicios Python corren desde **una sola imagen** (`Dockerfile`), seleccionando el
servicio con `uvicorn teleflow.<svc>.main:app`.

`metrics-service` es el único que **no** se puede escalar: publica gauges de valor absoluto y
el dashboard suma entre pods, así que dos réplicas hacen leer al doble todo número de negocio,
sin que nada falle ni se loguee. Estuvo dentro del executor (3 réplicas) y por eso se leía 3×.
La exclusión es **topológica a propósito** — se intentó coordinar por advisory lock y no
alcanzó, porque dos ciclos que no se solapan en el tiempo no se excluyen entre sí. Ver
[[2026-07-30-scanner-de-negocio-multi-replica]].

### Partición mental (hecho)
- **Core Engine:** parser / registry / executor / gateway.
- **Capa IA:** composer / review-ui.
- **Observabilidad de negocio:** metrics-service (lee la misma base, no participa del camino
  de ejecución).

## Cómo se relacionan (hecho)

- **Deploy de un flow:** `POST /flows/{name}` → gateway → parser (valida) → registry
  (persiste inmutable) (`gateway/main.py:106-142`).
- **Ejecución async:** `POST /execute` responde inmediato con `instance_id` + `TRIGGERED`;
  progreso por `GET /instances/{id}`.
- **Event-driven:** entities/relations emiten eventos a RabbitMQ (topic exchange, routing
  key = nombre del evento); el rule engine evalúa `condition` y dispara procesos; sistemas
  externos pueden suscribirse sin acoplamiento.
- **Durable sleep:** en `human_task` la instancia pasa a `WAITING_SIGNAL`, persiste contexto
  en Postgres (`context._cursor`) y libera el worker; `POST /instances/{id}/signal` publica
  en Redis pub/sub y reactiva en ms (ADR-002, [[2026-06-30-adr-002-durable-sleep]]).

## DSL `.tflow` v2 (hecho — sección 4, `teleflow-dsl-reference.typ`)

Bloques **nuevos v2**: `entity`, `relation`, `rule`, `view360`.
**Existentes**: `process`, `step`, `integration`, `catalog`, `party`.

- `entity`: identidad + campos tipados + máquina de estados (lifecycle) + invariantes +
  eventos por transición.
- `relation`: vínculo con estado propio entre dos entities (el "producto instanciado",
  ej. inscripción niño↔curso); identidad `(relation_type, from_id, to_id)`.
- `rule`: 4 triggers — `on_event`, `on_state`, `on_timer`, `on_relation`.
- `stage` con modos `sequential | parallel | decision` (parallel usa `asyncio.gather()` y
  **no admite human_task**).
- Evaluador de expresiones propio: operadores, `in`, `WHEN cond`, `days_since`/`years_since`,
  contextos `event.*`/`relation.*`/`payload.*`/`signals.*`, comparaciones null-safe.

La gramática EBNF `teleflow/dsl/teleflow.lark` es la **única fuente de verdad del lenguaje**
(ADR-001, [[2026-06-30-adr-001-lark-lalr]]). Toda extensión del DSL empieza ahí.

## Estados de una instancia (hecho — sección 5.3)

`TRIGGERED → IN_PROGRESS → {WAITING_SIGNAL ⇄ IN_PROGRESS} → COMPLETED | FAILED`;
`FAILED → RETRYING → {IN_PROGRESS | COMPENSATED}`.

## Persistencia (hecho — `teleflow-deployment.typ:156-191`, Alembic `0001_initial.py`)

Tablas clave: `flow_definitions` (inmutable, `UNIQUE(name,version)`), `flow_latest`,
`process_instances` (`context._cursor` = estado del durable sleep), `instance_transitions`,
`signals` (`signal_key UNIQUE` → idempotencia), `entity_state`, `entity_events` (log
inmutable, fuente de view360 y on_timer), `relation_state`, `flow_drafts`, `rule_timer_log`
(`UNIQUE(rule_name, subject_key)` → evita doble disparo de on_timer).

**Agregadas después del inicial** (12 tablas en total, migraciones `0002`-`0006`):

- `api_keys` (`0002`) — claves hasheadas SHA-256 con scopes e identidad para auditoría. La key
  de entorno queda como **bootstrap**. Ver [[seguridad-api-keys]].
- `audit_log` (`0004`) — append-only: quién desplegó qué versión y cuándo pasó a ser una
  consulta y no un grep sobre logs rotados. Ver [[2026-07-25-auditoria-persistida]].
- Columnas, no tablas: `flow_drafts.validation` (`0003`, el borrador se guarda con el resultado
  de validarlo contra el parser), `process_instances.idempotency_key` (`0005`) y
  `process_instances.driven_by` / `lease_expires_at` (`0006`, propiedad de la instancia en
  vuelo cuando el executor corre con varias réplicas —
  [[2026-07-30-propiedad-de-instancia-en-el-executor]]).

## Observabilidad (hecho — `copp-ia@devyos@fad74e4`)

Prometheus scrapea `/metrics` de los **6** servicios cada 15 s
(`teleflow/common/observability.py` instala el middleware, `/health` y `/ready` en cada app).
Grafana provisiona dos dashboards: **TeleFlow · Overview** (técnico: requests, p95, error rate,
throughput de steps) y **TeleFlow · Negocio** (trabajo pendiente).

**Los dashboards y las alertas viven dentro del chart** (`helm/teleflow/dashboards/`,
`helm/teleflow/alerts/alerts.yml`) y **no** en `observability/`, aunque el compose también los
use: Helm no puede leer archivos fuera del chart, así que si hubiera dos copias divergirían. El
compose los toma de ahí (`observability/grafana.Dockerfile` copia
`helm/teleflow/dashboards`, con el contexto de build en la raíz), y el chart los expone como
ConfigMap y `PrometheusRule` opt-in. Una sola fuente, dos consumidores.

Las métricas son de **dos clases y no se mezclan**:

- **Counters de eventos** — `teleflow_http_requests_total`, `teleflow_instances_total`
  (instancias por estado **final**), `teleflow_steps_total`, `teleflow_events_consumed_total`
  / `_published_total`, `teleflow_invariants_skipped_total`, `teleflow_domain_parse_failures_total`.
  Miden lo que ya pasó, en el momento en que pasa.
- **Gauges de estado actual** — `teleflow_instances_current{flow_name,status}`,
  `teleflow_human_task_backlog{flow_name,step_name}`,
  `teleflow_human_task_oldest_seconds{...}`, `teleflow_executor_backlog`,
  `teleflow_domain_broken_flows`. Los recalcula `BusinessMetricsCollector`
  (`executor_service/business_metrics.py`) agregando `process_instances` cada
  `BUSINESS_METRICS_INTERVAL` (30 s), solo sobre estados vivos. **El módulo vive en
  `executor_service/` por historia, pero el colector lo arranca `metrics_service`**
  (`metrics_service/main.py:49`) — la ubicación del archivo no dice quién lo ejecuta.
- **Frescura del colector** — `teleflow_business_metrics_last_success_timestamp_seconds` y
  `teleflow_business_metrics_refresh_failures_total`. Existen porque los gauges de arriba
  **conservan su último valor** si el refresh falla: con la base caída el pod queda vivo, `up`
  vale 1 y un backlog congelado en 10 se lee igual que uno estable en 10. Ver
  [[fallas-silenciosas]] #14.
- **`teleflow_executor_backlog`** es aparte del resto: es la señal de **capacidad** del
  executor —lo que compite por un worker— y **excluye durable sleep** a propósito, porque una
  instancia dormida esperando a un humano no ocupa nada. Es la métrica que puede consumir un
  autoescalador. Ver [[2026-08-18-senal-de-escalado-del-executor]].

El **backlog de human_tasks** — cuántas instancias esperan señal en cada step y hace cuánto —
es la métrica de negocio central y solo un gauge puede darla: un counter describe el pasado.
Ver [[2026-07-24-metricas-de-negocio-gauges]].

**Gotcha de deploy:** los dashboards viven en `/etc/grafana/dashboards`, **fuera** de
`/var/lib/grafana` (ahí monta el volumen `grafana-data`, y Docker copia el contenido de la
imagen al volumen solo cuando lo crea vacío: un dashboard nuevo nunca llegaría a una
instalación existente). Ver [[fallas-silenciosas]].

## Stack (hecho — sección 10)

Python 3.11, FastAPI+uvicorn, SQLAlchemy 2 async+asyncpg, Alembic, Pydantic v2,
networkx (DAG), httpx, aio-pika, redis.asyncio, structlog, mypy --strict (declarado),
pytest-asyncio, React+Vite. Prometheus+Grafana.

## Estado de implementación (al 2026-08-25 — `copp-ia@devyos@fad74e4`)

- **Fases 1-3 del arquitecto: COMPLETADO** ya en el commit inicial (motor básico, dominio +
  long-running, IA + 360). **`pytest` → 26/26** en la validación del 2026-07-09.
- **Fase 4 del arquitecto:** Helm, CLI, runbooks y SLA **hechos**; queda el plugin VS Code
  Tree-sitter, que está en Fase F del [[roadmap]] como opcional.
- **Suite: 286 passed + 3 skipped** (los skips son los e2e de métricas, que necesitan un
  Prometheus alcanzable), en 33 archivos entre unitarios y e2e contra el stack real.
- **`mypy .` en 0**, sobre **80** archivos incluidos los tests, y es el gate de CI — no
  `mypy teleflow`, que era menos estricto. Partía de 236 errores.
- **Fases A-E del [[roadmap]] cerradas**, salvo la protección de rama de Fase B, que depende
  de un tercero. Ver [[criterio-salida-fase-e]] y `docs/checklist-instalacion.md`.

## Decisiones de arquitectura

Las cinco originales del arquitecto:
[[2026-06-30-adr-001-lark-lalr]] · [[2026-06-30-adr-002-durable-sleep]] ·
[[2026-06-30-adr-003-llm-configurable]] · [[2026-06-30-adr-004-rabbitmq-en-stack]] ·
[[2026-06-30-adr-005-aislamiento-instancia]]

Las tomadas después (14 más, en `Knowledge/decisions/`). Las que cambian cómo se opera la
plataforma: [[2026-07-30-propiedad-de-instancia-en-el-executor]] ·
[[2026-07-30-scanner-de-negocio-multi-replica]] · [[2026-07-30-capa-de-datos-del-chart]] ·
[[2026-08-08-alcance-del-ha-de-la-capa-de-datos]] ·
[[2026-08-18-senal-de-escalado-del-executor]] · [[2026-07-25-auditoria-persistida]] ·
[[2026-07-25-estado-compartido-gateway]] · [[2026-07-14-clasificacion-errores-integracion]]
