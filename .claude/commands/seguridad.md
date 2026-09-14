---
description: Transversal — el subagente seguridad-infra analiza una feature o modulo y escribe seguridad.md
argument-hint: <carpeta-feature> [etapa: especificar|disenar|pre-pr|as-built]
allowed-tools: Bash(git rev-parse:*)
---

Provenance actual: copp-ia@!`git rev-parse --abbrev-ref HEAD`@!`git rev-parse --short HEAD`

Usa el subagente `seguridad-infra` para: $ARGUMENTS

Pasale la provenance de arriba. Mostra los huecos por severidad, completos los de severidad alta,
y lo que propone sumar a `wiki/Knowledge/backlog-hardening.md` (sumarlo lo decide una persona).
