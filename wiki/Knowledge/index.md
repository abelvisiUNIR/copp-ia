# Knowledge — copp-ia

Índice de conocimiento durable del proyecto. Solo lo que vale la pena recordar a largo
plazo llega aquí (ver modelo de dos capas en `~/.claude/CLAUDE.md`).

- `projects/` — visión de los componentes/módulos del sistema.
- `decisions/` — ADRs (`YYYY-MM-DD-titulo.md`).
- `concepts/` — conceptos de dominio, glosario.
- `people/` — stakeholders relevantes.
- `investigations/` — investigaciones cerradas con hallazgos.

## Páginas

- [[roadmap]] — **guía de desarrollo** por fases (aprender → CI → calidad → mejoras → producción).

### guides
- [[flujos-negocio]] — recorridos end-to-end por API: durable sleep + event-driven Ceibal + 360.

### projects
- [[teleflow-plataforma]] — visión, servicios, DSL v2, durable sleep, estado de implementación.

### decisions
- [[2026-06-30-adr-001-lark-lalr]] — Lark + LALR; gramática = fuente de verdad del DSL.
- [[2026-06-30-adr-002-durable-sleep]] — Postgres + Redis pub/sub; señales idempotentes.
- [[2026-06-30-adr-003-llm-configurable]] — proveedor LLM por env (anthropic/openai/ollama/stub).
- [[2026-06-30-adr-004-rabbitmq-en-stack]] — broker propio; migración a externo = config.
- [[2026-06-30-adr-005-aislamiento-instancia]] — una DB por organismo; no multi-tenant.
- [[2026-07-09-mypy-networkx-override]] — (wiki/tooling) networkx `ignore_missing_imports`;
  no instalar `types-networkx` (rompe por numpy 3.12 vs target 3.11).

### investigations
- [[2026-07-09-validacion-doc-vs-codigo]] — doc vs código: 26/26 tests ✅, mypy strict ❌,
  4 discrepancias doc↔código. Regla: **código > `.typ` > `.md`/README**.
