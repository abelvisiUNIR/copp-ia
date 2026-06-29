// =====================================================================
// TeleFlow Platform — Sección 2 y 3: Arquitectura
// =====================================================================
#import "lib/theme.typ": *

// ── helper: nodo de servicio ─────────────────────────────────────────
#let svc-box(name: "", port: "", desc: "", color: tf-blue) = block(
  fill: color,
  inset: (x: 10pt, y: 8pt),
  radius: 5pt,
  width: 100%,
)[
  #text(size: 9.5pt, weight: "bold", fill: white, name)
  #if port != "" [
    #h(4pt)
    #box(
      fill: white.transparentize(70%),
      inset: (x: 4pt, y: 1pt),
      radius: 3pt,
      text(size: 7.5pt, fill: white, ":" + port)
    )
  ]
  #if desc != "" [
    #linebreak()
    #text(size: 7.5pt, fill: white.transparentize(30%), desc)
  ]
]

// ── helper: infra box ────────────────────────────────────────────────
#let infra-box(name: "", role: "") = block(
  fill: tf-dark,
  inset: (x: 8pt, y: 6pt),
  radius: 4pt,
)[
  #text(size: 9pt, weight: "bold", fill: white, name)
  #linebreak()
  #text(size: 7.5pt, fill: tf-gray.lighten(30%), role)
]

// ── helper: flecha etiquetada ────────────────────────────────────────
#let arrow(label: "") = align(center)[
  #text(size: 20pt, fill: tf-blue.lighten(30%), "→")
  #if label != "" [
    #linebreak()
    #text(size: 7pt, fill: tf-gray, label)
  ]
]

#let arquitectura() = {

  section-header(num: "2", title: "Arquitectura general")

  // ── 2.1 Capas del sistema ──────────────────────────────────────────
  subsection(num: "2.1", title: "Capas del sistema")

  // Diagrama de capas (visual con bloques Typst)
  block(
    stroke: 1pt + rgb("#e5e7eb"),
    radius: 8pt,
    inset: 0pt,
    clip: true,
    width: 100%,
  )[
    // Capa 1 — IA
    #block(fill: tf-accent.lighten(80%), inset: 12pt, width: 100%)[
      #text(size: 8pt, weight: "bold", fill: tf-accent, "CAPA 1 — GENERACIÓN IA")
      #v(6pt)
      #grid(columns: (1fr, 1pt, 1fr, 1pt, 1fr), gutter: 0pt,
        block(fill: tf-accent.lighten(60%), inset: 8pt, radius: 4pt)[
          #text(size: 8.5pt, weight: "bold", "Analista de negocio") \
          #text(size: 7.5pt, fill: tf-gray, "Descripción en lenguaje natural")
        ],
        align(center + horizon, text(size: 16pt, fill: tf-accent, "→")),
        block(fill: tf-accent.lighten(60%), inset: 8pt, radius: 4pt)[
          #text(size: 8.5pt, weight: "bold", "LLM configurable") \
          #text(size: 7.5pt, fill: tf-gray, "Claude / GPT-4o / self-hosted")
        ],
        align(center + horizon, text(size: 16pt, fill: tf-accent, "→")),
        block(fill: tf-accent.lighten(60%), inset: 8pt, radius: 4pt)[
          #text(size: 8.5pt, weight: "bold", "review-ui :3100") \
          #text(size: 7.5pt, fill: tf-gray, "PR-style diff viewer")
        ],
      )
    ]

    // Flecha entre capas
    #block(fill: white, inset: 4pt, width: 100%,
      align(center, text(size: 20pt, fill: tf-blue.lighten(40%), "↓") +
        text(size: 7.5pt, fill: tf-gray, "  POST /flows/{name}"))
    )

    // Capa 2 — Engine
    #block(fill: tf-blue.lighten(85%), inset: 12pt, width: 100%)[
      #text(size: 8pt, weight: "bold", fill: tf-blue, "CAPA 2 — TELEFLOW ENGINE")
      #v(6pt)
      #grid(columns: (1fr, 1pt, 1fr, 1pt, 1fr, 1pt, 1fr), gutter: 0pt,
        svc-box(name: "api-gateway",       port: "8000", desc: "Auth · Rate limit",     color: tf-blue),
        align(center + horizon, text(size: 12pt, fill: tf-blue.lighten(30%), "→")),
        svc-box(name: "parser-service",    port: "8001", desc: "Lark · AST · Validación", color: tf-blue.darken(10%)),
        align(center + horizon, text(size: 12pt, fill: tf-blue.lighten(30%), "→")),
        svc-box(name: "registry-service",  port: "8003", desc: "Versiones · inmutable",  color: tf-blue.darken(10%)),
        align(center + horizon, text(size: 12pt, fill: tf-blue.lighten(30%), "↔")),
        svc-box(name: "executor-service",  port: "8002", desc: "DAG async · durable sleep", color: tf-blue.darken(20%)),
      )
    ]

    // Flecha entre capas
    #block(fill: white, inset: 4pt, width: 100%,
      align(center, text(size: 20pt, fill: tf-dark.lighten(40%), "↓") +
        text(size: 7.5pt, fill: tf-gray, "  SQL · pub/sub · AMQP"))
    )

    // Capa 3 — Infraestructura
    #block(fill: tf-dark.lighten(90%), inset: 12pt, width: 100%)[
      #text(size: 8pt, weight: "bold", fill: tf-dark, "CAPA 3 — INFRAESTRUCTURA DE DATOS")
      #v(6pt)
      #grid(columns: (1fr, 1fr, 1fr), gutter: 8pt,
        infra-box(name: "PostgreSQL :5432",  role: "Estado durable · audit log"),
        infra-box(name: "Redis :6379",       role: "Cache · pub/sub · durable sleep"),
        infra-box(name: "RabbitMQ :5672",    role: "Bus de eventos de dominio"),
      )
    ]

    // Flecha entre capas
    #block(fill: white, inset: 4pt, width: 100%,
      align(center, text(size: 20pt, fill: tf-warn.lighten(20%), "↓") +
        text(size: 7.5pt, fill: tf-gray, "  /metrics scraping"))
    )

    // Capa 4 — Observabilidad
    #block(fill: tf-warn.lighten(85%), inset: 12pt, width: 100%)[
      #text(size: 8pt, weight: "bold", fill: tf-warn, "CAPA 4 — OBSERVABILIDAD")
      #v(6pt)
      #grid(columns: (1fr, 1fr), gutter: 8pt,
        block(fill: tf-warn.lighten(60%), inset: 8pt, radius: 4pt)[
          #text(size: 8.5pt, weight: "bold", "Prometheus :9090") \
          #text(size: 7.5pt, fill: tf-gray, "Scraping de todos los servicios")
        ],
        block(fill: tf-warn.lighten(60%), inset: 8pt, radius: 4pt)[
          #text(size: 8.5pt, weight: "bold", "Grafana :3001") \
          #text(size: 7.5pt, fill: tf-gray, "Dashboards técnicos y de negocio")
        ],
      )
    ]
  ]

  v(24pt)

  // ── 3 Arquitectura de microservicios ──────────────────────────────
  section-header(num: "3", title: "Arquitectura de microservicios")

  subsection(num: "3.1", title: "Responsabilidades por servicio")

  tftable(
    headers: ("Servicio", "Puerto", "Responsabilidad única"),
    col-widths: (1.2fr, 0.6fr, 2.2fr),
    rows: (
      ("api-gateway",      "8000", "Único punto de entrada externo. Auth (X-TeleFlow-API-Key), token-bucket rate limiting por key, routing transparente a servicios internos."),
      ("parser-service",   "8001", "Recibe source .tflow y produce AST validado en JSON. Valida sintaxis (Lark LALR) Y semántica (estados, transiciones, referencias). Nunca ejecuta nada."),
      ("registry-service", "8003", "Almacena y versiona definiciones. Una versión registrada es inmutable (409 si se intenta reemplazar). Expone `latest` como pointer mutable."),
      ("executor-service", "8002", "Construye el DAG del flow con networkx, recorre steps async. Durable sleep para human_task. Rule engine (on_event/on_state/on_timer/on_relation). Vista 360. Entity/Relation state."),
      ("composer-service", "8004", "Abstracción LLM. Genera borradores .tflow desde lenguaje natural. Guarda drafts en Postgres para revisión PR-style."),
      ("review-ui",        "3100", "UI React+Vite para revisión PR-style de flows generados por IA. Diff viewer LCS personalizado."),
    ),
  )

  v(16pt)

  // ── 3.2 Flujo de deploy ──────────────────────────────────────────
  subsection(num: "3.2", title: "Flujo de deploy de un flow")

  block(
    fill: tf-light,
    inset: 14pt,
    radius: 6pt,
    width: 100%,
  )[
    #grid(
      columns: (auto, 1fr),
      gutter: 10pt,

      // Timeline
      stack(
        spacing: 0pt,
        ..range(4).map(i => {
          let items = (
            (tf-blue,   "Cliente → api-gateway"),
            (tf-blue.darken(10%), "api-gateway → parser-service"),
            (tf-blue.darken(20%), "parser-service → registry-service"),
            (tf-accent, "registry-service → cliente"),
          )
          let (color, _) = items.at(i)
          stack(
            spacing: 0pt,
            circle(radius: 6pt, fill: color),
            if i < 3 { rect(width: 2pt, height: 20pt, fill: rgb("#d1d5db")) },
          )
        })
      ),

      // Descripciones
      stack(
        spacing: 14pt,
        ..((
          ("POST /flows/{name}",             "Source .tflow + version + descripcion. Header: X-TeleFlow-API-Key"),
          ("Valida sintaxis y semantica",     "Lark LALR parsea. Transformer genera AST. Validator chequea coherencia."),
          ("Persiste version inmutable",      "Guarda source, AST JSON y checksum SHA-256. 409 si version ya existe."),
          ("Respuesta inmediata",             "{ flow_id, name, version, status: registered }"),
        ).map(((label, detail)) =>
          block[
            #text(size: 9pt, weight: "bold", fill: tf-dark, label)
            #linebreak()
            #text(size: 8.5pt, fill: tf-gray, detail)
          ]
        )),
      ),
    )
  ]

  v(16pt)

  // ── 3.3 Flujo de ejecución ──────────────────────────────────────
  subsection(num: "3.3", title: "Flujo de ejecución de proceso")

  grid(
    columns: (1fr, 1fr),
    gutter: 14pt,

    // Request
    block[
      #text(size: 9pt, weight: "bold", fill: tf-dark, "Solicitud (POST /execute)")
      #v(6pt)
      #codeblock(lang: "json", title: "Request", "POST /execute
{
  \"flow_name\": \"venta_internet_hogar\",
  \"version\": \"latest\",
  \"payload\": {
    \"cliente_id\": \"uuid-...\",
    \"producto\": \"internet_100\"
  },
  \"correlation_id\": \"ext-uuid-123\"
}

← { \"instance_id\": \"uuid\",
    \"status\": \"TRIGGERED\" }
      ")
    ],

    // Estado
    block[
      #text(size: 9pt, weight: "bold", fill: tf-dark, "Consulta de estado (GET /instances/{id})")
      #v(6pt)
      #codeblock(lang: "json", title: "Response", "{
  \"id\": \"uuid-...\",
  \"status\": \"WAITING_SIGNAL\",
  \"flow_name\": \"venta_internet_hogar\",
  \"current_step\": \"aprobacion_gerencia\",
  \"context\": {
    \"_cursor\": {
      \"stage\": 2,
      \"step\": 0
    }
  }
}
      ")
    ],
  )
}
