---
project: copp-ia
type: roadmap
provenance: copp-ia@devyos (código verificado en @13f2907)
created: 2026-07-10
updated: 2026-07-10
tags: [roadmap, plan, guia]
---

# Roadmap de desarrollo — copp-ia

> Documento **vivo**. Provenance de los hechos: código en `copp-ia@devyos` (mypy verificado
> en `@13f2907`). Cumple el pendiente "esbozar roadmap" de `onboarding-copp-ia`.
> Fuentes: [[teleflow-plataforma]], [[2026-07-09-validacion-doc-vs-codigo]], doc del arquitecto.

## Objetivo del owner (Yosdey)
Combinado y en este orden de madurez:
1. **Entender y aprender** la app.
2. **Endurecer la calidad** del código.
3. **Proponer mejoras/ideas** que la mejoren.
4. **Llevar a producción** cuando haya un producto estable y de calidad.

## Punto de partida (hechos comprobados)
- **No es desarrollo desde cero.** Fases 1-3 del arquitecto **implementadas y verificadas**:
  motor DAG async, durable sleep, entities/relations, rule engine, view360, capa IA
  (composer + review-ui), Helm, observabilidad. `pytest` **26/26**; deploy + execute
  demostrados en vivo (2026-07-09/10).
- **Fase 4 del arquitecto: en progreso** (Helm y CLI existen; plugin VS Code y runbooks/DR no).
- **mypy --strict: saneado a 0** (`saneamiento-mypy-strict`).

## Huecos reales detectados (no inventados) — insumo del roadmap
1. **Sin CI**: nada gatea `pytest`/`mypy`. La deuda de tipado se degradó por esto.
2. **Cobertura parcial**: los 26 tests cubren parser/validador/evaluador/DAG, **no el runtime
   con DB** (engine durable sleep, entities, rules, view360, adapters, gateway).
3. **DX/API**: el gateway no declara *security scheme* → Swagger no autentica; el CLI crashea
   en consola Windows cp1252 (falta forzar utf-8 en `cli.py`).
4. **Doc drift**: README/`.md` vs código (Grafana 3001, proveedor `stub`).
5. **Sin UI operativa** (solo review-ui de borradores) — decisión de alcance.

## Principios de trabajo (método)
- Chunks chicos y verificables; **un work-stream + una rama por chunk** (como en mypy).
- `pytest` + `mypy --strict` verdes tras cada cambio.
- **CI como red desde el día uno** (Fase B) antes de tocar features grandes.
- Ante conflicto doc↔código: **código > `.typ` > `.md`/README**.
- Flujo git: rama `devyos` (personal) → PR a `desarrollo` en puntos limpios.

---

## Fases

### Fase A — Entender la app (✅ CERRADA 2026-07-11)
- [x] Onboarding y asimilación de arquitectura → `onboarding-copp-ia`
- [x] Validación código vs doc → [[2026-07-09-validacion-doc-vs-codigo]]
- [x] Correr y documentar los 2 flujos de negocio end-to-end por API:
      event-driven Ceibal (entity→rule→process→360) y **durable sleep** (`venta_internet_hogar`,
      `human_task` + signal). → [[flujos-negocio]] (2026-07-11).
- [~] **Diferido (on-demand):** docs profundas por módulo (engine/rule engine/view360/adapters/DSL)
      en `Knowledge/projects/`. Decisión: los flujos e2e + [[teleflow-plataforma]] cubren el
      entendimiento operativo; cada módulo se documenta al tocarlo en Fase C.
- **Estado:** cerrada. Entendimiento suficiente para pasar a **Fase B (CI)**.

### Fase B — Red de seguridad: CI (🔶 casi cerrada — pendiente acción del owner en GitHub)
- [x] GitHub Actions (`.github/workflows/ci.yml`): `pytest` + `mypy --strict` + `docker build`.
      Validado localmente (mypy 0, pytest 26/26, build OK). Rama `chore/ci-pipeline`. → `fase-b-ci`
- [ ] (owner) push → confirmar verde en **Python 3.11 real** (la sesión usó 3.14).
- [ ] (owner) Gate: branch protection en `desarrollo` exigiendo el check `CI / quality`.
- **Criterio de salida:** ningún merge entra sin verde. **Falta solo lo del owner en GitHub.**

### Fase C — Endurecer calidad (✅ CERRADA 2026-07-12 → `fase-c-integracion`)
> Cubierto: runtime 0→39 tests (e2e de flujos + adapters con mocks), CI con job e2e.
> Diferido on-demand: tests con testcontainers (Chunk 2). DX (Swagger/CLI) → ver más abajo.
- [x] **Tests de integración del runtime**: executor contra
      Postgres/Redis/RabbitMQ (testcontainers o servicios en CI). Cubrir:
      ciclo `entity → rule → process`, `durable sleep + signal`, idempotencia `signal_key`,
      `on_timer` (rule_timer_log), y `view360`.
- [ ] Tests de adapters (rest/amqp/smtp) con mocks.
- [x] **DX (hecho 2026-07-12 → `dx-swagger-cli`):** *security scheme* `APIKeyHeader` en el gateway (Swagger autenticable) +
      fix utf-8 del CLI (`teleflow/cli.py`).
- [ ] Actualizar README/docs con las discrepancias (Grafana 3001, `stub`).
- **Criterio de salida:** runtime cubierto por tests, Swagger operable, CLI sin crash en Windows.

### Fase D — Mejoras / ideas (PROPUESTAS — evaluar antes de implementar)
> (propuesta, no del arquitecto) — cada idea pasa por un ADR o mini-work-stream antes de codear.
- [x] **Resiliencia (hecho 2026-07-14 → `resiliencia-executor`):** DLQ en RabbitMQ (los
  eventos fallidos ya no se descartan: dead-letter a `teleflow.rules.v1.dlq`) + backoff con
  clasificación transitorio/permanente y full jitter en los steps. **Circuit breaker en REST:
  pendiente**, deliberadamente fuera de scope hasta que haya un upstream que lo justifique.
- [x] **Seguridad (hecho 2026-07-14 → `seguridad-api-keys`):** API keys con scopes (10, por
  familia de acción), una key por integración (tabla `api_keys`, hasheadas SHA-256, con
  identidad para auditoría), y **revocación/rotación sin reiniciar el stack**. La key de env
  queda como bootstrap. **TLS interno: pendiente** (va con Fase E, hardening).
- [x] **Observabilidad de negocio (hecho 2026-07-24 → `observabilidad-negocio`):** gauges de
  estado actual publicados por un scanner del executor (`teleflow_instances_current`,
  `teleflow_human_task_backlog`, `teleflow_human_task_oldest_seconds`) y dashboard
  **TeleFlow · Negocio** provisionado. Antes solo había counters de eventos: ninguna métrica
  respondía "cuánto trabajo hay pendiente ahora". De paso se arregló que **ningún dashboard
  nuevo llegaba a una instalación existente** (el volumen `grafana-data` tapaba
  `/var/lib/grafana/dashboards` de la imagen).
- **DSL:** mejores mensajes de error del parser; validación semántica extra (refs a
  process/step inexistentes en `validator.py`).
- [x] **DX (hecho 2026-07-19 → `limpieza-dx-openapi`):** las 19 rutas del gateway declaran
  `operation_id` + `tags` (24 operaciones en 5 familias), y `tflow openapi` exporta el
  contrato a `docs/openapi.json` importando la app, sin stack levantado. README con la tabla
  de discrepancias doc-vs-código. **Colección `.http`: pendiente**, no se hizo.
- **UI operativa mínima (opcional):** panel de instancias/entities/360/signals (hoy solo API).
- [x] **Composer (hecho 2026-07-25 → `composer-llm-hardening`):** el ítem estaba mal descrito
  —los proveedores reales ya existían (`providers.py`), lo que faltaba era que el servicio no
  mintiera—. Sin credencial ya no cae al `stub` en silencio (el servicio no arranca); el
  borrador se valida contra el `parser-service` al componer y se guarda marcado (`validation`,
  alembic `0003`), y la `review-ui` lo muestra antes de aprobar; los errores del proveedor se
  clasifican en transitorio/permanente reusando `common/retry.py`. De 0 a 34 tests.
  **Pendiente:** hardening del prompt y templates TMForum.
- **Doc:** generación semi-automática desde código para frenar el drift.

### Fase E — Producción (cuando el producto esté estable y de calidad)
- [x] **Probar Helm charts en k8s local (hecho 2026-07-30 → [[fase-e-helm-kind]]):** el chart
  instala sin overrides y ejecuta procesos de negocio en Kubernetes (22 e2e contra el cluster).
  **No era un ítem de verificación, era uno de reparación:** el chart no se podía instalar
  —las imágenes de los subcharts de Bitnami fueron retiradas de Docker Hub— y aparecieron **15
  hallazgos**, tres de ellos bugs de producto y no del chart. Salieron 4 ADRs. `values` por
  entorno: existe `values-production.yaml`, que la doc usaba en su comando de deploy y **no
  existía**.
- [x] **Migraciones Alembic seguras dentro del pipeline de deploy** (mismo work-stream): dejaron
  de ser un hook de Helm —que se colgaba como `pre-install` y daba deadlock como `post-install`—
  y son un Job normal con initContainers que esperan a Postgres y al schema en `head`. Efecto
  bueno: en un upgrade los pods nuevos no arrancan hasta que el schema está migrado, así que el
  orden "schema primero, código después" lo garantiza el pod y no la ceremonia del deploy.
- [ ] Secrets fuera de `.env` (k8s Secrets / Vault); rotación de `TELEFLOW_API_KEY`.
  **Medio hecho:** el chart crea el Secret o consume uno del organismo (`existingSecret`), y sin
  ninguno de los dos el install **falla diciendo cuál falta**. Sigue pendiente que los passwords
  de Postgres y RabbitMQ salgan de `values` en texto plano.
- [ ] Readiness/liveness afinados; HPA del executor; StatefulSets Postgres/Redis/RabbitMQ en HA.
  **Los StatefulSets ya son propios** (con las imágenes oficiales que usa el compose, así que dev
  y producción comparten capa de datos). Falta el **HA** que recomienda §10.2: patroni, Sentinel y
  quorum queues. Los probes existen en todos los servicios.
- [ ] Runbooks, backup/restore Postgres, disaster recovery, alertas Prometheus.
  Backup/restore ya está ([[estado-durable]]). **Observabilidad: el chart trae los puntos de
  integración** (anotaciones de scrape, `ServiceMonitor` y ConfigMap de dashboards, opt-in) y se
  verificó con un Prometheus real descubriendo los 11 pods. Falta escribir las **reglas de
  alerta** — la primera y más urgente, el `up` de `metrics-service`, que quedó como punto único
  de fallo de las métricas de negocio.
- [ ] Hardening: TLS, no exponer servicios internos, revisión de superficie de ataque.
  El gateway dejó de ser `LoadBalancer` fijo (Service configurable + Ingress opt-in) y la
  `review-ui` **dejó de publicarse**: era la UI desde la que se aprueba y despliega código, y
  estaba potencialmente expuesta sin que nadie lo hubiera decidido. TLS sigue pendiente.
- [ ] **Nuevo, sale del work-stream:** que el pipeline verifique que las imágenes referenciadas
  **existen**. Una dependencia externa rompió un artefacto que nadie tocó y ni los tests ni el
  lint lo vieron, porque el fallo ocurre al desplegar.
- **Criterio de salida:** deploy reproducible por organismo (ADR-005) con checklist verde.

### Fase F — Futuro / opcional (Fase 4 del arquitecto)
- Plugin VS Code (Tree-sitter + syntax highlighting).
- 6 templates TMForum.
- Múltiples instancias por línea de negocio.

---

## Orden recomendado y dependencias
`A (transversal)` → **`B` (CI primero)** → `C` (calidad) → `D` (mejoras selectivas) → `E` (producción).
**Regla:** no pasar a Producción (E) sin C + D estables. D siempre después de tener CI (B).

## Backlog transversal
Los huecos que no caen limpio en una fase (auditoría persistida, `registry-service` sin tests,
rate limit por proceso, `/execute` sin idempotencia, `review-ui` sin red de seguridad,
backup/restore) están en [[backlog-hardening]], con evidencia y prioridad. Esa página se
mantiene aparte para no distorsionar la estructura de fases del arquitecto.

## Cómo lo trackeamos
- Cada Fase = uno o más **work-streams**, cada uno con su rama.
- ADRs para decisiones de mejora (Fase D) en `Knowledge/decisions/`.
- Este archivo se actualiza marcando `[x]` a medida que se cierran ítems.

## Próximo paso sugerido
Arrancar **Fase B (CI)**: es barata, alta protección, y habilita todo lo demás. Después,
el primer chunk de **Fase C** (un test de integración del ciclo `entity → rule → process`).
