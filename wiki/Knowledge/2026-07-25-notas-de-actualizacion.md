---
project: copp-ia
type: notas-de-actualizacion
provenance: copp-ia@devyos@b99339e
created: 2026-07-25
updated: 2026-07-25
tags: [operacion, migraciones, equipo, actualizacion]
---

# Notas de actualización — 2026-07-25

> Para las otras dos personas del equipo, **antes de hacer pull**. Lo de este día toca el
> schema, el arranque de dos servicios y la configuración del stack: si se pullea sin leer
> esto, el stack va a fallar de formas que parecen bugs y no lo son.

## Lo mínimo, en orden

```bash
git pull
docker compose up --build -d      # --build no es opcional: ver "RabbitMQ" abajo
docker compose exec api-gateway alembic upgrade head   # o esperar al servicio `migrate`
```

Y **revisar el `.env`** antes de levantar (ver abajo).

---

## 1. Tres migraciones nuevas (`0003`, `0004`, `0005`)

| Migración | Qué agrega |
|---|---|
| `0003` | `flow_drafts.provider` y `flow_drafts.validation` |
| `0004` | tabla `audit_log` (auditoría de acciones) |
| `0005` | `process_instances.idempotency_key` con índice único |

Las tres son **aditivas y nullable**: no tocan datos existentes y no hay que migrar nada a
mano. El servicio `migrate` del compose las aplica solo al levantar; si tu flujo no lo usa,
corré `alembic upgrade head`.

**Si no las aplicás**, los servicios van a fallar al consultar columnas que no existen.

## 2. Tu `.env` puede impedir que arranque el composer

**Este es el que más va a confundir.** Si tu `.env` tiene un `LLM_PROVIDER` real
(`anthropic`, `openai`) **sin `LLM_API_KEY`**, el `composer-service` **no arranca**, a
propósito.

Antes, esa combinación caía al `stub` en silencio: el servicio levantaba, `POST /compose`
respondía 201 y el analista recibía un esqueleto con `TODO:` creyendo que lo había generado el
modelo — y el log registraba `provider=anthropic`, o sea que la única traza decía lo contrario
de lo que pasó.

**Qué hacer:** poné `LLM_PROVIDER=stub` (es el default de `.env.example` ahora) o cargá una
credencial real. Con `stub` el ciclo compose → review → deploy funciona igual; lo que genera
son esqueletos para editar a mano, y ahora la UI lo dice explícitamente.

## 3. RabbitMQ: `--build` obligatorio, y la DLQ vieja se pierde

El servicio `rabbitmq` ahora tiene **volumen** (`rabbitmq-data`) y **hostname fijo**
(`rabbitmq`). Sin las dos cosas, las colas y la DLQ no sobrevivían a recrear el contenedor:
`docker compose up --build` las vaciaba, y como la app las vuelve a declarar al reconectar, la
DLQ aparecía en **0** — que se lee como "no hubo fallas".

**Consecuencia para vos:** al actualizar, lo que hubiera en tu DLQ local **se pierde una última
vez** (el contenedor se recrea con el nombre de nodo nuevo). De ahí en adelante persiste.

## 4. El gateway ahora usa Redis

Para dos cosas: el contador del rate limit (antes era por proceso, así que con varias réplicas
el límite efectivo se multiplicaba) y la invalidación del cache de API keys entre réplicas.

**Si Redis no está, el gateway funciona igual**, degradado: limita por proceso y purga solo su
cache local. La degradación se cuenta en `teleflow_rate_limit_degraded_total` y
`teleflow_key_revocations_unpublished_total`.

## 5. `/ready` del gateway ahora depende de Postgres

Antes respondía "listo" siempre, incluso con la base caída — cuando no puede resolver ninguna
key de la tabla `api_keys`. Ahora hace `db_ping`.

**Dónde importa:** el chart de Helm usa `/ready` como `readinessProbe`, así que en k8s un
gateway sin base sale de rotación. Es lo correcto, pero es nuevo.

## 6. Si trabajás sobre el front

`review-ui` ahora tiene lockfile y el `Dockerfile` usa `npm ci`. Si tenías `node_modules`
local, corré `npm ci` para quedar igual que el build.

Los tests de UI (Playwright) se corren con el stack levantado:

```bash
cd review-ui && npm ci && npx playwright install chromium && npm test
```

## 7. Un detalle si estás en Windows

Se agregó `.gitattributes` para que los `.sh` se guarden con **LF**. Sin eso, git los dejaba
con CRLF y bash fallaba con `set: pipefail: invalid option name` — el script terminaba con
error. En Linux no se nota, así que el problema aparecía solo en desarrollo y nunca en CI.

---

## Qué NO cambió

- Ninguna ruta existente de la API cambió de contrato: lo que había sigue funcionando igual.
- No hay que reconfigurar Prometheus ni Grafana.
- Las API keys existentes siguen valiendo, con sus scopes.

## Novedades que quizás quieras usar

- **`GET /audit`** — quién hizo qué, cuándo y con qué resultado. Requiere el scope nuevo
  `audit:read`, que **no** se hereda: hay que otorgarlo. Ver el README.
- **`Idempotency-Key`** en `POST /execute` — reintentar deja de crear un segundo expediente.
- **`scripts/backup.sh` / `restore.sh`** — respaldo de Postgres con el restore probado.

## Fuentes
[[2026-07-25]] (la daily del día) · [[backlog-hardening]] ·
[[2026-07-25-composer-llm-fallos-explicitos]] · [[2026-07-25-auditoria-persistida]] ·
[[2026-07-25-idempotencia-execute]] · [[2026-07-25-estado-compartido-gateway]] ·
[[2026-07-25-que-se-respalda]]
