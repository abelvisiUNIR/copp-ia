// =====================================================================
// TeleFlow Platform — tema y estilos compartidos
// =====================================================================

#let tf-blue    = rgb("#1a56db")
#let tf-dark    = rgb("#111928")
#let tf-gray    = rgb("#6b7280")
#let tf-light   = rgb("#f3f4f6")
#let tf-accent  = rgb("#0e9f6e")
#let tf-warn    = rgb("#d97706")
#let tf-danger  = rgb("#e02424")

// Paleta para tablas alternadas
#let row-even = rgb("#f9fafb")
#let row-odd  = white

// ------------------------------------------------------------------
// Caja de código inline
#let code(body) = box(
  fill: rgb("#f3f4f6"),
  inset: (x: 4pt, y: 2pt),
  radius: 3pt,
  text(font: "Courier New", size: 9pt, fill: rgb("#1f2937"), body)
)

// ------------------------------------------------------------------
// Bloque de código — body DEBE ser un string, no content.
// Uso:  #codeblock(lang: "bash", title: "Ejemplo", "code here")
// Para pasar strings multilínea usar la sintaxis de cadena Typst normal.
#let codeblock(lang: none, title: none, body) = {
  let header = if title != none {
    block(
      fill: tf-dark,
      inset: (x: 10pt, y: 6pt),
      radius: (top-left: 5pt, top-right: 5pt),
      width: 100%,
      text(fill: white, size: 8pt, weight: "bold", font: "Courier New",
        if lang != none { lang + "  ·  " } else { "" } + title
      )
    )
  } else { none }

  let radius-val = if title != none {
    (bottom-left: 5pt, bottom-right: 5pt, top-left: 0pt, top-right: 0pt)
  } else { 5pt }

  // body es un string; lo renderizamos como raw para evitar que Typst
  // interprete # _ $ como markup.
  let rendered = if type(body) == str {
    raw(body, lang: if lang != none { lang } else { "text" })
  } else {
    body
  }

  stack(
    spacing: 0pt,
    if header != none { header },
    block(
      fill: rgb("#1e293b"),
      inset: 10pt,
      width: 100%,
      radius: radius-val,
      clip: true,
      text(size: 8.5pt, fill: rgb("#e2e8f0"), rendered),
    )
  )
}

// ------------------------------------------------------------------
// Caja de nota / advertencia
#let callout(kind: "info", title: none, body) = {
  let (bg, border, icon) = if kind == "warning" {
    (rgb("#fffbeb"), tf-warn, "⚠")
  } else if kind == "danger" {
    (rgb("#fef2f2"), tf-danger, "✗")
  } else if kind == "success" {
    (rgb("#f0fdf4"), tf-accent, "✓")
  } else {
    (rgb("#eff6ff"), tf-blue, "ℹ")
  }

  block(
    fill: bg,
    stroke: (left: 3pt + border),
    inset: (x: 12pt, y: 10pt),
    radius: (right: 4pt),
    width: 100%,
  )[
    #if title != none {
      text(weight: "bold", fill: border, size: 9pt, icon + "  " + title)
      linebreak()
    }
    #text(size: 9pt, body)
  ]
}

// ------------------------------------------------------------------
// Tabla estilizada con cabecera de color
#let tftable(headers: (), rows: (), col-widths: none) = {
  let n = headers.len()
  let cols = if col-widths != none { col-widths } else { (1fr,) * n }

  table(
    columns: cols,
    fill: (col, row) => if row == 0 { tf-blue } else if calc.even(row) { row-even } else { row-odd },
    stroke: (col, row) => (
      bottom: if row == 0 { 0pt } else { 0.5pt + rgb("#e5e7eb") },
      rest: 0pt,
    ),
    inset: (x: 8pt, y: 6pt),
    ..headers.map(h => table.cell(
      text(fill: white, weight: "bold", size: 9pt, h)
    )),
    ..rows.flatten().map(cell => text(size: 9pt, cell))
  )
}

// ------------------------------------------------------------------
// Badge de estado
#let badge(label: "", color: tf-blue) = box(
  fill: color.lighten(80%),
  stroke: 0.5pt + color,
  inset: (x: 5pt, y: 2pt),
  radius: 10pt,
  text(size: 7.5pt, fill: color, weight: "bold", label)
)

// ------------------------------------------------------------------
// Cabecera de sección numerada con línea
#let section-header(num: "", title: "") = {
  v(16pt)
  block[
    #text(size: 22pt, weight: "bold", fill: tf-blue, num + "  ")
    #text(size: 22pt, weight: "bold", fill: tf-dark, title)
  ]
  line(length: 100%, stroke: 1pt + tf-blue.lighten(60%))
  v(8pt)
}

// ------------------------------------------------------------------
// Sub-sección
#let subsection(num: "", title: "") = {
  v(10pt)
  block[
    #text(size: 14pt, weight: "bold", fill: tf-dark, num + "  " + title)
  ]
  v(4pt)
}
