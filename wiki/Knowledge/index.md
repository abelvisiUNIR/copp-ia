# Knowledge — copp-ia

Índice de conocimiento durable del proyecto. Solo lo que vale la pena recordar a largo
plazo llega aquí (modelo de dos capas: `Journal\` es transitorio, `Knowledge\` es durable;
la promoción de uno a otro es deliberada, nunca automática).

- `projects/` — visión de los componentes/módulos del sistema.
- `decisions/` — ADRs (`YYYY-MM-DD-titulo.md`).
- `concepts/` — conceptos de dominio, glosario.
- `people/` — stakeholders relevantes.
- `investigations/` — investigaciones cerradas con hallazgos.

## Páginas

- [[roadmap]] — **guía de desarrollo** por fases (aprender → CI → calidad → mejoras → producción).
- [[2026-07-25-notas-de-actualizacion]] — **para el equipo antes de pullear** lo del 25/7:
  tres migraciones, el `.env` que puede impedir arrancar el composer, y `up --build` por el
  volumen de RabbitMQ.
- [[backlog-hardening]] — huecos concretos con evidencia (auditoría, registry sin tests, rate
  limit por proceso, `/execute` sin idempotencia, `review-ui`, backup/restore).

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
- [[2026-07-14-clasificacion-errores-integracion]] — (wiki/executor) el adapter clasifica
  transitorio vs permanente; el engine solo reintenta lo transitorio, con full jitter.
- [[2026-07-24-alcance-mypy]] — (wiki/tooling) `mypy .` cubre el repo entero y es el mismo
  comando en CI y en la doc; los tests se chequean sin exigirles anotaciones de firma.
- [[2026-07-24-metricas-de-negocio-gauges]] — (wiki/observabilidad) el estado actual
  (backlog de human_tasks, procesos vivos) va en gauges agregados por SQL desde
  `process_instances`; los counters miden eventos y no responden sobre el presente.
- [[2026-07-25-estado-compartido-gateway]] — (wiki/gateway, **proposed**) el rate limit y el
  cache de keys pasan a Redis: el chart ya declara `replicas: 2` y el código asume un solo
  proceso.
- [[2026-07-25-auditoria-persistida]] — (wiki/gateway, **proposed**) se audita toda escritura
  y todo intento denegado, sin guardar el cuerpo; el registro se engancha en `auth.require`
  para que ninguna ruta nueva quede afuera.
- [[2026-07-25-composer-llm-fallos-explicitos]] — (wiki/composer) sin proveedor real
  configurado el servicio no arranca (nunca cae al `stub` en silencio); el borrador se valida
  contra el parser al componer y se guarda marcado; los errores del LLM se clasifican.
- [[2026-07-30-capa-de-datos-del-chart]] — (wiki/despliegue) el chart deja los
  subcharts de Bitnami —cuyas imágenes ya no existen en Docker Hub— y se alinea con las
  imágenes oficiales que usa el compose, escribiendo los tres StatefulSets.
- [[2026-07-30-scanner-de-negocio-multi-replica]] — (wiki/observabilidad) enmienda
  a [[2026-07-24-metricas-de-negocio-gauges]]: con 3 réplicas del executor los gauges se leían
  3×; el colector se muda a `metrics-service`, de **una sola réplica**. Incluye el error de
  diseño del primer intento (advisory lock por ciclo) y por qué su test no lo detectaba.

### concepts
- [[fallas-silenciosas]] — el patrón que más veces apareció: mecanismos que parecen proteger
  y avisan sin cortar. Tres casos verificados y las preguntas para detectar el próximo.

### investigations
- [[2026-07-09-validacion-doc-vs-codigo]] — doc vs código: 26/26 tests ✅, mypy strict ❌,
  4 discrepancias doc↔código. Regla: **código > `.typ` > `.md`/README**.
