// =====================================================================
// TeleFlow Platform — Sección 1: Visión y propuesta de valor
// =====================================================================
#import "lib/theme.typ": *

#let vision() = {

  section-header(num: "1", title: "Visión y propuesta de valor")

  text(size: 10pt)[
    TeleFlow es una plataforma de orquestación empresarial basada en el principio
    #text(weight: "bold", "Business & Software as Code"). Permite a organismos públicos
    y privados modelar, desplegar y ejecutar sus procesos de venta y post-venta como
    código declarativo, con el mismo rigor con que Terraform gestiona infraestructura.
  ]

  v(16pt)

  // Propuesta de valor — flujo de pasos
  subsection(num: "1.1", title: "El ciclo de vida de un proceso")

  grid(
    columns: (1fr,) * 5,
    gutter: 0pt,
    ..range(5).map(i => {
      let (num, title, desc, color) = (
        ("01", "Análisis",     "Analista describe en\nlenguaje natural",     tf-blue),
        ("02", "Generación",   "LLM configurable\ngenera el .tflow",         tf-accent),
        ("03", "Revisión",     "Dev revisa diff\ntipo pull-request",         tf-warn),
        ("04", "Deploy",       "Motor registra\ny valida la versión",        tf-blue.darken(20%)),
        ("05", "Ejecución",    "Executor corre el DAG\ndurable + observable", tf-dark),
      ).at(i)

      block(
        fill: color,
        inset: 12pt,
        width: 100%,
      )[
        #text(size: 20pt, weight: "black", fill: white.transparentize(50%), num)
        #linebreak()
        #text(size: 10pt, weight: "bold", fill: white, title)
        #linebreak()
        #v(4pt)
        #text(size: 8pt, fill: white.transparentize(30%), desc)
      ]
    })
  )

  v(20pt)

  // Modelo de despliegue por organismo
  subsection(num: "1.2", title: "Un producto, muchos organismos")

  grid(
    columns: (1fr, 1fr),
    gutter: 16pt,

    // Izquierda: descripción
    block[
      #text(size: 10pt)[
        TeleFlow *no es SaaS*. Es un producto que se instancia por organismo, como
        GitLab self-hosted. Cada organismo posee y opera su propia instancia con
        datos completamente aislados.
      ]
      #v(10pt)
      #text(size: 10pt)[
        El mismo #code("docker-compose.yml") y los mismos Helm charts sirven a todos.
        Los templates de proceso (TMForum, ITSM, etc.) se comparten como repositorios Git.
      ]
      #v(16pt)
      #callout(kind: "info", title: "Analogía")[
        TeleFlow es a los procesos de negocio lo que #text(weight: "bold", "Terraform")
        es a la infraestructura: código versionado, revisable y reproducible.
      ]
    ],

    // Derecha: lista de organismos
    block(
      fill: tf-light,
      inset: 16pt,
      radius: 6pt,
    )[
      #text(size: 10pt, weight: "bold", fill: tf-dark, "Organismos cliente (ejemplos)")
      #v(10pt)
      #for (org, desc) in (
        ("OSE",              "Empresa pública de agua y saneamiento"),
        ("Antel",            "Operador nacional de telecomunicaciones"),
        ("Ceibal",           "Plan educativo 1:1 de Uruguay"),
        ("Min. Economía",    "Gestión de subsidios y transferencias"),
      ) [
        #grid(
          columns: (60pt, 1fr),
          gutter: 6pt,
          text(size: 9pt, weight: "bold", fill: tf-blue, org),
          text(size: 9pt, fill: tf-gray, desc),
        )
        #v(4pt)
      ]
    ],
  )

  v(20pt)

  // Tabla de analogías
  subsection(num: "1.3", title: "Analogías de diseño")

  tftable(
    headers: ("Concepto TeleFlow", "Analogía técnica", "Analogía de negocio"),
    col-widths: (1.2fr, 1.2fr, 1fr),
    rows: (
      ("Archivo `.tflow`",    "Helm chart / K8s manifest",    "Especificación del proceso"),
      ("`entity`",            "Aggregate (DDD)",              "Niño, cliente, contrato"),
      ("`process`",           "Kubernetes Deployment",        "Proceso de venta, soporte"),
      ("`relation`",          "Join con estado propio",       "Inscripción, contrato activo"),
      ("Registry Service",    "OCI Registry / Helm repo",     "Repositorio de procesos"),
      ("Executor Service",    "Kubernetes controller loop",   "Motor de ejecución"),
      ("Instance",            "Pod en ejecución",             "Venta en curso"),
      ("State Store",         "etcd del cluster",             "Estado durable del negocio"),
    ),
  )
}
