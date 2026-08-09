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

El paso 3 dispara `activacion_acceso_plataforma`, que **queda en FAILED** en el step
`crear_credenciales_lms`: ese step llama a un LMS real y el `.env.example` no trae su URL
(`${env.LMS_URL}`), porque el repo no puede traer un endpoint que no existe. El error dice qué
variable falta y falla en el primer intento, sin gastar reintentos. Todo lo demás del ejemplo
—entities, relations, rules, vista 360, durable sleep— funciona sin configurar nada.

Para verlo completo, apuntá `LMS_URL` a un endpoint que responda 2xx a `POST /api/credentials`.
Ojo: apuntarla a un host que **no resuelve** es peor que dejarla sin definir, porque un error de
red es transitorio y el step gasta todos sus reintentos con backoff antes de fallar.

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
helm/teleflow/       chart para K8s/RKE2 (réplicas según sección 10.2)
helm/teleflow/dashboards/  dashboards Grafana — única copia, la usan compose y el chart
helm/teleflow/alerts/      reglas de alerta — única copia, la usan compose y el chart
observability/       prometheus.yml + provisioning de Grafana + tests de las alertas
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

### Respaldo y restauración

**Postgres es lo único que hay que respaldar**: es el único estado que el producto no puede reconstruir. Redis es cache y coordinación, los dashboards viven en la imagen, y las colas son trabajo en vuelo (ver el ADR *qué se respalda*).

```bash
scripts/backup.sh                                   # -> backups/teleflow-YYYYmmdd-HHMMSS.dump
scripts/restore.sh backups/teleflow-....dump teleflow_verificacion
```

Se respalda con la base **arriba**: `pg_dump -Fc` toma una instantánea consistente sin bloquear escrituras. Parar el servicio convertiría el respaldo en una interrupción, y un respaldo que cuesta una ventana de mantenimiento se corre menos seguido.

`restore.sh` **exige la base destino** y no tiene default: restaurar es la operación que destruye datos. Sobre la base en uso pide `--confirmar`.

**El viaje de ida y vuelta está probado** (`tests/e2e/test_backup_restore_e2e.py`): escribe un dato reconocible, respalda, restaura en otra base y lo busca ahí. Un backup sin restore probado no es un respaldo, es un archivo.

**La rotación y el destino remoto quedan fuera**: dónde se guardan los dumps y por cuánto tiempo depende de la infraestructura y el marco normativo de cada organismo.

### Rate limit compartido entre réplicas

El límite (`RATE_LIMIT_RPM`, 120 por defecto) se cuenta **en Redis**, no en cada proceso: con `replicas: 2` el límite efectivo era el doble del configurado, porque cada réplica llevaba su propio contador. Ventana fija por minuto y por key, con la key **hasheada** (Redis no es lugar para una credencial, ni en el nombre de una clave); las entradas expiran solas.

**Si Redis no responde, el gateway degrada al contador en memoria** —lo de antes: limita por proceso— y lo cuenta en `teleflow_rate_limit_degraded_total`. Esa es la métrica a alertar: mientras suba, el límite vuelve a ser N× con N réplicas.

Costo medido: **+0,6 ms** sobre un request de ~7 ms (300 muestras por lado), dentro de la variación entre corridas.

### Revocación de credenciales con varias réplicas

Revocar o rotar una key la corta **en el acto y en todas las réplicas del gateway**, sin esperar el TTL del cache (`API_KEY_CACHE_TTL`, 30 s por defecto). El `DELETE` solo pasa por una réplica; las demás se enteran por un anuncio en Redis (canal `teleflow:keys:revocadas`) y purgan su cache local.

**Sin Redis el gateway funciona igual**, degradado: la purga local sigue andando y el TTL vuelve a ser el techo. Esa degradación no es silenciosa — se cuenta en `teleflow_key_revocations_unpublished_total`, que es la métrica a alertar: mientras suba, una credencial revocada puede seguir entrando hasta 30 s por réplica.

El chart declara `replicas: 2` para el gateway (`helm/teleflow/values.yaml`), así que esto **no es hipotético**.

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

Prometheus (`:9090`) scrapea `/metrics` de los servicios cada 15 s. Grafana (`:3001`) trae
dos dashboards provisionados en la carpeta *TeleFlow*:

| Dashboard | Responde |
|---|---|
| **TeleFlow · Overview** | Salud técnica: requests, latencia p95, tasa de error, throughput de steps |
| **TeleFlow · Negocio** | Trabajo pendiente: backlog de human_tasks por step y su antigüedad, procesos en curso por estado, terminados por hora |

Los gauges de negocio los publica **`metrics-service`, que corre en una sola réplica**. No es un
detalle de despliegue: los gauges llevan el valor absoluto y los paneles suman entre instancias,
así que dos procesos publicando hacen leer el doble del trabajo pendiente, sin que nada falle.
**No escalar ese servicio.**

### En Kubernetes

El chart trae los **puntos de integración**, no un stack de monitoreo: un organismo con
Kubernetes casi siempre ya tiene Prometheus y Grafana, y montarle un segundo le duplica
infraestructura y parte las métricas en dos lugares. Un organismo que no tenga nada necesita
instalar algo como `kube-prometheus-stack` aparte — este chart no se lo resuelve.

| Pieza | Default | Para qué |
|---|---|---|
| Anotaciones `prometheus.io/*` en los pods | **sí** | descubrimiento por anotaciones; inertes si nadie las mira |
| `ServiceMonitor` | no | Prometheus Operator. **Requiere su CRD**: encenderlo sin el operator hace fallar el install |
| ConfigMap con los dashboards | no | lo levanta el sidecar de Grafana buscando la etiqueta `grafana_dashboard` |
| `PrometheusRule` con las alertas | no | mismo CRD del Operator que el `ServiceMonitor`, misma razón para no venir puesto |

```bash
helm upgrade --install teleflow helm/teleflow -n teleflow   --set observabilidad.serviceMonitor.enabled=true   --set observabilidad.serviceMonitor.labels.release=kube-prometheus-stack   --set observabilidad.dashboards.enabled=true   --set observabilidad.prometheusRule.enabled=true   --set observabilidad.prometheusRule.labels.release=kube-prometheus-stack
```

La etiqueta del `ServiceMonitor` importa: muchas instalaciones solo adoptan los que la traen, y
sin ella el recurso se crea y **se ignora en silencio**.

La etiqueta del `PrometheusRule` importa por lo mismo. Y encenderlo **con el `ServiceMonitor`
apagado** deja la alerta de disponibilidad muda: la etiqueta `platform=teleflow` que la regla
filtra la estampa el `ServiceMonitor`. Las dos alertas de negocio funcionan igual, porque miran
nombres de métrica y no etiquetas.

Los dashboards viven en `helm/teleflow/dashboards/` y las reglas de alerta en
`helm/teleflow/alerts/`, no en `observability/`, porque Helm solo puede leer archivos de adentro
del chart. En los dos casos es una sola copia con dos consumidores —las imágenes del compose y
los recursos que genera el chart—, para que no haya dos versiones desincronizadas.

Las métricas de negocio son de dos clases y no se mezclan:

- **Counters de eventos** (`teleflow_instances_total`, `teleflow_steps_total`): cuentan lo que
  ya pasó, en el momento en que pasa.
- **Gauges de estado actual** (`teleflow_instances_current`, `teleflow_human_task_backlog`,
  `teleflow_human_task_oldest_seconds`): los recalcula un scanner de `metrics-service` cada
  `BUSINESS_METRICS_INTERVAL` (30 s) agregando `process_instances`. Un counter no puede
  responder "¿cuánta gente tiene trabajo pendiente ahora?" — para eso están estos.

Los gauges cubren solo los estados **vivos** (`TRIGGERED`, `IN_PROGRESS`, `RETRYING`,
`WAITING_SIGNAL`): los terminales ya los cuenta `teleflow_instances_total` y agregarlos
obligaría a escanear toda la historia de la tabla en cada ciclo.

### Alertas

Las reglas están en `helm/teleflow/alerts/alerts.yml` — una sola fuente que consumen el
Prometheus del compose (horneada en su imagen) y el `PrometheusRule` del chart. En el compose se
ven en la pestaña *Alerts* de Prometheus; no hay Alertmanager, porque a quién se le avisa es
decisión del organismo.

| Alerta | Dispara cuando | Gravedad |
|---|---|---|
| `TeleFlowServicioCaido` | un target de TeleFlow no responde al scrape hace 2 min | critical |
| `TeleFlowMetricasDeNegocioCongeladas` | los gauges de negocio llevan >3 min sin refrescarse | critical |
| `TeleFlowSinPublicadorDeMetricasDeNegocio` | no existe la serie de frescura hace >5 min | warning |

El criterio es alertar sobre **lo que no se nota**. Un gateway caído lo reporta el primer
usuario que entra; que los números de negocio dejen de actualizarse no lo reporta nadie:

- Si `metrics-service` **se cae**, los paneles muestran "No data", que se lee igual que "no hay
  trabajo pendiente". Corre en una sola réplica a propósito, así que no tiene quien lo
  reemplace.
- Peor: si el pod **sigue vivo pero no puede leer la base**, el refresh falla, se loguea y el
  servicio sigue —un fallo de métricas no debe bajar el servicio—, pero los gauges conservan el
  último valor. Un backlog congelado en 10 es indistinguible de un backlog estable de 10, y
  `up` vale 1. Para eso existe `teleflow_business_metrics_last_success_timestamp_seconds`: es la
  única señal que distingue "al día" de "quieto". El acompañante
  `teleflow_business_metrics_refresh_failures_total` separa las dos causas — sube si el refresh
  está fallando, queda quieto si el colector nunca arrancó.

Las reglas tienen tests unitarios (`observability/alerts_test.yml`, `promtool test rules`) que
corren en CI. No son ceremonia: una alerta con un nombre de métrica mal escrito es
sintácticamente válida y **nunca dispara**, que desde afuera se ve igual que un sistema sano.

### Imágenes de contenedor referenciadas

```bash
python scripts/verificar_imagenes.py --listar   # enumera las referencias del repo, sin red
python scripts/verificar_imagenes.py            # consulta el registry: ¿siguen existiendo?
```

Las imágenes se declaran en tres lugares (los `Dockerfile`, `docker-compose.yml` y
`helm/teleflow/values.yaml`) y el script las enumera de los tres, sin lista escrita a mano.

Dos chequeos distintos, a propósito:

- **Lo determinista gatea los merges** (`tests/test_imagenes_contract.py`, sin red): que la capa
  de datos use la **misma** imagen en el compose y en el chart —están declaradas dos veces y
  nada más las mantenía sincronizadas—, que el StatefulSet la tome de `values.yaml` y que ningún
  tag sea mutable.
- **Lo que depende del registry corre programado** (`.github/workflows/imagenes.yml`, semanal) y
  **no** bloquea merges. El motivo del trigger: las imágenes de los subcharts de Bitnami
  desaparecieron de Docker Hub y rompieron el chart sin que nadie tocara un archivo — un
  disparador por `push` no se habría enterado, porque no hubo push.

El script distingue "la imagen no existe" (exit 1) de "no pude consultar el registry" (exit 2).
Sin credenciales, el rate limit anónimo de Docker Hub cae en el segundo caso: para evitarlo, el
workflow hace login si están la variable `DOCKERHUB_USER` y el secreto `DOCKERHUB_TOKEN`.

### Runbooks de operación

Qué hacer cuando suena una alerta, cómo mirar la DLQ y cómo restaurar la base:
**[`docs/runbooks.md`](docs/runbooks.md)**. Todos sus comandos se ejecutaron contra el stack
real; lo que no se probó está marcado como tal en vez de omitido.

### Alta disponibilidad de la capa de datos

Lo que el chart entrega, y lo que deliberadamente no:

| | Default | HA |
|---|---|---|
| RabbitMQ | **3 réplicas en cluster**, colas quorum | **sí, y probado**: matando el nodo que aloja la cola, una cola clásica pierde el mensaje y la quorum lo conserva |
| Postgres | 1 réplica | **no** — se recomienda apuntar a la base administrada del organismo (abajo) |
| Redis | 1 réplica | **no**, y es un punto único de fallo asumido |

RabbitMQ es el único donde el HA **no se puede resolver desde afuera**: el tipo de cola lo
declara la aplicación al declararla, así que un broker administrado en cluster seguiría teniendo
colas clásicas —que viven en un solo nodo— si este código no pidiera quorum. Y ahí vive la DLQ,
o sea justo lo que ya falló una vez y no se puede volver a perder.

En Postgres y Redis pasa lo contrario: no hay nada que solo la plataforma pueda aportar, y un
organismo que ya opera una base administrada tiene mejor HA del que daría cualquier manifiesto de
este chart. Redis además guarda estado que **degrada** en vez de perderse (contadores de rate
limit, pub/sub de revocación, estado compartido del gateway; el durable sleep vive en Postgres).

El razonamiento completo y las alternativas descartadas están en el ADR de la wiki sobre el
alcance del HA de la capa de datos (2026-08-08).

Para desarrollo o un cluster de un solo nodo: `--set rabbitmq.replicas=1`.

### Apoyarse en la capa de datos del organismo

El chart instala Postgres, Redis y RabbitMQ propios (una réplica cada uno), que es lo razonable
para desarrollo y una instalación chica. **Para producción, lo recomendado en el caso de Postgres
es apuntar a la base administrada que el organismo ya opera**: tiene HA de verdad y gente de
guardia, que es más de lo que puede dar cualquier manifiesto de este chart.

```bash
helm install teleflow helm/teleflow --set apiKey=... \
  --set postgres.enabled=false \
  --set externalDatabase.host=pg.organismo.gub.uy \
  --set externalDatabase.port=6432 \
  --set externalDatabase.username=teleflow --set externalDatabase.database=teleflow \
  --set externalDatabase.sslMode=verify-full \
  --set externalDatabase.existingSecret=teleflow-db --set externalDatabase.urlKey=DATABASE_URL
```

Cada bloque `external*` acepta `host` (obligatorio: los initContainers esperan a que acepte
conexiones), `port`, credenciales propias, TLS opt-in (`sslMode` en Postgres, `tls` en Redis y
RabbitMQ) y `existingSecret` + `urlKey`.

**Con `existingSecret`, la URL completa la pone el organismo en un Secret que administra él y el
chart la consume por referencia: la contraseña no aparece en el spec del pod.** Sin él, la URL se
arma en el chart y la contraseña queda en texto plano en el env — hoy aparece **13 veces** en los
manifiestos renderizados. Es el límite conocido que cierra el ítem de secrets de Fase E.

Un `existingSecret` sin `urlKey` **corta el `helm install`** nombrando el bloque incompleto, en
vez de dejar el pod en `CreateContainerConfigError` con el motivo escondido en sus eventos.

El job `chart` de CI renderiza los cuatro modos (propio, externo, externo con Secret, externo a
medio configurar) porque ninguno de esos fallos se ve leyendo el diff.

## Doc vs. código: discrepancias conocidas

La doc consolidada (`.md` y PDF en `docs/`) es más vieja que los `.typ` y que el código. **Ante conflicto, el orden de verdad es: código > `.typ` > `.md`/README.**

| Tema | Dice la doc | Es |
|---|---|---|
| Puerto Grafana | 3000 (`.md` §9.2) | **3001** en el host (`docker-compose.yml:158`); 3000 es el puerto interno |
| Proveedores LLM | 3 (`.md` §9.3) | **4**: se omite `stub`, que además es el default del compose sin API key |
| Rule engine / vista 360 | gateway (diagrama `.md` §7.1) | **executor-service**; el gateway es proxy puro. El diagrama es vista lógica, no ubicación física |
| `mypy --strict` | convención vigente | ✅ vigente y en 0 — pero **no pasaba** hasta el saneamiento de 2026-07-09 (eran 236 errores) |

## Producción

El chart no tiene dependencias: Postgres, Redis y RabbitMQ son StatefulSets propios con las
**mismas imágenes oficiales que usa el `docker-compose.yml`**, así que lo que se prueba en dev y
en CI es la misma capa de datos que corre en producción. No hace falta `helm dependency update`.

```bash
# El Secret con las credenciales lo administra el organismo (recomendado en producción):
kubectl -n teleflow create secret generic teleflow-secrets \
  --from-literal=TELEFLOW_API_KEY='...'

helm install teleflow helm/teleflow -n teleflow --create-namespace \
  -f helm/teleflow/values-production.yaml \
  --set image.repository=<registry>/teleflow \
  --set existingSecret=teleflow-secrets
```

Sin `existingSecret` ni `apiKey`, el `helm install` **falla diciendo cuál de los dos falta**: una
API key por default que funciona deja la instalación arriba sin que nadie se entere.

Usar siempre un **tag de imagen inmutable**. Con un tag que se reescribe (`latest`, `dev`) más
`pullPolicy: IfNotPresent`, `helm upgrade` reporta `deployed` y los pods se quedan con el código
viejo: el pod spec no cambió, así que no hay rollout ni aviso.
