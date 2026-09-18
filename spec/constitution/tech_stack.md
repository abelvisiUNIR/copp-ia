---
project: copp-ia
type: tech-stack
provenance: copp-ia@desarrollo@ef0a5e3
fuente: pyproject.toml, docker-compose.yml, helm/teleflow/, review-ui/package.json
updated: 2026-09-18
---

# Stack tecnico

> Espejo de los manifiestos del repo. Ante conflicto, mandan `pyproject.toml`,
> `docker-compose.yml` y el chart. Sirve para que una spec no proponga una dependencia que ya
> esta resuelta, ni una que contradiga una decision tomada.

## Backend — Python

`requires-python = ">=3.11"` (`pyproject.toml:10`). El CI corre en 3.11; el entorno local del
owner es 3.14.

| Dependencia | Para que |
|---|---|
| `fastapi` + `uvicorn[standard]` | Los 6 servicios HTTP |
| `lark` | Gramatica del DSL `.tflow` (LALR, ADR-001) |
| `networkx` | DAG de ejecucion |
| `httpx` | Cliente HTTP (incluye los proveedores LLM) |
| `aio-pika` | RabbitMQ — bus de eventos, colas `quorum` |
| `SQLAlchemy[asyncio]` + `asyncpg` + `alembic` | Postgres y migraciones |
| `redis` | Cache, pub/sub y durable sleep |
| `structlog` | Logging estructurado |
| `prometheus-client` | Metricas |
| `pydantic` + `pydantic-settings` | Modelos y configuracion |

Dev: `pytest`, `pytest-asyncio` (`asyncio_mode = "auto"`), `mypy`, `aiosqlite`, `pyyaml`.

**Sin Poetry, uv ni PDM**: setuptools y `pip install -e ".[dev]"`. Una spec que quiera cambiar
esto necesita un ADR.

## Servicios

Los puertos de la tabla son **internos del contenedor**. Al host el compose publica solo
`api-gateway` (8000), `review-ui` (3100→80), rabbitmq-mgmt (15672), Prometheus y Grafana: los
8001-8005 **no son alcanzables desde afuera**, que es lo que hace del gateway el unico punto de
entrada de verdad y no solo por convencion.

| Servicio | Puerto interno | Responsabilidad |
|---|---|---|
| `api-gateway` | 8000 | Unico punto de entrada. Auth `X-TeleFlow-API-Key`, rate limit, routing |
| `parser-service` | 8001 | Lark LALR → AST JSON, validacion sintactica y semantica |
| `executor-service` | 8002 | DAG engine async, durable sleep, rule engine, entities, vista 360 |
| `registry-service` | 8003 | Versionado inmutable de flows, pointer `latest` mutable |
| `composer-service` | 8004 | Abstraccion LLM (ADR-003), borradores `.tflow` |
| `metrics-service` | 8005 | Gauges de negocio. **Una sola replica, por diseño** (`test_metrics_service_contract.py`) |
| `review-ui` | 80 (publicado en 3100) | UI React de revision PR-style |

Los 6 servicios Python comparten **una sola imagen Docker**; el servicio se elige con
`command: uvicorn teleflow.<svc>.main:app`.

## Modelo de datos

Base compartida por todos los servicios: `teleflow/common/models.py` (ORM) y `alembic/versions/`
(migraciones). `common/config.py`, `db.py` y `models.py` no son una feature: cada `base-*` cita
las tablas que usa en vez de repetir el modelo. Las features nuevas que agregan tablas o columnas
siguen la numeracion (`0008`, ...) y tienen que convivir con los pods viejos durante un upgrade.

| Tabla | Creada en | Columnas agregadas despues |
|---|---|---|
| `flow_definitions` | `0001_initial.py:18` | — |
| `flow_latest` | `0001_initial.py:31` | — |
| `process_instances` | `0001_initial.py:38` | `idempotency_key` (`0005`), `driven_by` y `lease_expires_at` (`0006`) |
| `instance_transitions` | `0001_initial.py:53` | — |
| `entity_state` | `0001_initial.py:66` | — |
| `entity_events` | `0001_initial.py:77` | — |
| `relation_state` | `0001_initial.py:89` | — |
| `signals` | `0001_initial.py:100` | — |
| `flow_drafts` | `0001_initial.py:114` | `provider` y `validation` (`0003`), `source_generado` (`0007`) |
| `rule_timer_log` | `0001_initial.py:128` | — |
| `api_keys` | `0002_api_keys.py:18` | — |
| `audit_log` | `0004_audit_log.py:18` | — |

## Frontend

Solo `review-ui/`: React 18 + Vite 5, tests con Playwright (`npm ci`, `npm test`). npm con
`package-lock.json`.

## Infraestructura

- **Datos**: Postgres 5432, Redis 6379, RabbitMQ 5672 — los tres **solo internos**, el compose no
  los publica; al host sale unicamente la consola de RabbitMQ en 15672. Cluster de 3 con quorum
  queues en el chart. Camino externo de primera clase: `external<Comp>.existingSecret`.
- **Observabilidad**: Prometheus 9090, Grafana 3001 (no 3000: suele estar ocupado). Alertas en
  `helm/teleflow/alerts/alerts.yml`, **una sola fuente** para el compose y el chart.
- **Deploy**: `docker-compose.yml` para desarrollo/staging, Helm (`helm/teleflow/`) para k8s.
  Migraciones Alembic como Job con initContainers, **no** como hook de Helm.
- **CLI**: `tflow` (`teleflow.cli:main`).

## CI

`.github/workflows/ci.yml` — push a `desarrollo`, PR a `desarrollo`. Las ramas de chunk se cubren
por el PR y no por el push: listar cada rama era imposible y duplicaba la corrida. Jobs: `quality`
(mypy strict + pytest no-e2e), `e2e` (stack en compose + promtool + Playwright), `docker-build`,
`chart` (bateria de `helm template` con asserts sobre secrets, HPA y capa de datos externa).

`.github/workflows/imagenes.yml` — cron semanal que verifica que las imagenes referenciadas
sigan existiendo. Deliberadamente **fuera** del gate de merge: el artefacto no cambia y la
dependencia se rompe sola, asi que un job por push seria ciego por construccion.
