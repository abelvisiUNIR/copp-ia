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
| `prometheus` / `grafana` | 9090 / 3001 | Métricas y dashboards |

## Quickstart (desarrollo / staging)

```bash
cp .env.example .env        # ajustar TELEFLOW_API_KEY y LLM_*
docker compose up --build
```

Las migraciones Alembic corren automáticamente (servicio `migrate`).

- API gateway: http://localhost:8000/docs
- Review UI: http://localhost:3100
- Grafana: http://localhost:3001 (admin/admin) — `GRAFANA_PORT` lo cambia; 3000 suele estar ocupado
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

### Disparos idempotentes

Un reintento por timeout —el más común— crearía un segundo expediente: dos notificaciones al ciudadano, dos llamadas a la integración. Para evitarlo, mandá una `Idempotency-Key`:

```bash
curl -X POST "$API/execute" -H "X-TeleFlow-API-Key: $KEY" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"flow_name":"venta_internet_hogar","payload":{"cliente_id":"c-1"}}'
```

La primera llamada crea la instancia; las repeticiones devuelven **la misma**, con `idempotent_replay: true`. La clave **no expira**: vive con la instancia, así que un reintento tardío sigue protegido.

**Es opcional**: sin clave, cada llamada dispara (el comportamiento de siempre). Y **la misma clave con otro pedido da 409**, en vez de devolver la instancia vieja — recibir el resultado de otra operación creyendo que la propia se ejecutó es peor que un error visible.

### Capa IA (compose → review → deploy)

```bash
tflow compose alta_socio --description "Proceso de alta de socio con validación de identidad y aprobación manual"
# revisar el diff en http://localhost:3100 y aprobar, o:
tflow approve <draft_id> --version 1.0.0
```

El proveedor LLM se configura por instancia: `LLM_PROVIDER=anthropic|openai|ollama|stub` (ADR-003). El default es `stub`, que genera un esqueleto editable a mano y permite recorrer el ciclo compose → review → deploy sin credenciales. **Un proveedor real sin `LLM_API_KEY` hace que `composer-service` no arranque**: la alternativa —caer al `stub`— entregaba un esqueleto que parecía generado por el modelo.

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
mypy .          # todo el repo, igual que CI
```

Convenciones: tipado estricto, Pydantic v2 en la API, dataclasses en el AST, structlog con `instance_id`/`flow_name`/`step_name`, pytest-asyncio, Alembic.

`mypy .` cubre el repo entero (64 archivos) y es exactamente lo que corre CI. A los tests **no** se les exigen anotaciones de firma (`[tool.mypy.overrides]` en `pyproject.toml`): lo que se busca ahí es que un cambio de firma en `teleflow/` rompa el type check de sus tests, no anotar 350 funciones de test.

Los tests e2e (`tests/e2e/`) requieren el stack levantado; si el gateway no responde **se saltan**, así `pytest` sigue verde sin Docker.

### Contrato OpenAPI

```bash
tflow openapi                          # escribe docs/openapi.json
tflow openapi --output otro/lado.json
```

Sale del código (importa la app), así que **no hace falta el stack levantado**. Cada ruta declara `operation_id` y `tags` explícitos, para que un cliente generado tenga nombres estables: si se renombra la función Python, el método del cliente no cambia.

### Auditoría

Toda acción de **escritura** y **todo intento denegado** (401/403/429, incluso de lectura) queda registrado en la tabla `audit_log`: quién, qué, sobre qué, cuándo y con qué resultado. Las lecturas exitosas no se registran, salvo la lectura de la auditoría misma.

```bash
curl "$API/audit?limit=50"                    -H "X-TeleFlow-API-Key: $KEY"
curl "$API/audit?scope=flows:deploy"          -H "X-TeleFlow-API-Key: $KEY"
curl "$API/audit?solo_denegados=true"         -H "X-TeleFlow-API-Key: $KEY"
curl "$API/audit?subject=socio&desde=2026-07-01" -H "X-TeleFlow-API-Key: $KEY"
```

Requiere el scope `audit:read`, que se otorga explícitamente: no lo hereda `keys:admin` ni ningún otro.

**No se guarda el cuerpo de los requests** — por ahí pasan datos personales, y esta es la tabla que más tiempo se conserva. De un deploy se guardan la versión y el **checksum** del source, que responden "¿esta versión es la que se publicó?" sin almacenar el código.

**La tabla no se purga sola.** La retención es política de cada organismo: un despliegue con mucho tráfico de escritura va a querer una política de archivado. Borrar auditoría por un default del producto sería peor que la tabla creciendo.

## Observabilidad

Prometheus (`:9090`) scrapea `/metrics` de los 5 servicios cada 15 s. Grafana (`:3001`) trae
dos dashboards provisionados en la carpeta *TeleFlow*:

| Dashboard | Responde |
|---|---|
| **TeleFlow · Overview** | Salud técnica: requests, latencia p95, tasa de error, throughput de steps |
| **TeleFlow · Negocio** | Trabajo pendiente: backlog de human_tasks por step y su antigüedad, procesos en curso por estado, terminados por hora |

Las métricas de negocio son de dos clases y no se mezclan:

- **Counters de eventos** (`teleflow_instances_total`, `teleflow_steps_total`): cuentan lo que
  ya pasó, en el momento en que pasa.
- **Gauges de estado actual** (`teleflow_instances_current`, `teleflow_human_task_backlog`,
  `teleflow_human_task_oldest_seconds`): los recalcula un scanner del executor cada
  `BUSINESS_METRICS_INTERVAL` (30 s) agregando `process_instances`. Un counter no puede
  responder "¿cuánta gente tiene trabajo pendiente ahora?" — para eso están estos.

Los gauges cubren solo los estados **vivos** (`TRIGGERED`, `IN_PROGRESS`, `RETRYING`,
`WAITING_SIGNAL`): los terminales ya los cuenta `teleflow_instances_total` y agregarlos
obligaría a escanear toda la historia de la tabla en cada ciclo.

## Doc vs. código: discrepancias conocidas

La doc consolidada (`.md` y PDF en `docs/`) es más vieja que los `.typ` y que el código. **Ante conflicto, el orden de verdad es: código > `.typ` > `.md`/README.**

| Tema | Dice la doc | Es |
|---|---|---|
| Puerto Grafana | 3000 (`.md` §9.2) | **3001** en el host (`docker-compose.yml:158`); 3000 es el puerto interno |
| Proveedores LLM | 3 (`.md` §9.3) | **4**: se omite `stub`, que además es el default del compose sin API key |
| Rule engine / vista 360 | gateway (diagrama `.md` §7.1) | **executor-service**; el gateway es proxy puro. El diagrama es vista lógica, no ubicación física |
| `mypy --strict` | convención vigente | ✅ vigente y en 0 — pero **no pasaba** hasta el saneamiento de 2026-07-09 (eran 236 errores) |

## Producción

```bash
helm dependency update helm/teleflow
helm install teleflow helm/teleflow -n teleflow --create-namespace \
  --set image.repository=<registry>/teleflow \
  --set apiKeySecret=teleflow-secrets
```
