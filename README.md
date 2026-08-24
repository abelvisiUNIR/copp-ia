# TeleFlow Platform

**Business & Software as Code** — plataforma de orquestación empresarial que permite modelar, desplegar y ejecutar procesos de negocio como código declarativo (`.tflow`), con el mismo rigor con que Terraform gestiona infraestructura.

Implementación del [Documento de Arquitectura v1.0](docs/TeleFlow-Arquitectura-v1.0.md).

> TeleFlow no es SaaS: se instancia por organismo (ADR-005). El mismo `docker-compose.yml` y los mismos Helm charts sirven a todos.

## Arquitectura

| Servicio | Puerto | Responsabilidad |
|---|---|---|
| `api-gateway` | 8000 | Único punto de entrada. Auth (`X-TeleFlow-API-Key`), rate limit, routing |
| `parser-service` | 8001 | Lark LALR → AST JSON. Validación sintáctica y semántica |
| `executor-service` | 8002 | DAG engine async. Durable sleep. Rule engine. Entities/relations. Vista 360 |
| `registry-service` | 8003 | Versionado inmutable de flows. Pointer `latest` mutable |
| `composer-service` | 8004 | Abstracción LLM (ADR-003). Borradores `.tflow` desde lenguaje natural |
| `review-ui` | 3100 | UI React para revisión PR-style de flows generados por IA |
| `postgres` / `redis` / `rabbitmq` | 5432 / 6379 / 5672 | Estado durable · cache + pub/sub + sleep · bus de eventos |
| `prometheus` / `grafana` | 9090 / 3000 | Métricas y dashboards |

## Quickstart (desarrollo / staging)

```bash
cp .env.example .env        # ajustar TELEFLOW_API_KEY y LLM_*
docker compose up --build
```

Las migraciones Alembic corren automáticamente (servicio `migrate`).

- API gateway: http://localhost:8000/docs
- Review UI: http://localhost:3100
- Grafana: http://localhost:3000 (admin/admin)
- RabbitMQ mgmt: http://localhost:15672 (teleflow/teleflow)

### Desplegar el dominio de ejemplo (Ceibal)

```bash
pip install -e .            # instala el CLI tflow
set TELEFLOW_API_KEY=dev-key-change-me   # PowerShell: $env:TELEFLOW_API_KEY="..."

tflow validate examples/ceibal.tflow
tflow deploy examples/ceibal.tflow --name ceibal --version 1.0.0
tflow deploy examples/venta_internet_hogar.tflow --name venta_internet_hogar --version 1.0.0
tflow flows
```

### Ciclo de vida completo vía API

```bash
H='-H "X-TeleFlow-API-Key: dev-key-change-me" -H "Content-Type: application/json"'

# 1. Crear entidades
curl -X POST localhost:8000/entities/nino $H -d '{
  "fields": {"ci":"1.234.567-8","nombre":"Juan Pérez","fecha_nac":"2014-03-01",
             "departamento":"Montevideo","nivel":"primaria"}}'
curl -X POST localhost:8000/entities/curso $H -d '{
  "fields": {"nombre":"Robótica Básica","area":"robotica"}}'

# 2. Transicionar: REGISTRADO → ACTIVO (emite nino.activado →
#    la regla prioridad_dispositivo dispara asignacion_dispositivo)
curl -X POST localhost:8000/entities/nino/{id}/transition $H -d '{"via":"activar"}'

# 3. Crear la relación inscripción y activarla (emite inscripcion.activada →
#    la regla activar_acceso dispara activacion_acceso_plataforma)
curl -X POST localhost:8000/relations/inscripcion $H -d '{
  "from_id":"{nino_id}","to_id":"{curso_id}",
  "fields":{"fecha_inscripcion":"2026-06-10","modalidad":"virtual"}}'
curl -X POST localhost:8000/relations/inscripcion/{rid}/transition $H -d '{"via":"activar"}'

# 4. Vista 360
curl localhost:8000/entities/nino/{id}/360 $H
```

### Durable sleep (human_task)

```bash
# Disparar la venta: queda en WAITING_SIGNAL en el step aprobacion_gerencia
tflow execute venta_internet_hogar --payload '{"cliente_id":"c-1","producto":"fibra-300"}'
tflow status <instance_id>     # → WAITING_SIGNAL

# Días después... el gerente aprueba (idempotente por signal_id):
tflow signal <instance_id> --step aprobacion_gerencia --signal approve --actor juan.perez
tflow status <instance_id>     # → COMPLETED
```

El executor puede reiniciarse sin perder instancias dormidas: el estado vive en Postgres y la reactivación llega por Redis pub/sub (ADR-002).

### Capa IA (compose → review → deploy)

```bash
tflow compose alta_socio --description "Proceso de alta de socio con validación de identidad y aprobación manual"
# revisar el diff en http://localhost:3100 y aprobar, o:
tflow approve <draft_id> --version 1.0.0
```

El proveedor LLM se configura por instancia: `LLM_PROVIDER=anthropic|openai|ollama|stub` (ADR-003). Sin API key configurada se usa el modo `stub` (esqueleto editable).

## El lenguaje TeleFlow DSL v2

La gramática EBNF vive en [teleflow/dsl/teleflow.lark](teleflow/dsl/teleflow.lark) (ADR-001: fuente de verdad del lenguaje). Bloques: `entity`, `relation`, `rule`, `view360`, `process`, `step`, `integration`, `catalog`, `party`. Ver ejemplos completos en [examples/](examples/).

## Estructura del repo

```
teleflow/
  common/            config · logging structlog · métricas · DB · modelos SQLAlchemy
  dsl/               teleflow.lark · AST (dataclasses) · transformer · validador · evaluador
  parser_service/    :8001
  registry_service/  :8003
  executor_service/  :8002  (engine DAG, durable sleep, rule engine, entities, view360, adapters)
  gateway/           :8000
  composer_service/  :8004  (providers LLM + drafts PR-style)
  cli.py             CLI tflow
review-ui/           React + Vite (diff viewer PR-style)
alembic/             migraciones (no create_all en producción)
helm/teleflow/       chart para K8s/RKE2 (réplicas según sección 9.1)
observability/       prometheus.yml + dashboards Grafana
examples/            ceibal.tflow · venta_internet_hogar.tflow
tests/               pytest (parser, validador, evaluador, DAG)
```

## Desarrollo

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e .[dev]
pytest
mypy teleflow
```

Convenciones: tipado estricto, Pydantic v2 en la API, dataclasses en el AST, structlog con `instance_id`/`flow_name`/`step_name`, pytest-asyncio, Alembic.

## Producción

```bash
helm dependency update helm/teleflow
helm install teleflow helm/teleflow -n teleflow --create-namespace \
  --set image.repository=<registry>/teleflow \
  --set apiKeySecret=teleflow-secrets
```
