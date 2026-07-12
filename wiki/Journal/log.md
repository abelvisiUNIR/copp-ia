# Journal log — copp-ia

Entradas breves con timestamp, agregadas por `/checkpoint`. Más reciente arriba.

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
