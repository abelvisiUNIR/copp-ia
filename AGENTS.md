# AGENTS.md — copp-ia · TeleFlow Platform

Reglas para cualquier agente de IA que trabaje en este repo (Claude Code, OpenCode, Cursor,
Copilot, Codex). Es la fuente unica: `CLAUDE.md` la importa y solo agrega lo propio de Claude Code.
Todo el proyecto —codigo, docs, commits— esta en **español**.

## Que es

**Business & Software as Code**: plataforma de orquestacion donde un organismo modela, despliega
y ejecuta sus procesos de negocio como codigo declarativo (`.tflow`), con el rigor con que
Terraform gestiona infraestructura. **No es SaaS**: se instala por organismo, con datos
fisicamente aislados (ADR-005). Clientes objetivo: organismos publicos y empresas de servicios
(OSE, Antel, Ceibal). Detalle en `spec/constitution/mission.md`.

Direccion de producto vigente: la interfaz evoluciona de pantallas a un **asistente
conversacional con `@capacidades`** (ver `spec/features/asistente-conversacional/` cuando exista).
No se proponen pantallas nuevas por funcionalidad.

## Stack

Python ≥ 3.11 (FastAPI, Lark, networkx, SQLAlchemy async + Alembic, aio-pika, redis, structlog,
pydantic), React 18 + Vite 5 en `review-ui/`, Postgres / Redis / RabbitMQ, Prometheus + Grafana,
Docker Compose y Helm. Instalacion con setuptools (`pip install -e ".[dev]"`): **sin Poetry, uv ni
PDM**. Detalle, puertos y modelo de datos: `spec/constitution/tech_stack.md`.

## Mapa del repo

| Ruta | Que hay |
|---|---|
| `teleflow/dsl/` | Gramatica Lark (`teleflow.lark`, **unica fuente de verdad del lenguaje**), parser, validator, evaluator |
| `teleflow/gateway/` | Unico punto de entrada: auth por API key, scopes, rate limit, auditoria, proxy |
| `teleflow/parser_service/` · `registry_service/` · `executor_service/` · `composer_service/` · `metrics_service/` | Los otros 5 servicios (una sola imagen Docker) |
| `teleflow/common/` | Config, DB, modelos ORM, logging, observabilidad, reintentos |
| `teleflow/cli.py` | CLI `tflow` |
| `alembic/versions/` | Migraciones `0001`–`0007` |
| `tests/` · `tests/e2e/` | Unitarios y contratos · e2e contra el stack real (`-m e2e`) |
| `review-ui/` | UI React + tests Playwright |
| `helm/teleflow/` | Chart (tambien la **unica copia** de alertas y dashboards) |
| `observability/` | Dockerfiles de Prometheus/Grafana y test de alertas |
| `examples/` | Flows `.tflow` de referencia (tienen que validar limpios) |
| `docs/` | Documentacion formal en Typst (`*.typ` → PDF) |
| `spec/` | Especificaciones SDD: constitucion, linea base `base-*` y features futuras |
| `wiki/Knowledge/` | ADRs, roadmap, conceptos, backlog de hardening |
| `.claude/` | Subagentes, comandos, skills, hooks y reglas (los usa Claude Code; las instrucciones valen para todos) |

## Comandos

```bash
# Stack local
cp .env.example .env
docker compose up --build          # gateway :8000/docs · UI :3100 · Grafana :3001 · Prometheus :9090

# Entorno Python
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"

# Gates — nada se da por terminado sin estos
mypy .                              # strict sobre todo el repo, tiene que dar 0
pytest -m "not e2e" -q              # rapido, sin Docker
pytest -m e2e -q                    # requiere el stack levantado

# Alertas (promtool)
docker compose run --rm --no-deps -v "$PWD:/repo" -w /repo/observability --entrypoint promtool prometheus test rules alerts_test.yml

# UI
cd review-ui && npm ci && npm run test:install && npm test   # contra el stack en :3100

# Chart
helm template t helm/teleflow --set apiKey=x

# Migraciones / imagenes / docs / respaldo
alembic upgrade head
python scripts/verificar_imagenes.py
cd docs; .\compilar.ps1
scripts/backup.sh [destino] · scripts/restore.sh <dump> <base> [--confirmar]

# CLI
tflow validate|deploy|flows|execute|status|signal|compose|drafts|approve|openapi
```

## Convenciones

- **Commits**: Conventional Commits con scope, subject en español, en minuscula, sin punto final,
  describiendo el **resultado** y no la implementacion:
  `feat(dsl): que las ramas de una decision no se derramen una en otra`.
  Scopes: `dsl`, `gateway`, `composer`, `executor`, `registry`, `helm`, `ci`, `deploy`, `metrics`,
  `observability`, `review-ui`, `api`, `ops`, `dx`, `tests`, `docs`, `wiki`.
- **Ramas**: una rama por chunk de trabajo. `devyos` (personal) → PR a `desarrollo`.
- **Nombres de archivo** en kebab-case (modulos Python en snake_case, como el paquete).
- **Tests** nombrados por el comportamiento, en español (`test_una_carrera_da_409_y_no_500`).
- **Nada inventado**: toda afirmacion sobre el codigo cita `archivo:linea` y su provenance
  (`copp-ia@<rama>@<sha>`). Lo comprobado se separa de lo inferido, que se marca `(inferencia)`.
  La ruta va **desde la raiz del repo** (`teleflow/gateway/main.py:145`, no `main.py:145`: hay
  seis `main.py`). Un test se cita `tests/archivo.py::nombre_test`. Unica excepcion: dentro de
  una carpeta de `spec/features/`, los documentos hermanos se citan por nombre (`spec.md:42`).
- **Autoridad ante conflicto**: codigo > `docs/*.typ` > `.md` / README.
- **Toda extension del DSL empieza en `teleflow/dsl/teleflow.lark`** (ADR-001).
- **Doc que describe un modulo se actualiza en el mismo commit que cambia el modulo** (incluida su
  carpeta `spec/features/base-*`).

## Prohibido

- `git push` — lo hace siempre el owner. Commits locales si.
- **Agregar** `type: ignore` para pasar `mypy`: si el tipo no cierra, el problema es el tipo. Los
  que ya existen (middlewares de FastAPI y dos en `teleflow/executor_service/engine.py`) son deuda
  conocida: no se suman nuevos y se sacan cuando se toca ese codigo.
- Borrar, saltear o debilitar un test, relajar una validacion o cambiar un criterio de la spec
  para que el codigo "pase". Es una falla silenciosa (`wiki/Knowledge/concepts/fallas-silenciosas.md`).
- **Credenciales en cualquier archivo**, aunque este gitignoreado: este working tree se sincroniza
  a Google Drive y todo se replica. Secretos solo en variables de entorno o en el gestor del
  cluster (`existingSecret`).
- Secretos en la wiki, specs, descripciones o comentarios de Jira (se escribe `[REDACTED]`).
- Cambiar gestor de paquetes, framework o agregar dependencias sin un ADR.
- Asumir un solo proceso: el chart corre replicas (`wiki/Knowledge/concepts/supuesto-de-proceso-unico.md`).
- En Jira: crear Epics, borrar issues, editar o transicionar issues sin la label `spec-driven`,
  crear cualquier cosa sin dry-run y confirmacion.
- Editar una migracion Alembic ya publicada: se agrega una nueva.

## Flujo de trabajo: Spec-Driven Development

Cada funcionalidad se especifica en `spec/features/<carpeta>/` con cinco archivos. Detalle y
estados en `spec/README.md`.

| Etapa | Archivo | Subagente | Comando |
|---|---|---|---|
| Analisis de requisitos | `spec.md` | `analista-requisitos` | `/especificar` |
| Diseño / plan tecnico | `plan.md` | `disenador-tecnico` | `/disenar` |
| Desglose de tareas | `tasks.md` | `desglosador-tareas` | `/desglosar` |
| Implementacion IA | codigo + tests | `implementador` | `/implementar` |
| Revision | informe | `revisor` (solo lectura) | `/revisar` |
| Validacion contra spec | `validacion.md` | `validador-spec` | `/validar` |
| Seguridad e infraestructura (transversal) | `seguridad.md` | `seguridad-infra` | `/seguridad` |

- **Linea base**: `spec/features/base-*` (`status: implementada`, solo `spec.md` y `seguridad.md`)
  documenta lo que el codigo ya hace. Se escribe **bajo demanda**, cuando una feature toca el
  modulo, con `/as-built <modulo>`. Nunca se sincroniza con Jira.
- **Costo**: los subagentes se invocan **de a uno**, cuando la etapa lo necesita; nunca en tandas
  paralelas. Antes de encadenar mas de dos, se pide OK. `desglosador-tareas` y `validador-spec`
  corren en un modelo mas barato (`model: sonnet`).
- **Features nuevas**: `borrador` → (una persona decide) `consolidada` → `/sync-jira` en dry-run →
  confirmacion → `sincronizada`.
- **Ciclo que se autocorrige**: implementador → revisor → validador; un hallazgo vuelve al
  implementador. **Tope 3 vueltas por tarea**; despues se para y se escala a una persona.
- Decisiones que sobreviven a la feature → ADR en `wiki/Knowledge/decisions/`. Estado del
  roadmap → `wiki/Knowledge/roadmap.md`. Huecos → `wiki/Knowledge/backlog-hardening.md`.

## Higiene de contexto

- Notas de sesion, checkpoints y work-streams van en `wiki/Journal/` (gitignoreado, transitorio).
  Al cerrar un chunk se promueve a `wiki/Knowledge/` solo lo durable. **No** van en `docs/`, que es
  documentacion formal de producto.
- Para retomar un modulo, leer primero su `spec/features/base-*` y los ADRs que cita, no el codigo
  entero.

## Entorno local (Windows)

- Docker Desktop no puede bind-montear archivos desde esta ruta (tiene espacios): Prometheus y
  Grafana se construyen con Dockerfiles propios en `observability/` que hacen `COPY`.
- El puerto 3000 del host esta ocupado: Grafana mapea a 3001 (`GRAFANA_PORT`).
- PowerShell 5.1 + `Invoke-RestMethod`: para mandar JSON con acentos el body va como
  `[Text.Encoding]::UTF8.GetBytes($json)`.
