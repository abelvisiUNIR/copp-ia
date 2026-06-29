// =====================================================================
// TeleFlow Platform — Documentación técnica completa
// Compilar:  typst compile docs/main.typ docs/TeleFlow-Platform-Docs-v1.0.pdf
// =====================================================================

#import "lib/theme.typ": *
#import "teleflow-portada.typ": portada
#import "teleflow-vision.typ": vision
#import "teleflow-arquitectura.typ": arquitectura
#import "teleflow-dsl-reference.typ": dsl_reference
#import "teleflow-api-reference.typ": api_reference
#import "teleflow-adr.typ": adrs
#import "teleflow-deployment.typ": deployment

// ── Configuración global del documento ───────────────────────────────
#set document(
  title: "TeleFlow Platform — Documentación Técnica v1.0",
  author: "BPFocus · COPP-IA",
  date: datetime(year: 2026, month: 6, day: 11),
)

#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2cm),
  header: context {
    if counter(page).get().first() > 2 {
      grid(
        columns: (1fr, auto),
        text(size: 8pt, fill: tf-gray, "TeleFlow Platform  ·  Documentación Técnica v1.0"),
        text(size: 8pt, fill: tf-gray, "Confidencial"),
      )
      line(length: 100%, stroke: 0.5pt + tf-blue.lighten(60%))
    }
  },
  footer: context {
    if counter(page).get().first() > 2 {
      line(length: 100%, stroke: 0.5pt + rgb("#e5e7eb"))
      v(2pt)
      grid(
        columns: (1fr, auto),
        text(size: 8pt, fill: tf-gray,
          query(selector(heading).before(here())).last().body
        ),
        text(size: 8pt, fill: tf-gray,
          counter(page).display("1 / 1", both: true)
        ),
      )
    }
  },
  numbering: "1",
)

#set text(
  font: ("Inter", "Arial", "Helvetica Neue", "sans-serif"),
  size: 10pt,
  fill: tf-dark,
  lang: "es",
)

#set par(
  justify: true,
  leading: 0.75em,
)

#set heading(numbering: none)

#show heading.where(level: 1): it => {
  v(8pt)
  text(size: 16pt, weight: "bold", fill: tf-dark, it.body)
  v(4pt)
}

#show heading.where(level: 2): it => {
  v(6pt)
  text(size: 12pt, weight: "bold", fill: tf-dark, it.body)
  v(3pt)
}

#show heading.where(level: 3): it => {
  v(4pt)
  text(size: 10pt, weight: "bold", fill: tf-blue, it.body)
  v(2pt)
}

// ── Tabla de contenidos ───────────────────────────────────────────────
#show outline.entry.where(level: 1): it => {
  v(4pt)
  strong(it)
}

// ── PORTADA ───────────────────────────────────────────────────────────
#portada()

// ── TABLA DE CONTENIDOS ───────────────────────────────────────────────
#set page(margin: (top: 3cm, bottom: 2.5cm, left: 2.5cm, right: 2cm))

#align(center)[
  #v(20pt)
  #text(size: 26pt, weight: "black", fill: tf-dark, "Tabla de contenidos")
  #v(8pt)
  #line(length: 80pt, stroke: 2pt + tf-blue)
  #v(20pt)
]

#outline(
  title: none,
  depth: 2,
  indent: 1.5em,
)

#pagebreak()

// ── SECCIONES PRINCIPALES ─────────────────────────────────────────────
#set page(
  margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2cm),
)

// Sección 1 — Visión y propuesta de valor
= Visión y propuesta de valor
#vision()

#pagebreak()

// Sección 2+3 — Arquitectura
= Arquitectura del sistema
#arquitectura()

#pagebreak()

// Sección 4+5 — DSL y ciclos de vida
= TeleFlow DSL v2 — Referencia
#dsl_reference()

#pagebreak()

// Sección 6+7+8+9 — Event-driven, Vista 360, Durable sleep, API
= Arquitectura event-driven y API
#api_reference()

#pagebreak()

// Sección 10+11 — Despliegue, stack, DB
= Despliegue y stack tecnológico
#deployment()

#pagebreak()

// Sección 11 — ADRs
= Decisiones de arquitectura (ADRs)
#adrs()

#pagebreak()

// ── APÉNDICE A — Ejemplo completo ceibal.tflow ────────────────────────
= Apéndice A — Dominio Ceibal (ceibal.tflow)

text(size: 9pt)[
  El archivo #code("examples/ceibal.tflow") es el ejemplo canónico del DSL.
  Incluye los 9 tipos de bloque y cubre el flujo completo del dominio educativo de Ceibal.
]

#v(10pt)

#codeblock(lang: "tflow", title: "examples/ceibal.tflow — entity nino")[
entity "nino" {
  description: "Estudiante registrado en Ceibal"
  fields {
    ci:           string   required unique
    nombre:       string   required
    fecha_nac:    date     required
    departamento: string
    nivel:        enum["primaria", "secundaria", "utu"]
    dispositivo:  string   optional
    tutor_email:  string   optional
  }
  lifecycle {
    initial: "REGISTRADO"
    states ["REGISTRADO", "ACTIVO", "INSCRIPTO", "GRADUADO", "INACTIVO"]
    transitions {
      REGISTRADO -> ACTIVO     via "activar"
      ACTIVO     -> INSCRIPTO  via "inscribir"
      INSCRIPTO  -> ACTIVO     via "desinscribir"
      ACTIVO     -> GRADUADO   via "graduar"
      ACTIVO     -> INACTIVO   via "desactivar"
      INACTIVO   -> ACTIVO     via "reactivar"
    }
  }
  events {
    on_transition "activar"   emit "nino.activado"
    on_transition "inscribir" emit "nino.inscripto"
    on_transition "graduar"   emit "nino.graduado"
    on_field_change "nivel"   emit "nino.nivel_cambiado"
  }
  invariants {
    "edad >= 5 AND edad <= 18"
    "nivel != null WHEN estado == INSCRIPTO"
  }
}
]

#v(8pt)

#codeblock(lang: "tflow", title: "examples/ceibal.tflow — reglas event-driven")[
rule "activar_acceso_al_inscribirse" {
  on_event: "inscripcion.activada"
  execute:  process.activacion_acceso_plataforma
  with {
    nino_id:  event.from_id
    curso_id: event.to_id
  }
}

rule "detectar_abandono" {
  on_timer {
    after:     30 days
    since:     "inscripcion.activada"
    condition: days_since(relation.inscripcion.ultimo_acceso) >= 30
               OR relation.inscripcion.ultimo_acceso == null
  }
  execute: process.reenganche_estudiante
  with {
    nino_id:  relation.from_id
    curso_id: relation.to_id
  }
}
]

#pagebreak()

// ── APÉNDICE B — Quick start ──────────────────────────────────────────
= Apéndice B — Quick start

#subsection(num: "B.1", title: "Instalar y arrancar")

#block(fill: rgb("#1e293b"), inset: 10pt, radius: 5pt, width: 100%)[
  #set text(font: "Courier New", size: 8pt, fill: rgb("#e2e8f0"))
  ```bash
  # 1. Clonar y configurar
  git clone <repo>
  cd govtech-platform
  cp .env.example .env

  # 2. Levantar el stack completo
  docker compose up --build -d

  # 3. Verificar servicios
  docker compose ps
  curl -s http://localhost:8000/health

  # 4. Desplegar con la CLI
  pip install -e .
  export TELEFLOW_URL=http://localhost:8000
  export TELEFLOW_API_KEY=dev-key-change-me
  tflow validate examples/ceibal.tflow
  tflow deploy examples/ceibal.tflow --name ceibal --version 1.0.0
  ```
]

#v(10pt)

#subsection(num: "B.2", title: "Ciclo de vida completo — Durable sleep")

#block(fill: rgb("#1e293b"), inset: 10pt, radius: 5pt, width: 100%)[
  #set text(font: "Courier New", size: 8pt, fill: rgb("#e2e8f0"))
  ```bash
  # Desplegar
  tflow deploy examples/venta_internet_hogar.tflow \
    --name venta_internet_hogar --version 1.0.0

  # Ejecutar proceso
  tflow execute --flow venta_internet_hogar \
    --payload '{"cliente_id":"cli-001","producto":"internet_100"}'

  # Verificar estado (duerme en aprobacion_gerencia)
  tflow status <instance_id>
  # status: WAITING_SIGNAL, current_step: aprobacion_gerencia

  # Enviar señal de aprobación
  tflow signal <instance_id> \
    --step aprobacion_gerencia --signal approve --actor juan.perez

  # Verificar completado
  tflow status <instance_id>
  # status: COMPLETED
  ```
]

#v(10pt)

#subsection(num: "B.3", title: "Observabilidad")

#block(fill: rgb("#1e293b"), inset: 10pt, radius: 5pt, width: 100%)[
  #set text(font: "Courier New", size: 8pt, fill: rgb("#e2e8f0"))
  ```bash
  # Prometheus — scraping de 5 targets
  open http://localhost:9090/targets

  # Grafana — dashboards tecnicos y de negocio
  open http://localhost:3001
  # admin / admin (cambiar en produccion)

  # Logs estructurados del executor
  docker compose logs -f executor-service
  ```
]

#v(20pt)

// ── Pie de página del documento ───────────────────────────────────────
#align(center)[
  #line(length: 100%, stroke: 0.5pt + rgb("#e5e7eb"))
  #v(8pt)
  #text(size: 8pt, fill: tf-gray,
    "TeleFlow Platform · Documento de Arquitectura v1.0 · Junio 2026 · BPFocus · COPP-IA")
  #v(4pt)
  #text(size: 8pt, fill: tf-gray, style: "italic", "Confidencial - No distribuir sin autorizacion")
]
