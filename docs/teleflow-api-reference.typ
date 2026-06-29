// =====================================================================
// TeleFlow Platform — Sección 6+7+8: Event-driven, Vista 360, Durable Sleep
//                     + API Reference completa
// =====================================================================
#import "lib/theme.typ": *

// helper: endpoint card
#let endpoint(method: "GET", path: "", auth: true, desc: "", body: none, response: none) = {
  let method-color = if method == "POST" { tf-blue }
    else if method == "GET" { tf-accent }
    else if method == "PATCH" { tf-warn }
    else if method == "DELETE" { tf-danger }
    else { tf-gray }

  block(
    stroke: 0.5pt + rgb("#e5e7eb"),
    radius: 5pt,
    inset: 0pt,
    clip: true,
    width: 100%,
  )[
    // Header
    #block(
      fill: method-color.lighten(85%),
      inset: (x: 10pt, y: 7pt),
      width: 100%,
    )[
      #box(
        fill: method-color,
        inset: (x: 6pt, y: 2pt),
        radius: 3pt,
        text(size: 8.5pt, weight: "bold", fill: white, method)
      )
      #h(8pt)
      #text(size: 9.5pt, weight: "bold", font: "Courier New", fill: tf-dark, path)
      #if auth { h(8pt); badge(label: "API-KEY", color: tf-gray) }
      #if desc != "" {
        h(8pt)
        text(size: 8.5pt, fill: tf-gray, desc)
      }
    ]
    // Body / Response
    #if body != none or response != none {
      block(inset: (x:10pt, y:8pt), width: 100%)[
        #if body != none {
          text(size: 8pt, weight: "bold", fill: tf-gray, "REQUEST BODY")
          v(2pt)
          text(font: "Courier New", size: 8pt, fill: rgb("#374151"), body)
          if response != none { v(6pt) }
        }
        #if response != none {
          text(size: 8pt, weight: "bold", fill: tf-gray, "RESPONSE")
          v(2pt)
          text(font: "Courier New", size: 8pt, fill: rgb("#374151"), response)
        }
      ]
    }
  ]
  v(8pt)
}

#let api_reference() = {

  // ── 6 Arquitectura event-driven ────────────────────────────────────
  section-header(num: "6", title: "Arquitectura event-driven")

  subsection(num: "6.1", title: "Modelo de tres capas")

  block(
    fill: tf-light,
    inset: 14pt,
    radius: 6pt,
    width: 100%,
  )[
    // Secuencia visual
    #grid(
      columns: (1fr, 0.4fr, 1fr, 0.4fr, 1fr, 0.4fr, 1fr),
      gutter: 0pt,
      align: top,

      // Entity
      block(fill: tf-blue.lighten(70%), inset: 8pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, weight: "bold", "entity / relation") \
          #v(4pt)
          #text(size: 7.5pt, fill: tf-gray, "emite evento al\ncompletar transición")
        ]
      ],
      align(center + horizon, text(size: 18pt, fill: tf-blue.lighten(30%), "→")),

      // RabbitMQ
      block(fill: tf-dark.lighten(15%), inset: 8pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, weight: "bold", fill: white, "RabbitMQ") \
          #v(4pt)
          #text(size: 7.5pt, fill: tf-gray.lighten(30%), "topic exchange\nteleflow.domain.events")
        ]
      ],
      align(center + horizon, text(size: 18pt, fill: tf-blue.lighten(30%), "→")),

      // Rule Engine
      block(fill: tf-accent.lighten(70%), inset: 8pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, weight: "bold", "rule engine") \
          #v(4pt)
          #text(size: 7.5pt, fill: tf-gray, "evalúa condición\ndispara proceso")
        ]
      ],
      align(center + horizon, text(size: 18pt, fill: tf-blue.lighten(30%), "→")),

      // Executor
      block(fill: tf-blue.lighten(50%), inset: 8pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, weight: "bold", fill: white, "executor") \
          #v(4pt)
          #text(size: 7.5pt, fill: white.transparentize(30%), "POST /internal/execute\nnueva instancia")
        ]
      ],
    )

    #v(10pt)

    #callout(kind: "info", title: "on_timer — trigger temporal")[
      El rule engine escanea periódicamente la tabla #code("entity_events") buscando eventos
      de tipo #code("since") con antigüedad mayor a #code("after_seconds"). Evalúa la condición
      y, si es verdadera y no existe registro en #code("rule_timer_log"), dispara el proceso e
      inserta el log para garantizar idempotencia.
    ]
  ]

  v(14pt)

  subsection(num: "6.2", title: "Flujo completo del dominio Ceibal")

  block(
    fill: tf-light,
    inset: 14pt,
    radius: 6pt,
    width: 100%,
  )[
    #for (step-num, event, rule, process-name) in (
      ("1", "curso.disponible",          "notificar_oferta",               "notificacion_oferta_curso"),
      ("2", "inscripcion.activada",      "activar_acceso_al_inscribirse",  "activacion_acceso_plataforma"),
      ("3", "nino.activado (sin disp.)", "prioridad_dispositivo",          "asignacion_dispositivo"),
      ("4", "inscripcion.completada",    "emitir_certificado_al_completar","emision_certificado"),
      ("5", "timer: 30 días sin acceso", "detectar_abandono",              "reenganche_estudiante"),
    ) {
      grid(
        columns: (20pt, 1fr, 1fr, 1fr),
        gutter: 8pt,
        align: (center, left, left, left),
        block(fill: tf-blue, inset: (x:5pt, y:3pt), radius: 10pt,
          text(size: 8pt, weight: "bold", fill: white, step-num)
        ),
        block[
          #text(size: 7.5pt, weight: "bold", fill: tf-gray, "EVENTO") \
          #text(size: 8.5pt, fill: tf-dark, event)
        ],
        block[
          #text(size: 7.5pt, weight: "bold", fill: tf-gray, "REGLA") \
          #text(size: 8.5pt, fill: tf-blue, rule)
        ],
        block[
          #text(size: 7.5pt, weight: "bold", fill: tf-gray, "PROCESO") \
          #text(size: 8.5pt, fill: tf-accent.darken(10%), process-name)
        ],
      )
      v(4pt)
    }
  ]

  v(24pt)

  // ── 7 Vista 360 ────────────────────────────────────────────────────
  section-header(num: "7", title: "Vista 360 del objeto de negocio")

  subsection(num: "7.1", title: "Arquitectura de la vista 360")

  grid(columns: (1fr, 1fr), gutter: 14pt,
    block[
      #text(size: 9pt)[
        El endpoint #code("GET /entities/{type}/{id}/360") agrega en paralelo
        cinco fuentes de datos y devuelve una vista única del objeto de negocio.
      ]
      #v(10pt)
      #tftable(
        headers: ("Fuente", "Descripción"),
        col-widths: (1fr, 1.5fr),
        rows: (
          ("entity_state",    "Estado actual y campos del entity"),
          ("relation_state",  "Relaciones activas e históricas"),
          ("process_instances","Procesos en vuelo filtrados por payload"),
          ("entity_events",   "Línea de tiempo de eventos"),
          ("rule conditions", "Alertas evaluadas en tiempo real"),
        ),
      )
    ],

    block[
      #text(size: 9pt, weight: "bold", fill: tf-dark, "Ejemplo de respuesta")
      #v(4pt)
      #codeblock(lang: "json", "{
  \"entity\": \"nino\",
  \"id\": \"uuid-juan-perez\",
  \"estado_actual\": \"INSCRIPTO\",
  \"campos\": {
    \"nombre\": \"Juan Pérez\",
    \"nivel\": \"secundaria\",
    \"departamento\": \"Montevideo\",
    \"dispositivo\": \"XO-4 asignado\"
  },
  \"relaciones_activas\": [{
    \"tipo\": \"inscripcion\",
    \"curso\": \"Robótica Básica\",
    \"estado\": \"ACTIVA\",
    \"progreso\": 65,
    \"ultimo_acceso\": \"2026-06-10\"
  }],
  \"procesos_activos\": [{
    \"flow\": \"asignacion_dispositivo\",
    \"status\": \"IN_PROGRESS\",
    \"current_step\": \"verificar_stock\"
  }],
  \"alertas\": [{
    \"rule\": \"detectar_abandono\",
    \"severidad\": \"warning\",
    \"mensaje\": \"18 días sin acceso\"
  }],
  \"timeline\": [
    {\"evento\":\"nino.inscripto\",\"fecha\":\"2026-06-08\"},
    {\"evento\":\"nino.activado\", \"fecha\":\"2026-05-15\"},
    {\"evento\":\"nino.registrado\",\"fecha\":\"2026-05-15\"}
  ]
}
      ")
    ],
  )

  v(24pt)

  // ── 8 Durable sleep ────────────────────────────────────────────────
  section-header(num: "8", title: "Durable sleep — procesos de larga duración")

  subsection(num: "8.1", title: "Flujo de durable sleep")

  block(
    fill: tf-light,
    inset: 14pt,
    radius: 6pt,
    width: 100%,
  )[
    #for (i, (actor, action, detail)) in (
      ("executor-service", "Llega a step human_task",     "Persiste instancia → WAITING_SIGNAL en Postgres con cursor completo"),
      ("executor-service", "Suscribe a Redis",             "SUBSCRIBE teleflow:signal:{instance_id} — worker liberado, sin polling"),
      ("Actor humano",     "días o semanas después...",    ""),
      ("api-gateway",      "POST /instances/{id}/signal", "{ signal: \"approve\", actor_id: \"juan.p\", signal_data: {...} }"),
      ("executor-service", "Mensaje Redis recibido",       "Instancia → IN_PROGRESS, continúa DAG desde step siguiente"),
    ).enumerate() {
      if detail == "" and action == "días o semanas después..." {
        v(4pt)
        line(length: 100%, stroke: (dash: "dashed", paint: tf-gray.lighten(40%)))
        align(center, text(size: 8.5pt, fill: tf-gray, style: "italic", action))
        line(length: 100%, stroke: (dash: "dashed", paint: tf-gray.lighten(40%)))
        v(4pt)
      } else {
        grid(
          columns: (80pt, 1fr),
          gutter: 8pt,
          badge(label: actor, color: if actor == "Actor humano" { tf-warn } else if actor == "api-gateway" { tf-accent } else { tf-blue }),
          block[
            #text(size: 8.5pt, weight: "bold", fill: tf-dark, action) \
            #if detail != "" { text(size: 7.5pt, fill: tf-gray, detail) }
          ],
        )
        v(4pt)
      }
    }
  ]

  v(14pt)

  subsection(num: "8.2", title: "Garantías del durable sleep")

  grid(
    columns: (1fr, 1fr),
    gutter: 10pt,
    ..for (title-g, desc, color) in (
      ("Sin pérdida en restart", "El executor puede reiniciarse en cualquier momento. Al arrancar recupera todas las instancias IN_PROGRESS y WAITING_SIGNAL desde Postgres.", tf-accent),
      ("Latencia de ms",         "La reactivación llega por Redis pub/sub. No hay timers ni polling que introduzcan latencia artificial.", tf-blue),
      ("Idempotencia",           "La señal tiene signal_key único. Múltiples envíos del mismo signal_id no crean efectos duplicados (IntegrityError → silencioso).", tf-warn),
      ("Audit log completo",     "Cada señal registra quién la envió (actor_id), cuándo, y con qué datos. La tabla signals es el log de aprobaciones.", tf-dark),
    ) {
      (block(
        fill: color.lighten(80%),
        stroke: (left: 3pt + color),
        inset: (x: 10pt, y: 8pt),
        radius: (right: 4pt),
      )[
        #text(size: 9pt, weight: "bold", fill: color.darken(10%), title-g) \
        #v(3pt)
        #text(size: 8.5pt, fill: tf-dark, desc)
      ],)
    }
  )

  v(24pt)

  // ── API Reference ──────────────────────────────────────────────────
  section-header(num: "9", title: "Referencia de la API")

  callout(kind: "info", title: "Autenticación")[
    Todos los endpoints requieren el header #code("X-TeleFlow-API-Key: <key>").
    La key se configura en la variable de entorno #code("TELEFLOW_API_KEY").
    Las peticiones sin key o con key inválida reciben #code("401 Unauthorized").
  ]

  v(10pt)

  subsection(num: "9.1", title: "Flows")
  endpoint(
    method: "POST", path: "/flows/{name}",
    desc: "Registra o actualiza un flow (parse + deploy)",
    body: "{ \"source\": \"<contenido .tflow>\", \"version\": \"1.0.0\", \"description\": \"...\" }",
    response: "{ \"flow_id\": \"uuid\", \"name\": \"...\", \"version\": \"1.0.0\", \"status\": \"registered\" }",
  )
  endpoint(
    method: "GET", path: "/flows",
    desc: "Lista todos los flows registrados",
    response: "[{ \"name\": \"...\", \"version\": \"...\", \"latest\": true }]",
  )
  endpoint(
    method: "GET", path: "/flows/{name}",
    desc: "Obtiene metadata y source de la versión latest",
    response: "{ \"name\": \"...\", \"version\": \"...\", \"source\": \"...\", \"ast\": {...} }",
  )
  endpoint(
    method: "GET", path: "/flows/{name}/versions",
    desc: "Lista todas las versiones del flow",
    response: "[{ \"version\": \"1.0.0\", \"created_at\": \"...\" }]",
  )

  subsection(num: "9.2", title: "Ejecución de procesos")
  endpoint(
    method: "POST", path: "/execute",
    desc: "Dispara una nueva instancia de proceso (respuesta inmediata)",
    body: "{ \"flow_name\": \"...\", \"version\": \"latest\", \"payload\": {...}, \"correlation_id\": \"...\" }",
    response: "{ \"instance_id\": \"uuid\", \"status\": \"TRIGGERED\" }",
  )
  endpoint(
    method: "GET", path: "/instances/{id}",
    desc: "Estado actual de una instancia",
    response: "{ \"id\": \"uuid\", \"status\": \"IN_PROGRESS\", \"current_step\": \"...\", \"context\": {...} }",
  )
  endpoint(
    method: "GET", path: "/instances",
    desc: "Lista instancias con filtros opcionales",
    body: "Query params: flow_name, status, correlation_id",
    response: "[{ \"id\": \"uuid\", \"status\": \"...\", \"flow_name\": \"...\" }]",
  )
  endpoint(
    method: "POST", path: "/instances/{id}/signal",
    desc: "Envía señal a un human_task en WAITING_SIGNAL",
    body: "{ \"step_name\": \"aprobacion_gerencia\", \"signal\": \"approve\", \"actor_id\": \"...\", \"signal_data\": {...} }",
    response: "{ \"instance_id\": \"uuid\", \"step_name\": \"...\", \"signal\": \"approve\" }",
  )

  subsection(num: "9.3", title: "Entities y relaciones")
  endpoint(
    method: "POST", path: "/entities/{type}",
    desc: "Crea un nuevo entity",
    body: "{ \"entity_id\": \"...\", \"campos\": { \"nombre\": \"...\", \"ci\": \"...\" } }",
    response: "{ \"entity_type\": \"nino\", \"entity_id\": \"...\", \"estado\": \"REGISTRADO\" }",
  )
  endpoint(
    method: "POST", path: "/entities/{type}/{id}/transition",
    desc: "Ejecuta una transición de estado",
    body: "{ \"via\": \"activar\", \"campos\": {...} }",
    response: "{ \"estado\": \"ACTIVO\", \"event\": \"nino.activado\" }",
  )
  endpoint(
    method: "PATCH", path: "/entities/{type}/{id}",
    desc: "Actualiza campos (valida invariantes)",
    body: "{ \"campos\": { \"nivel\": \"secundaria\" } }",
    response: "{ \"entity_id\": \"...\", \"campos\": {...} }",
  )
  endpoint(
    method: "GET", path: "/entities/{type}/{id}/360",
    desc: "Vista 360 completa del entity",
    response: "{ estado, campos, relaciones_activas, procesos_activos, alertas, timeline }",
  )
  endpoint(
    method: "POST", path: "/relations/{type}",
    desc: "Crea una nueva relación",
    body: "{ \"from_id\": \"...\", \"to_id\": \"...\", \"campos\": {...} }",
    response: "{ \"relation_type\": \"...\", \"from_id\": \"...\", \"to_id\": \"...\", \"estado\": \"PENDIENTE\" }",
  )
  endpoint(
    method: "POST", path: "/relations/{type}/{id}/transition",
    desc: "Transiciona el estado de la relación",
    body: "{ \"via\": \"activar\" }",
    response: "{ \"estado\": \"ACTIVA\", \"event\": \"inscripcion.activada\" }",
  )

  subsection(num: "9.4", title: "Composer (IA)")
  endpoint(
    method: "POST", path: "/compose",
    desc: "Genera borrador .tflow desde descripción en lenguaje natural",
    body: "{ \"description\": \"Proceso de alta de servicio de agua para hogares...\", \"base_flow\": \"optional\" }",
    response: "{ \"draft_id\": \"uuid\", \"name\": \"...\", \"status\": \"pending\" }",
  )
  endpoint(
    method: "GET", path: "/drafts",
    desc: "Lista borradores pendientes de revisión",
    response: "[{ \"id\": \"uuid\", \"name\": \"...\", \"status\": \"pending\", \"created_at\": \"...\" }]",
  )
  endpoint(
    method: "POST", path: "/drafts/{id}/approve",
    desc: "Aprueba el borrador y lo despliega como flow",
    body: "{ \"version\": \"1.0.0\", \"description\": \"...\" }",
    response: "{ \"flow_id\": \"uuid\", \"status\": \"registered\" }",
  )
  endpoint(
    method: "POST", path: "/drafts/{id}/reject",
    desc: "Rechaza el borrador con comentario",
    body: "{ \"comment\": \"Falta la etapa de validación de identidad\" }",
    response: "{ \"draft_id\": \"uuid\", \"status\": \"rejected\" }",
  )

  subsection(num: "9.5", title: "Observabilidad")
  endpoint(method: "GET", path: "/health",  auth: false, desc: "Liveness probe — devuelve 200 si el proceso responde")
  endpoint(method: "GET", path: "/ready",   auth: false, desc: "Readiness probe — verifica conectividad con DB y dependencias")
  endpoint(method: "GET", path: "/metrics", auth: false, desc: "Métricas en formato Prometheus (http_requests_total, dsl_parse_total, etc.)")
}
