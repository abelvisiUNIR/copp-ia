// =====================================================================
// TeleFlow Platform — Sección 9+10: Despliegue, Stack tecnológico, DB Schema
// =====================================================================
#import "lib/theme.typ": *

#let deployment() = {

  section-header(num: "10", title: "Despliegue y operación")

  subsection(num: "10.1", title: "Modelo de despliegue")

  grid(
    columns: (1fr, 1fr),
    gutter: 16pt,

    // Desarrollo
    block(
      stroke: 2pt + tf-blue,
      radius: 6pt,
      inset: 14pt,
    )[
      #text(size: 10pt, weight: "bold", fill: tf-blue, "Desarrollo / Staging")
      #v(8pt)
      #codeblock(lang: "bash", "# Primer arranque
cp .env.example .env
# Editar TELEFLOW_API_KEY, LLM_API_KEY, etc.

docker compose up --build -d

# Verificar servicios
docker compose ps
curl http://localhost:8000/health
      ")
      #v(8pt)
      #text(size: 8.5pt)[Un solo servidor. Una imagen Docker para los 5 servicios Python.
      El comando selecciona el servicio via #code("uvicorn teleflow.<svc>.main:app").]
    ],

    // Producción
    block(
      stroke: 2pt + tf-accent,
      radius: 6pt,
      inset: 14pt,
    )[
      #text(size: 10pt, weight: "bold", fill: tf-accent, "Producción — Kubernetes / RKE2")
      #v(8pt)
      #codeblock(lang: "bash", "# Deploy con Helm
helm upgrade --install teleflow \\
  ./helm/teleflow \\
  --namespace teleflow \\
  --create-namespace \\
  -f values-production.yaml

# Escalar executor
kubectl scale deployment \\
  teleflow-executor-service \\
  --replicas=3 \\
  -n teleflow
      ")
      #v(8pt)
      #text(size: 8.5pt)[Namespace dedicado. StatefulSets para Postgres, Redis y RabbitMQ.
      Deployments con 2-3 réplicas para los servicios sin estado.]
    ],
  )

  v(16pt)

  subsection(num: "10.2", title: "Replicas recomendadas en producción")

  tftable(
    headers: ("Servicio", "Tipo K8s", "Réplicas mínimas", "Notas"),
    col-widths: (1fr, 0.9fr, 0.9fr, 1.8fr),
    rows: (
      ("api-gateway",      "Deployment",  "2",  "Sin estado. Detrás de Ingress/LoadBalancer"),
      ("parser-service",   "Deployment",  "2",  "Sin estado. CPU-bound (Lark LALR)"),
      ("registry-service", "Deployment",  "2",  "Sin estado. Lee de Postgres"),
      ("executor-service", "Deployment",  "3",  "Semáforo interno por réplica (WORKER_CONCURRENCY)"),
      ("composer-service", "Deployment",  "1",  "Llama a API externa. Sin estado local"),
      ("review-ui",        "Deployment",  "2",  "Nginx estático"),
      ("postgres",         "StatefulSet", "1+", "PVC dedicado. Recomendado: HA con patroni"),
      ("redis",            "StatefulSet", "1",  "Sentinel para HA en prod"),
      ("rabbitmq",         "StatefulSet", "3",  "Cluster quorum queue recomendado"),
    ),
  )

  v(16pt)

  subsection(num: "10.3", title: "Variables de entorno")

  tftable(
    headers: ("Variable", "Requerida", "Default", "Descripción"),
    col-widths: (1.2fr, 0.5fr, 0.8fr, 1.5fr),
    rows: (
      ("TELEFLOW_API_KEY",    "Sí",  "dev-key-change-me", "API key para el gateway. Cambiar en producción"),
      ("DATABASE_URL",        "Sí",  "—",                  "postgresql+asyncpg://user:pass@host:5432/teleflow"),
      ("REDIS_URL",           "Sí",  "—",                  "redis://host:6379/0"),
      ("RABBITMQ_URL",        "Sí",  "—",                  "amqp://user:pass@host:5672/"),
      ("POSTGRES_PASSWORD",   "Sí",  "teleflow",           "Password del usuario Postgres"),
      ("RABBITMQ_PASSWORD",   "Sí",  "teleflow",           "Password del usuario RabbitMQ"),
      ("LLM_PROVIDER",        "No",  "stub",               "anthropic | openai | ollama | stub"),
      ("LLM_API_KEY",         "No",  "—",                  "Clave del proveedor LLM (requerida si no stub)"),
      ("LLM_MODEL",           "No",  "—",                  "Modelo a usar (ej: claude-fable-5, gpt-4o)"),
      ("LLM_BASE_URL",        "No",  "—",                  "Para Ollama: http://host:11434"),
      ("WORKER_CONCURRENCY",  "No",  "10",                 "Semáforo del executor: instancias concurrentes"),
      ("TIMER_SCAN_INTERVAL", "No",  "60",                 "Segundos entre escaneos del rule engine on_timer"),
      ("BUSINESS_METRICS_INTERVAL", "No", "30",            "Segundos entre recálculos de los gauges de negocio (backlog de human_tasks)"),
      ("RATE_LIMIT_RPM",      "No",  "120",                "Requests por minuto por API key en el gateway"),
      ("GRAFANA_PORT",        "No",  "3001",               "Puerto del host para Grafana (default 3001, no 3000)"),
      ("GRAFANA_PASSWORD",    "No",  "admin",              "Password del admin de Grafana"),
    ),
  )

  v(16pt)

  callout(kind: "warning", title: "Notas de entorno Windows / Docker Desktop")[
    - Las rutas con espacios ("Mi unidad", "Servicios SAS") no funcionan como
      bind mounts en Docker Desktop para Windows. Prometheus y Grafana usan Dockerfiles propios
      que copian la config con COPY (en lugar de bind mount).
    - El puerto 3000 puede estar ocupado por wslrelay. Usar #code("GRAFANA_PORT=3001").
    - Para enviar JSON con acentos desde PowerShell, usar
      #code("[Text.Encoding]::UTF8.GetBytes(json)") como body del request.
  ]

  v(20pt)

  subsection(num: "10.4", title: "CLI tflow — comandos disponibles")

  tftable(
    headers: ("Comando", "Descripción", "Ejemplo"),
    col-widths: (1fr, 1.3fr, 1.5fr),
    rows: (
      ("`tflow validate`",  "Valida un .tflow localmente sin desplegarlo",       "`tflow validate ceibal.tflow`"),
      ("`tflow deploy`",    "Parsea y registra en el registry",                  "`tflow deploy ceibal.tflow --name ceibal --version 1.0.0`"),
      ("`tflow flows`",     "Lista flows registrados",                           "`tflow flows`"),
      ("`tflow execute`",   "Dispara una instancia de proceso",                  "`tflow execute --flow ceibal --payload '{...}'`"),
      ("`tflow status`",    "Muestra estado de una instancia",                   "`tflow status <instance_id>`"),
      ("`tflow signal`",    "Envía señal a un human_task",                       "`tflow signal <id> --step aprobacion --signal approve`"),
      ("`tflow compose`",   "Genera borrador .tflow con IA",                     "`tflow compose --desc 'proceso de alta de cliente'`"),
      ("`tflow drafts`",    "Lista borradores pendientes de revisión",           "`tflow drafts`"),
      ("`tflow approve`",   "Aprueba y despliega un borrador",                   "`tflow approve <draft_id> --version 1.0.0`"),
    ),
  )

  v(20pt)

  // ── DB Schema ─────────────────────────────────────────────────────
  section-header(num: "10.5", title: "Schema de base de datos")

  text(size: 9pt)[
    Gestionado con Alembic. La migración inicial está en
    #code("alembic/versions/0001_initial.py"). No se usa #code("create_all()") en producción.
  ]

  v(10pt)

  // Tabla principal
  for (table-name, cols, notes) in (
    (
      "flow_definitions",
      (("id", "UUID PK"), ("name", "varchar(200)"), ("version", "varchar(50)"), ("source", "text"), ("ast", "JSONB"), ("checksum", "varchar(64) — SHA-256 del source"), ("status", "varchar(30) — registered/active/archived"), ("created_at", "timestamptz")),
      "UNIQUE(name, version). Una vez registrada, la row es inmutable.",
    ),
    (
      "process_instances",
      (("id", "UUID PK"), ("flow_name", "varchar"), ("flow_version", "varchar"), ("correlation_id", "varchar — índice"), ("status", "varchar(30) — TRIGGERED/IN_PROGRESS/WAITING_SIGNAL/COMPLETED/FAILED"), ("context", "JSONB — incluye _cursor: {stage, step}"), ("current_step", "varchar"), ("error", "JSONB nullable"), ("created_at / updated_at", "timestamptz")),
      "context._cursor es el estado durable del durable sleep.",
    ),
    (
      "signals",
      (("id", "UUID PK"), ("instance_id", "UUID FK → process_instances"), ("step_name", "varchar"), ("signal", "varchar(100)"), ("actor_id", "varchar nullable"), ("signal_data", "JSONB"), ("signal_key", "varchar(200) UNIQUE — idempotencia"), ("processed", "boolean"), ("created_at", "timestamptz")),
      "signal_key UNIQUE garantiza exactamente-una-ejecución.",
    ),
    (
      "entity_state",
      (("id", "UUID PK"), ("entity_type", "varchar(100)"), ("entity_id", "varchar(100)"), ("estado", "varchar(50)"), ("campos", "JSONB"), ("updated_at", "timestamptz")),
      "UNIQUE(entity_type, entity_id). Upsert en transiciones.",
    ),
    (
      "entity_events",
      (("id", "UUID PK"), ("entity_type", "varchar(100)"), ("entity_id", "varchar(100)"), ("event_name", "varchar(200)"), ("payload", "JSONB"), ("occurred_at", "timestamptz — índice")),
      "Log inmutable de eventos. Fuente para la Vista 360 y on_timer.",
    ),
    (
      "flow_drafts",
      (("id", "UUID PK"), ("name", "varchar"), ("description", "text"), ("source", "text — borrador generado"), ("base_source", "text nullable — original si es edición"), ("status", "varchar(30) — pending/approved/rejected"), ("comments", "JSONB array")),
      "Los borradores aprobados se despliegan como flow_definition.",
    ),
    (
      "rule_timer_log",
      (("id", "UUID PK"), ("rule_name", "varchar(200)"), ("subject_key", "varchar(300)"), ("fired_at", "timestamptz")),
      "UNIQUE(rule_name, subject_key). Evita doble disparo de on_timer.",
    ),
  ) {
    v(10pt)
    block(
      stroke: 0.5pt + rgb("#e5e7eb"),
      radius: 5pt,
      inset: 0pt,
      clip: true,
      width: 100%,
    )[
      #block(
        fill: tf-dark.lighten(10%),
        inset: (x: 12pt, y: 7pt),
        width: 100%,
      )[
        #text(font: "Courier New", size: 9.5pt, weight: "bold", fill: white, table-name)
        #h(10pt)
        #text(size: 8pt, fill: tf-gray.lighten(30%), notes)
      ]
      #block(inset: (x: 12pt, y: 8pt), width: 100%)[
        #grid(
          columns: (0.7fr, 1.3fr),
          gutter: 4pt,
          ..cols.map(((col, typ)) => (
            text(font: "Courier New", size: 8pt, fill: tf-blue, col),
            text(size: 8pt, fill: tf-gray, typ),
          )).flatten()
        )
      ]
    ]
  }

  v(24pt)

  // ── Stack tecnológico ─────────────────────────────────────────────
  section-header(num: "11", title: "Stack tecnológico")

  tftable(
    headers: ("Componente", "Tecnología", "Justificación"),
    col-widths: (0.9fr, 1fr, 2fr),
    rows: (
      ("Framework web",    "FastAPI + uvicorn",         "Async nativo, tipado con Pydantic v2, OpenAPI automático, performance comparable a Go para I/O bound"),
      ("Parser DSL",       "Lark (LALR)",               "Gramática EBNF en Python. Performance LALR determinístico. Transformer → dataclasses. Ver ADR-001"),
      ("DAG engine",       "networkx",                  "Construcción y traversal del DAG del flow. Detección de ciclos. API intuitiva para grafos dirigidos"),
      ("HTTP client",      "httpx",                     "Async nativo, HTTP/2, timeouts configurables. Usado en adapters REST y en el gateway"),
      ("AMQP client",      "aio-pika",                  "RabbitMQ async nativo asyncio. Topic exchange para routing por evento"),
      ("ORM",              "SQLAlchemy 2 async + asyncpg", "Async I/O nativo hacia Postgres. Mapped columns con Python typing. Sin ORMs que bloqueen el event loop"),
      ("Migraciones",      "Alembic",                   "Versionado de schema. No create_all() en producción. Historia completa de cambios"),
      ("Logging",          "structlog",                  "Logging estructurado JSON. instance_id, flow_name, step_name en cada línea"),
      ("Type checking",    "mypy --strict",             "Sin Any sin justificar. Pydantic v2 para modelos API, dataclasses para AST interno"),
      ("Testing",          "pytest-asyncio",            "Sin unittest. Fixtures async para todos los tests. 26/26 tests pasan"),
      ("Frontend",         "React + Vite",              "UI liviana para PR-style review de .tflow. Diff viewer LCS personalizado"),
      ("Observabilidad",   "Prometheus + Grafana",      "Dashboards técnicos (latencia, error rate) y de negocio (procesos completados, backlog)"),
      ("Contenedores",     "Docker + Helm/RKE2",        "Una imagen para 5 servicios Python. Helm charts para Kubernetes. docker compose para dev"),
      ("Redis",            "redis.asyncio (pub/sub)",   "Durable sleep reactivation. Cache de ASTs con TTL 30s. get_message en lugar de listen() para networking estable"),
      ("Mensajería",       "RabbitMQ 3.13",             "Topic exchange. aio-pika consumer en executor. management UI en :15672. Ver ADR-004"),
    ),
  )

  v(16pt)

  subsection(num: "11.1", title: "Convenciones de código")

  grid(
    columns: (1fr, 1fr),
    gutter: 14pt,

    stack(spacing: 8pt,
      callout(kind: "success", title: "Hacer")[
        #text(size: 8.5pt)[
          - mypy --strict en todos los servicios \
          - Pydantic v2 para request/response models \
          - Dataclasses para nodos AST (no Pydantic) \
          - structlog con campos contextuales siempre \
          - pytest-asyncio para todos los tests \
          - Alembic para cualquier cambio de schema \
          - /health (liveness) y /ready (readiness) en cada svc \
          - /metrics en formato Prometheus en cada svc
        ]
      ],
    ),

    stack(spacing: 8pt,
      callout(kind: "danger", title: "Nunca hacer")[
        #text(size: 8.5pt)[
          - create_all() o Base.metadata.create_all() en prod \
          - Any sin justificar en mypy \
          - unittest (usar pytest siempre) \
          - Exponer servicios internos fuera de la red Docker \
          - Credenciales hardcodeadas (usar \${env.VAR} en .tflow) \
          - Bloquear el event loop con operaciones síncronas pesadas \
          - Modificar una versión ya registrada en el registry
        ]
      ],
    ),
  )

  v(20pt)

  // ── Roadmap ───────────────────────────────────────────────────────
  section-header(num: "12", title: "Roadmap de implementación")

  block(
    fill: tf-light,
    inset: 14pt,
    radius: 6pt,
    width: 100%,
  )[
    #for (phase, color, items, status) in (
      (
        "Fase 1 — Motor básico",
        tf-blue,
        ("parser-service (Lark + AST + validación)", "registry-service (CRUD Postgres + semver)", "executor-service (sequential stages + REST adapters)", "api-gateway (auth + rate limit + routing)"),
        "COMPLETADO",
      ),
      (
        "Fase 2 — Dominio + long-running",
        tf-accent,
        ("entity + relation + rule en parser y executor", "executor: parallel stages + durable sleep + signals", "Adapters AMQP + SMTP + SMS", "Prometheus + Grafana + dashboards"),
        "COMPLETADO",
      ),
      (
        "Fase 3 — IA + 360",
        tf-warn,
        ("composer-service (abstracción LLM: Claude/GPT-4o/Ollama/Stub)", "review-ui (React PR-style + LCS diff viewer)", "view360 endpoint con 5 fuentes en paralelo", "Templates TMForum (6 procesos tipo)"),
        "COMPLETADO",
      ),
      (
        "Fase 4 — Producción",
        tf-dark,
        ("Helm charts K8s/RKE2 con values por entorno", "CLI tflow (validate/deploy/execute/signal/compose/approve)", "Plugin VS Code (Tree-sitter + syntax highlighting)", "SLA + runbooks + disaster recovery"),
        "EN PROGRESO",
      ),
    ) {
      grid(
        columns: (auto, 1fr),
        gutter: 10pt,
        align: top,
        // Indicador de fase
        block(fill: color, inset: (x:8pt, y:4pt), radius: 4pt,
          text(size: 8pt, weight: "bold", fill: white, phase)
        ) + " " + badge(label: status, color: if status == "COMPLETADO" { tf-accent } else { tf-warn }),

        block[
          #for item in items [
            #text(size: 8.5pt, fill: tf-dark, "✓  " + item) \
          ]
        ],
      )
      v(10pt)
    }
  ]
}
