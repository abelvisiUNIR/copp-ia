// =====================================================================
// TeleFlow Platform — Portada
// =====================================================================
#import "lib/theme.typ": *

#let portada() = {
  set page(margin: 0pt)

  // Fondo degradado simulado con rectángulos
  place(top + left,
    rect(width: 100%, height: 100%, fill: tf-dark)
  )
  place(top + right,
    rect(width: 60%, height: 100%, fill: gradient.linear(
      tf-blue.darken(30%), tf-dark,
      angle: 135deg
    ))
  )

  // Franja decorativa
  place(bottom + left,
    rect(width: 100%, height: 6pt, fill: tf-blue)
  )

  // Contenido centrado
  align(center + horizon)[
    #v(80pt)

    // Logo / wordmark
    #block(
      fill: white.transparentize(90%),
      inset: (x: 30pt, y: 20pt),
      radius: 8pt,
    )[
      #text(size: 52pt, weight: "black", fill: white, tracking: -2pt, "TeleFlow")
      #linebreak()
      #text(size: 14pt, fill: tf-blue.lighten(60%), weight: "light",
        tracking: 8pt, "PLATFORM")
    ]

    #v(24pt)

    #text(size: 20pt, fill: white.transparentize(20%), weight: "medium",
      "Business & Software as Code")

    #v(48pt)
    #line(length: 200pt, stroke: 1.5pt + tf-blue.lighten(40%))
    #v(24pt)

    #text(size: 13pt, fill: tf-gray.lighten(40%),
      "Documentación Técnica Completa")
    #v(8pt)
    #text(size: 11pt, fill: tf-gray.lighten(20%), "v1.0.0  ·  Junio 2026  ·  Confidencial")

    #v(60pt)

    // Badges de tecnología
    #grid(
      columns: (auto,) * 5,
      gutter: 8pt,
      ..("FastAPI", "Lark LALR", "PostgreSQL", "Redis", "RabbitMQ").map(t =>
        box(
          fill: white.transparentize(85%),
          stroke: 0.5pt + white.transparentize(60%),
          inset: (x: 10pt, y: 5pt),
          radius: 4pt,
          text(size: 8pt, fill: white.transparentize(20%), t)
        )
      )
    )
  ]

  pagebreak()
}
