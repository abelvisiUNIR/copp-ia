// =====================================================================
// TeleFlow Platform — Sección 4 + 5: DSL Reference + Ciclos de vida
// =====================================================================
#import "lib/theme.typ": *

#let dsl_reference() = {

  section-header(num: "4", title: "TeleFlow DSL v2 — Referencia")

  text(size: 10pt)[
    El DSL es el corazón del producto. Un archivo #code(".tflow") es una declaración
    completa del dominio de negocio: entidades, relaciones, procesos, reglas e integraciones.
    La gramática EBNF vive en #code("teleflow/dsl/teleflow.lark") y es la fuente de verdad
    del lenguaje (ADR-001).
  ]

  v(14pt)

  // ── 4.1 Bloques disponibles ────────────────────────────────────────
  subsection(num: "4.1", title: "Bloques disponibles")

  tftable(
    headers: ("Bloque", "Estado", "Descripción"),
    col-widths: (0.8fr, 0.7fr, 2.5fr),
    rows: (
      ("`entity`",      "NUEVO v2",  "Objeto de negocio con identidad, campos tipados, máquina de estados explícita, invariantes y eventos emitidos por transición."),
      ("`relation`",    "NUEVO v2",  "Vínculo entre dos entities con su propio estado y ciclo de vida. El «producto instanciado» (ej: inscripción niño↔curso)."),
      ("`rule`",        "NUEVO v2",  "Regla de negocio event-driven. Cuatro tipos: on_event, on_state, on_timer, on_relation."),
      ("`view360`",     "NUEVO v2",  "Declara la vista 360 de un entity: estado, relaciones activas, procesos en vuelo, historial de eventos, alertas."),
      ("`process`",     "existente", "Orquesta steps en stages (sequential, parallel, decision). Puede emitir eventos y modificar estado de entities."),
      ("`step`",        "existente", "Tarea atómica reutilizable: automated, human_task, decision, notification."),
      ("`integration`", "existente", "Conectores externos: REST, AMQP/Kafka, SMTP, SMS. Credenciales via `${env.VAR}`."),
      ("`catalog`",     "existente", "Productos ofertables. Puede referenciar una entity como su instancia al contratarse."),
      ("`party`",       "existente", "Actores del proceso. Puede vincularse a una entity."),
    ),
  )

  v(20pt)

  // ── 4.2 Bloque entity ─────────────────────────────────────────────
  subsection(num: "4.2", title: "Bloque entity")

  grid(columns: (1fr, 1fr), gutter: 14pt,
    // Sintaxis
    block[
      #text(size: 9pt, weight: "bold", fill: tf-dark, "Sintaxis completa")
      #v(6pt)
      #codeblock(lang: "tflow", title: "entity", "entity \"nino\" {
  description: \"Estudiante Ceibal\"

  fields {
    ci:          string   required unique
    nombre:      string   required
    fecha_nac:   date     required
    departamento: string
    nivel:       enum[\"primaria\",\"secundaria\",\"utu\"]
    dispositivo: string   optional
  }

  lifecycle {
    initial: \"REGISTRADO\"
    states [\"REGISTRADO\",\"ACTIVO\",\"INSCRIPTO\",
            \"GRADUADO\",\"INACTIVO\"]

    transitions {
      REGISTRADO -> ACTIVO    via \"activar\"
      ACTIVO     -> INSCRIPTO via \"inscribir\"
      INSCRIPTO  -> ACTIVO    via \"desinscribir\"
      ACTIVO     -> GRADUADO  via \"graduar\"
      ACTIVO     -> INACTIVO  via \"desactivar\"
      INACTIVO   -> ACTIVO    via \"reactivar\"
    }
  }

  events {
    on_transition \"activar\"   emit \"nino.activado\"
    on_transition \"inscribir\" emit \"nino.inscripto\"
    on_transition \"graduar\"   emit \"nino.graduado\"
    on_field_change \"nivel\"   emit \"nino.nivel_cambiado\"
  }

  invariants {
    \"edad >= 5 AND edad <= 18\"
    \"nivel != null WHEN estado == INSCRIPTO\"
  }
}
      ")
    ],

    // Referencia de campos
    stack(spacing: 10pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Tipos de campo")
        #v(4pt)
        #tftable(
          headers: ("Tipo", "Descripción"),
          col-widths: (0.7fr, 1.3fr),
          rows: (
            ("`string`",   "Texto libre"),
            ("`number`",   "Entero o decimal"),
            ("`date`",     "Fecha (YYYY-MM-DD)"),
            ("`datetime`", "Fecha+hora con TZ"),
            ("`bool`",     "true / false"),
            ("`enum[...]`","Conjunto fijo de valores"),
          ),
        )
      ],
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Modificadores de campo")
        #v(4pt)
        #tftable(
          headers: ("Modificador", "Efecto"),
          col-widths: (1fr, 1.2fr),
          rows: (
            ("`required`",         "No nulo en create"),
            ("`optional`",         "Puede ser null"),
            ("`unique`",           "Índice único en DB"),
            ("`default(v)`",       "Valor por defecto"),
            ("`range(min, max)`",  "Validación de rango"),
          ),
        )
      ],
      callout(kind: "info", title: "Invariantes")[
        Se evalúan en cada PATCH y en cada transición de estado.
        Sintaxis: expresión booleana del evaluador TeleFlow.\
        #code("WHEN cond") hace que el invariante solo aplique cuando la condición es verdadera.
      ],
    ),
  )

  v(20pt)

  // ── 4.3 Bloque relation ───────────────────────────────────────────
  subsection(num: "4.3", title: "Bloque relation")

  grid(columns: (1fr, 1fr), gutter: 14pt,
    codeblock(lang: "tflow", title: "relation")[
relation "inscripcion" {
  description: "Niño ↔ Curso"

  from:        entity.nino
  to:          entity.curso
  cardinality: "many_to_many"
  constraint:  "max 3 cursos simultáneos"

  lifecycle {
    initial: "PENDIENTE"
    states ["PENDIENTE","ACTIVA",
            "COMPLETADA","ABANDONADA"]
    transitions {
      PENDIENTE -> ACTIVA     via "activar"
      ACTIVA    -> COMPLETADA via "completar"
      ACTIVA    -> ABANDONADA via "abandonar"
    }
  }

  fields {
    fecha_inscripcion: date   required
    modalidad:  enum["presencial","virtual"]
    progreso:   number default(0) range(0,100)
    ultimo_acceso: datetime   optional
  }

  events {
    on_transition "activar"  emit "inscripcion.activada"
    on_transition "completar" emit "inscripcion.completada"
    on_field_change "progreso"
      emit "inscripcion.progreso_actualizado"
  }
}
    ],

    stack(spacing: 10pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Cardinalidades soportadas")
        #v(4pt)
        #tftable(
          headers: ("Valor", "Semántica"),
          col-widths: (1fr, 1.2fr),
          rows: (
            (`"one_to_one"`,   "1 : 1"),
            (`"one_to_many"`,  "1 : N"),
            (`"many_to_many"`, "N : M (default)"),
          ),
        )
      ],
      callout(kind: "success", title: "API de relaciones")[
        #text(size: 8.5pt)[
          - #code("POST /relations/{type}") — crear relación\
          - #code("POST /relations/{type}/{id}/transition") — transicionar\
          - #code("PATCH /relations/{type}/{id}") — actualizar campos
        ]
      ],
      callout(kind: "info", title: "Identidad")[
        La relación se identifica por #code("(relation_type, from_id, to_id)").
        Los eventos incluyen #code("from_id") y #code("to_id") para que las
        reglas puedan extraerlos con #code("event.from_id") / #code("event.to_id").
      ],
    ),
  )

  v(20pt)

  // ── 4.4 Bloque rule ───────────────────────────────────────────────
  subsection(num: "4.4", title: "Bloque rule")

  grid(columns: (1fr, 1fr), gutter: 14pt,
    stack(spacing: 8pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "on_event — inmediato")
        #codeblock(lang: "tflow", "rule \"activar_acceso_al_inscribirse\" {
  on_event: \"inscripcion.activada\"
  execute:  process.activacion_acceso_plataforma
  with {
    nino_id:  event.from_id
    curso_id: event.to_id
  }
}
        ")
      ],
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "on_event + condición")
        #codeblock(lang: "tflow", "rule \"prioridad_dispositivo\" {
  on_event:  \"nino.activado\"
  condition: event.entity.dispositivo == null
  execute:   process.asignacion_dispositivo
  with {
    nino_id: event.entity_id
  }
}
        ")
      ],
    ),

    stack(spacing: 8pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "on_timer — temporal")
        #codeblock(lang: "tflow", "rule \"detectar_abandono\" {
  on_timer {
    after:     30 days
    since:     \"inscripcion.activada\"
    condition: days_since(
      relation.inscripcion.ultimo_acceso
    ) >= 30 OR
    relation.inscripcion.ultimo_acceso == null
  }
  execute: process.reenganche_estudiante
  with {
    nino_id:  relation.from_id
    curso_id: relation.to_id
  }
}
        ")
      ],
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Tipos de trigger")
        #tftable(
          headers: ("Tipo", "Cuándo dispara"),
          col-widths: (0.9fr, 1.5fr),
          rows: (
            ("`on_event`",    "Al recibir el evento del bus RabbitMQ"),
            ("`on_state`",    "Cuando entity/relation alcanza un estado"),
            ("`on_timer`",    "Si condición persiste N días después de evento"),
            ("`on_relation`", "Al crear/modificar/eliminar una relation"),
          ),
        )
      ],
    ),
  )

  v(20pt)

  // ── 4.5 Bloque process / stage ────────────────────────────────────
  subsection(num: "4.5", title: "Bloque process y stages")

  grid(columns: (1fr, 1fr), gutter: 14pt,
    stack(spacing: 8pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Stage sequential")
        #codeblock(lang: "tflow", "stage \"alta\" {
  mode: sequential
  steps [
    step.crear_credenciales_lms,
    step.notificar_acceso
  ]
}
        ")
      ],
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Stage parallel")
        #codeblock(lang: "tflow", "stage \"contacto\" {
  mode: parallel
  steps [
    step.notificar_tutor_abandono,
    step.recordatorio_estudiante
  ]
}
        ")
      ],
    ),

    stack(spacing: 8pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Stage decision (con branches)")
        #codeblock(lang: "tflow", "stage \"evaluacion_credito\" {
  mode: decision
  steps [step.consultar_buro]
  when signals.aprobacion_gerencia.signal
       == \"approve\"   -> stage.activacion
  else               -> stage.rechazo
}
        ")
      ],
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Modos de stage")
        #tftable(
          headers: ("Modo", "Comportamiento"),
          col-widths: (0.9fr, 1.5fr),
          rows: (
            ("`sequential`", "Steps en serie. El cursor avanza paso a paso."),
            ("`parallel`",   "Steps con asyncio.gather(). No admite human_task."),
            ("`decision`",   "Evalúa branches. Salta a otro stage o a stage.end."),
          ),
        )
      ],
    ),
  )

  v(20pt)

  // ── 4.6 Bloque step ───────────────────────────────────────────────
  subsection(num: "4.6", title: "Bloque step — atributos")

  tftable(
    headers: ("Atributo", "Tipo", "Aplica a", "Descripción"),
    col-widths: (1fr, 0.7fr, 1fr, 2fr),
    rows: (
      ("`type`",        "enum",     "todos",         "automated | human_task | decision | notification"),
      ("`integration`", "ref",      "automated",     "Referencia al bloque integration a usar"),
      ("`method`",      "string",   "automated REST","Verbo HTTP: GET, POST, PUT, PATCH, DELETE"),
      ("`path`",        "string",   "automated REST","Path del endpoint. Soporta interpolación ${...}"),
      ("`payload`",     "block",    "automated",     "Pares clave: expresión para el body de la llamada"),
      ("`retries`",     "number",   "automated",     "Intentos en caso de error (default: 0)"),
      ("`timeout`",     "duration", "automated",     "Ej: 30 seconds, 5 minutes"),
      ("`assignee`",    "string",   "human_task",    "Rol o usuario que debe resolver la tarea"),
      ("`signals`",     "list",     "human_task",    "Valores válidos de signal aceptados"),
      ("`channel`",     "string",   "notification",  "email | sms | amqp"),
      ("`to`",          "expr",     "notification",  "Destinatario (puede ser payload.field)"),
      ("`template`",    "string",   "notification",  "Mensaje con interpolación {payload.field}"),
      ("`condition`",   "expr",     "decision",      "Condición booleana. False → branch else"),
    ),
  )

  v(20pt)

  // ── 4.7 Evaluador de expresiones ─────────────────────────────────
  subsection(num: "4.7", title: "Evaluador de expresiones")

  grid(columns: (1fr, 1fr), gutter: 14pt,
    stack(spacing: 8pt,
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Operadores")
        #tftable(
          headers: ("Operador", "Ejemplo"),
          col-widths: (1fr, 1.2fr),
          rows: (
            ("==, !=",    "`estado == ACTIVO`"),
            (">=, <=, >, <", "`progreso >= 80`"),
            ("AND, OR, NOT", "`x >= 5 AND x <= 18`"),
            ("`in`",       "`estado in [\"A\",\"B\"]`"),
            ("`WHEN cond`", "`expr WHEN estado == X`"),
          ),
        )
      ],
      block[
        #text(size: 9pt, weight: "bold", fill: tf-dark, "Funciones built-in")
        #tftable(
          headers: ("Función", "Resultado"),
          col-widths: (1.2fr, 1fr),
          rows: (
            ("`days_since(field)`",  "Días desde fecha"),
            ("`years_since(field)`", "Años desde fecha"),
          ),
        )
      ],
    ),

    block[
      #text(size: 9pt, weight: "bold", fill: tf-dark, "Contexto disponible en expresiones")
      #v(6pt)
      #tftable(
        headers: ("Prefijo", "Apunta a"),
        col-widths: (1fr, 1.5fr),
        rows: (
          ("`event.*`",            "Campos del evento RabbitMQ actual"),
          ("`event.entity.*`",     "Estado del entity que emitió el evento"),
          ("`relation.*`",         "Campos de la relation sujeto"),
          ("`payload.*`",          "Payload del proceso en ejecución"),
          ("`signals.<step>.*`",   "Data de la señal recibida en human_task"),
          ("`instance.payload.*`", "Payload de la instancia (en view360 filter)"),
          ("nombre bare (sin punto)", "Literal string — para comparar con estados"),
        ),
      )
      #v(8pt)
      #callout(kind: "info", title: "Null safety")[
        Todas las comparaciones son null-safe. #code("x >= 30 OR x == null") es válido:
        si #code("x") es null, la parte #code("x >= 30") devuelve false y la
        condición completa se evalúa correctamente.
      ]
    ],
  )

  v(24pt)

  // ── 5 Ciclos de vida ──────────────────────────────────────────────
  section-header(num: "5", title: "Ciclos de vida")

  subsection(num: "5.1", title: "Máquina de estados — entity nino (Ceibal)")

  // Diagrama de estados manual con Typst
  block(
    fill: tf-light,
    inset: 16pt,
    radius: 6pt,
    width: 100%,
  )[
    #grid(
      columns: (auto, 1fr, auto, 1fr, auto),
      gutter: 0pt,
      align: center + horizon,

      // [*]
      circle(radius: 8pt, fill: tf-dark),

      // flecha
      stack(dir: ltr, spacing: 4pt,
        line(length: 100%, stroke: 1pt + tf-blue),
        text(size: 7pt, fill: tf-gray, "crear")
      ),

      // REGISTRADO
      block(fill: tf-blue.lighten(70%), inset: (x:10pt, y:6pt), radius: 4pt,
        text(size: 9pt, weight: "bold", "REGISTRADO")
      ),

      stack(dir: ltr, spacing: 4pt,
        line(length: 100%, stroke: 1pt + tf-blue),
        text(size: 7pt, fill: tf-gray, "activar →\nemit nino.activado")
      ),

      // ACTIVO
      block(fill: tf-accent.lighten(60%), inset: (x:10pt, y:6pt), radius: 4pt,
        text(size: 9pt, weight: "bold", fill: tf-accent.darken(20%), "ACTIVO")
      ),
    )

    #v(10pt)

    // Fila 2 — desde ACTIVO
    #grid(
      columns: (1fr,) * 3,
      gutter: 10pt,

      block(fill: tf-blue.lighten(80%), inset: 10pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, "ACTIVO → ") #text(weight: "bold", size: 8.5pt, "INSCRIPTO") \
          #text(size: 7.5pt, fill: tf-gray, "via \"inscribir\"\nemit nino.inscripto")
          #linebreak()
          #text(size: 8.5pt, "INSCRIPTO → ") #text(weight: "bold", size: 8.5pt, "ACTIVO") \
          #text(size: 7.5pt, fill: tf-gray, "via \"desinscribir\"")
        ]
      ],

      block(fill: tf-accent.lighten(80%), inset: 10pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, "ACTIVO → ") #text(weight: "bold", size: 8.5pt, "GRADUADO") \
          #text(size: 7.5pt, fill: tf-gray, "via \"graduar\"\nemit nino.graduado")
        ]
      ],

      block(fill: tf-warn.lighten(80%), inset: 10pt, radius: 4pt)[
        #align(center)[
          #text(size: 8.5pt, "ACTIVO → ") #text(weight: "bold", size: 8.5pt, "INACTIVO") \
          #text(size: 7.5pt, fill: tf-gray, "via \"desactivar\"")
          #linebreak()
          #text(size: 8.5pt, "INACTIVO → ") #text(weight: "bold", size: 8.5pt, "ACTIVO") \
          #text(size: 7.5pt, fill: tf-gray, "via \"reactivar\"")
        ]
      ],
    )
  ]

  v(16pt)

  subsection(num: "5.2", title: "Estados de una instancia de proceso")

  block(
    fill: tf-light,
    inset: 14pt,
    radius: 6pt,
    width: 100%,
  )[
    #grid(
      columns: (auto, 1fr) * 4,
      gutter: 6pt,
      align: center + horizon,

      ..for (state, color, arrow, label) in (
        ("TRIGGERED",      tf-blue,            "→", "executor\ninicia DAG"),
        ("IN_PROGRESS",    tf-accent,          "→", "human_task\nsin señal"),
        ("WAITING_SIGNAL", tf-warn,            "→", "POST /signal\nvía Redis"),
        ("COMPLETED",      tf-accent.darken(10%), "", ""),
      ) {
        (
          block(fill: color.lighten(60%), inset: (x:8pt,y:5pt), radius: 4pt,
            text(size: 8.5pt, weight: "bold", state)
          ),
          if arrow != "" {
            align(center, stack(
              text(size: 16pt, fill: color.lighten(20%), arrow),
              text(size: 7pt, fill: tf-gray, label)
            ))
          } else { [] },
        )
      }
    )

    #v(8pt)

    // Segunda fila: estados de error
    #grid(
      columns: (1fr,) * 3,
      gutter: 8pt,

      block(fill: tf-danger.lighten(80%), inset: 8pt, radius: 4pt)[
        #text(size: 8.5pt, weight: "bold", fill: tf-danger, "FAILED") \
        #text(size: 7.5pt, fill: tf-gray, "Step agota reintentos")
      ],
      block(fill: tf-warn.lighten(80%), inset: 8pt, radius: 4pt)[
        #text(size: 8.5pt, weight: "bold", fill: tf-warn, "RETRYING") \
        #text(size: 7.5pt, fill: tf-gray, "POST /retry → retoma desde step fallido")
      ],
      block(fill: tf-gray.lighten(50%), inset: 8pt, radius: 4pt)[
        #text(size: 8.5pt, weight: "bold", fill: tf-dark, "COMPENSATED") \
        #text(size: 7.5pt, fill: tf-gray, "Rollback exitoso")
      ],
    )
  ]
}
