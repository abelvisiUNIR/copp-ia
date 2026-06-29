// =====================================================================
// TeleFlow Platform — ADRs (Architecture Decision Records)
// =====================================================================
#import "lib/theme.typ": *

#let adr-card(
  num: "",
  title: "",
  decision: "",
  alternatives: (),
  rationale: "",
  consequences: "",
  status: "ACCEPTED",
) = {
  let status-color = if status == "ACCEPTED" { tf-accent }
    else if status == "DEPRECATED" { tf-danger }
    else { tf-warn }

  block(
    stroke: 0.5pt + rgb("#e5e7eb"),
    radius: 6pt,
    inset: 0pt,
    clip: true,
    width: 100%,
  )[
    // Header
    #block(
      fill: tf-dark,
      inset: (x: 14pt, y: 10pt),
      width: 100%,
    )[
      #grid(
        columns: (1fr, auto),
        text(size: 10pt, weight: "bold", fill: white, "ADR-" + num + "  " + title),
        badge(label: status, color: status-color),
      )
    ]

    // Body
    #block(inset: (x: 14pt, y: 12pt), width: 100%)[
      #grid(
        columns: (0.9fr, 1.1fr),
        gutter: 16pt,

        // Izquierda
        stack(spacing: 10pt,
          block[
            #text(size: 8pt, weight: "bold", fill: tf-blue, "DECISIÓN")
            #v(4pt)
            #text(size: 9pt, fill: tf-dark, decision)
          ],
          if alternatives.len() > 0 { block[
            #text(size: 8pt, weight: "bold", fill: tf-gray, "ALTERNATIVAS CONSIDERADAS")
            #v(4pt)
            #for alt in alternatives [
              #text(size: 8.5pt, fill: tf-gray, "• " + alt) \
            ]
          ]},
        ),

        // Derecha
        stack(spacing: 10pt,
          block[
            #text(size: 8pt, weight: "bold", fill: tf-accent, "RAZONAMIENTO")
            #v(4pt)
            #text(size: 9pt, fill: tf-dark, rationale)
          ],
          block(
            fill: tf-light,
            inset: 10pt,
            radius: 4pt,
          )[
            #text(size: 8pt, weight: "bold", fill: tf-warn, "CONSECUENCIAS")
            #v(4pt)
            #text(size: 8.5pt, fill: tf-dark, consequences)
          ],
        ),
      )
    ]
  ]
  v(14pt)
}

#let adrs() = {

  section-header(num: "11", title: "Decisiones de arquitectura (ADRs)")

  text(size: 10pt)[
    Las ADRs documentan las decisiones técnicas significativas tomadas durante el diseño
    de TeleFlow. Cada ADR captura el contexto, las alternativas y las consecuencias para
    que el equipo pueda entender y evaluar los trade-offs en el futuro.
  ]

  v(16pt)

  adr-card(
    num: "001",
    title: "Lark + LALR para el parser DSL",
    status: "ACCEPTED",
    decision: "Usar Lark con el algoritmo LALR como parser del lenguaje .tflow. La gramática EBNF vive en teleflow/dsl/teleflow.lark y es la única fuente de verdad del lenguaje.",
    alternatives: (
      "PLY (lex/yacc en Python) — más verboso",
      "Parsimonious (PEG) — backtracking sin límite",
      "Tree-sitter — excelente para IDE, difícil integrar en Python runtime",
      "Parser combinador manual — frágil a largo plazo",
    ),
    rationale: "Lark ofrece la mejor relación entre legibilidad de gramática (EBNF nativo en Python), performance LALR determinístico en producción, y extensibilidad. El transformer Visitor/Transformer de Lark convierte el parse tree en dataclasses tipados con código mínimo. Tree-sitter se reserva para el plugin de VS Code en Fase 4.",
    consequences: "La gramática EBNF es la fuente de verdad: cualquier extensión del DSL requiere modificar teleflow.lark primero. El transformador debe actualizarse para cada nueva regla gramatical. Los errores de sintaxis incluyen línea/columna gracias al error reporting de Lark.",
  )

  adr-card(
    num: "002",
    title: "Durable sleep vía Redis pub/sub + Postgres",
    status: "ACCEPTED",
    decision: "Las instancias en WAITING_SIGNAL persisten su contexto completo en Postgres. Redis pub/sub las reactiva en milisegundos. La señal es idempotente por signal_key único (UNIQUE constraint).",
    alternatives: (
      "Polling activo — consume recursos, latencia variable",
      "Timer externo (cron job) — dependencia nueva, complejidad operativa",
      "Temporal.io — excelente pero requiere infraestructura propia y licencia",
      "Celery + Redis — acoplamiento fuerte, no soporta estado durable nativo",
    ),
    rationale: "El estado durable en Postgres garantiza que el executor puede reiniciarse sin perder instancias dormidas. Redis pub/sub provee reactivación con latencia de milisegundos sin polling activo. El modelo es conceptualmente idéntico al de Temporal.io pero con componentes estándar ya presentes en el stack. La idempotencia de señales (signal_key UNIQUE) garantiza exactamente-una-ejecución incluso con reintentos del cliente.",
    consequences: "El executor debe suscribirse a Redis al arrancar y recuperar instancias dormidas desde Postgres (_recover()). En entornos con networking inestable (Docker Desktop) el listener usa get_message con polling suave en lugar de listen() bloqueante.",
  )

  adr-card(
    num: "003",
    title: "LLM configurable por instancia de organismo",
    status: "ACCEPTED",
    decision: "El proveedor LLM se configura via variables de entorno (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL). La interfaz LLMProvider abstrae anthropic/openai/ollama/stub.",
    alternatives: (
      "LLM fijo (solo Anthropic/Claude) — no sirve para organismos con restricciones",
      "Configuración en DB — complejidad operativa sin beneficio",
      "Plugin system — sobre-ingeniería para 4 proveedores",
    ),
    rationale: "Cada organismo tiene restricciones propias: OSE puede usar Claude API; Antel puede requerir modelo self-hosted por regulación; el Ministerio puede necesitar datos en territorio nacional. La interfaz LLMProvider es un ABC de Python con un único método generate(prompt) → str. El cambio de proveedor es una variable de entorno, no un deploy de código.",
    consequences: "composer-service implementa AnthropicProvider, OpenAIProvider, OllamaProvider y StubProvider. StubProvider genera un esqueleto sintácticamente válido offline, útil para desarrollo y testing. Si LLM_API_KEY no está configurada, el servicio cae automáticamente a Stub.",
  )

  adr-card(
    num: "004",
    title: "RabbitMQ incluido en el stack",
    status: "ACCEPTED",
    decision: "RabbitMQ se incluye como servicio propio en docker-compose y los Helm charts. No se depende del broker del organismo cliente para la instalación inicial.",
    alternatives: (
      "Kafka — sobre-dimensionado para el volumen de eventos de un organismo",
      "Broker del organismo (RabbitMQ/Kafka externo) — bloquea el onboarding inicial",
      "Sin broker (directo via Postgres NOTIFY) — limita la integración con sistemas externos",
    ),
    rationale: "Simplifica el onboarding: docker compose up funciona sin configuración externa. Los organismos que ya tienen broker propio pueden configurar TeleFlow para usarlo desactivando el RabbitMQ del Compose (variable RABBITMQ_URL apuntando al externo). La migración a broker externo es un cambio de configuración, no de código.",
    consequences: "El stack es autosuficiente desde el primer día. El executor usa aio-pika para AMQP async. Los exchanges son de tipo topic con routing key = nombre del evento (nino.activado, inscripcion.activada, etc.).",
  )

  adr-card(
    num: "005",
    title: "Aislamiento por instancia — no multi-tenant",
    status: "ACCEPTED",
    decision: "Cada organismo tiene su propia instancia de TeleFlow con su propia base de datos. No hay row-level security ni schema switching.",
    alternatives: (
      "Multi-tenant con RLS en Postgres — viable pero suma complejidad operativa y de seguridad",
      "Multi-tenant con schemas separados — facilita backups por tenant pero complica las migraciones Alembic",
      "SaaS compartido — contradice el requisito de datos aislados de organismos públicos",
    ),
    rationale: "Modelo más simple de operar para organismos con equipos IT propios. Cada organismo conoce exactamente qué datos tiene y dónde. El aislamiento es físico, no lógico: imposible data leak entre organismos por bug de aplicación. Los templates y procesos se comparten vía Git, no vía DB compartida.",
    consequences: "Las actualizaciones de la plataforma se aplican via git pull + docker compose pull + docker compose up --build en cada instancia. No hay mecanismo automático de propagación. Los organismos grandes pueden operar múltiples instancias (ej: una por línea de negocio) con configuración independiente.",
  )

  v(20pt)

  // Resumen de ADRs
  section-header(num: "11.1", title: "Resumen de decisiones")

  tftable(
    headers: ("ADR", "Título", "Estado", "Impacto principal"),
    col-widths: (0.4fr, 1.2fr, 0.6fr, 1.8fr),
    rows: (
      ("001", "Lark + LALR",           "ACCEPTED", "Gramática EBNF como fuente de verdad. Extensiones del DSL empiezan en teleflow.lark"),
      ("002", "Durable sleep",         "ACCEPTED", "Postgres + Redis. Recovery automático en restart. Señales idempotentes"),
      ("003", "LLM configurable",      "ACCEPTED", "anthropic / openai / ollama / stub via env vars. Sin recompilación"),
      ("004", "RabbitMQ en el stack",  "ACCEPTED", "Stack autosuficiente desde docker compose up. Migración a broker externo = env var"),
      ("005", "Aislamiento por instancia", "ACCEPTED", "Una DB por organismo. Sin multi-tenancy. Aislamiento físico"),
    ),
  )
}
