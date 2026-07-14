# Journal log — copp-ia

Entradas breves con timestamp, agregadas por `/checkpoint`. Más reciente arriba.

- 2026-07-14: **cierre de sesión.** Fase D: primer ítem [[dsl-error-reporting]] ✅ cerrado y mergeado a `devyos` (`c38c9c3`, mypy 0, suite 50/50). Historia de la sesión reescrita sin trailer de IA (preferencia del owner). **Retomar:** elegir siguiente ítem de Fase D — resiliencia executor (`/retry` + DLQ/backoff), seguridad (API keys con scopes/roles), o limpieza DX (operation_id + export OpenAPI). Pendiente del owner: push + branch protection (Fase B). Ver [[roadmap]].

- 2026-07-13: **CERRADO** work-stream [[dsl-error-reporting]] (`status: completed`). Primer ítem de **Fase D** hecho: mensajes del parser (3 tipos de error + terminales esperados + `parse_expr` con contexto) y validación semántica extra (duplicados → error; refs de triggers de rule → warning). +11 tests, mypy 0, suite 39→50. Mergeado a `devyos` con `--no-ff` (`03ff11a`), sin push. Próximo: elegir siguiente ítem de Fase D (resiliencia executor / seguridad API keys / limpieza DX).

- 2026-07-13: **abierto** work-stream [[dsl-error-reporting]] — arranca **Fase D** por el DSL error reporting. Scope: mensajes del parser (gap real; `parser.py`) + 2 gaps semánticos a confirmar (triggers de rule con refs inexistentes, nombres duplicados). Hallazgo: `validator.py` ya es robusto (refs process/step ya validadas), así que el foco pivota al parser. Fase B sigue pendiente del owner (push).

- 2026-07-12: **cierre de sesión.** Fase C ✅ cerrada ([[fase-c-integracion]], runtime 0→39 tests: e2e + adapters + job CI e2e) y quick win DX ✅ ([[dx-swagger-cli]]: security scheme en gateway para Swagger Authorize + CLI utf-8). Todo mergeado a `devyos` (mypy 0, e2e 3/3). **Retomar:** Fase D (endurecer errores del executor `/retry`, o DSL error reporting). Pendiente del owner: push + branch protection (Fase B). Ver [[roadmap]].

- 2026-07-11: Fase B (CI) hecha del lado del código — `.github/workflows/ci.yml` en `chore/ci-pipeline` ([[fase-b-ci]]), validada local (mypy 0, pytest 26/26, build OK). Pendiente del owner: push + branch protection. Próximo: Fase C (tests de integración). Rama actual: `chore/ci-pipeline`.

- 2026-07-11: **Fase A CERRADA** — flujos e2e documentados ([[flujos-negocio]]); work-stream [[fase-a-flujos-e2e]] completado. Docs por módulo diferidas on-demand a Fase C. Próximo: Fase B (CI).
- 2026-07-11: Fase A — corridos los 2 flujos e2e en vivo (durable sleep + event-driven Ceibal/360); guía [[flujos-negocio]]. Work-stream [[fase-a-flujos-e2e]].

- 2026-07-10: creado [[roadmap]] — guía de desarrollo por fases (A entender · B CI · C calidad · D mejoras · E producción). Objetivo del owner: aprender + endurecer + proponer mejoras + luego producción.

- 2026-07-09: creada rama personal `devyos` desde `desarrollo`; merge `--no-ff` de `chore/mypy-strict-clean` (`eaef97d`), `.claude/` agregado a `.gitignore` (`f64ed98`), y wiki commiteada (`9945ae1`). Local, sin push.

- 2026-07-09: **cerrado** work-stream [[saneamiento-mypy-strict]] (`status: completed`) — objetivo cumplido, commit local `13f2907`.
- 2026-07-09: [[saneamiento-mypy-strict]] — `mypy --strict` **236 → 0** (16 archivos + override networkx en pyproject); pytest 26/26. Pendiente de commit.
- 2026-07-09: abierto work-stream [[saneamiento-mypy-strict]] — llevar `mypy --strict` a 0 (hoy 236 errores). Derivado del onboarding.
- 2026-07-09: **cerrado** work-stream [[onboarding-copp-ia]] (`status: completed`) — objetivo cumplido; lead de `rules.py` descartado como falso positivo.
- 2026-07-09: onboarding — validado código vs doc y poblado Knowledge ([[teleflow-plataforma]], 5 ADRs, [[2026-07-09-validacion-doc-vs-codigo]]). Tests 26/26 ✅, mypy --strict falla (236) ❌. Regla: código > `.typ` > `.md`/README.
- 2026-06-30: abierto work-stream [[onboarding-copp-ia]] — asimilar visión/arquitectura del arquitecto, fijar contexto base y planificar roadmap.
