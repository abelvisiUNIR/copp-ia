---
project: copp-ia
type: roadmap
provenance: copp-ia@devyos (código verificado en @13f2907)
created: 2026-07-10
updated: 2026-08-08
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
- [x] Secrets fuera de `.env` (k8s Secrets / Vault); rotación de `TELEFLOW_API_KEY`.
  El chart crea el Secret o consume uno del organismo (`existingSecret`), y sin ninguno de los
  dos el install **falla diciendo cuál falta**. Desde 2026-08-18 también corta cuando el
  `existingSecret` **se declara y no existe** — antes ese caso decía `Install complete` y dejaba
  los 18 pods en `CreateContainerConfigError` con el motivo enterrado en sus eventos (lo
  encontró el checklist de salida, instalando). La rotación se administra por API con scope
  `keys:admin`; la key del Secret es el bootstrap.
  **Límite consciente que queda:** los passwords de la capa de datos **propia** salen de `values`
  en texto plano — ya no llegan al spec de los pods, pero el valor inicial está ahí. La salida es
  la capa de datos del organismo con `external<Comp>.existingSecret`, que es el camino
  recomendado en producción.
- [x] **HA de la capa de datos (hecho 2026-08-08 → `ha-capa-de-datos`)**, con alcance
  deliberadamente menor que la lectura literal de §10.2 y decidido en
  [[2026-08-08-alcance-del-ha-de-la-capa-de-datos]]: la plataforma entrega HA **donde solo ella
  puede hacerlo**. **RabbitMQ: cluster de 3 con quorum queues** (peer discovery de k8s, cookie
  que sobrevive a los upgrades, RBAC de endpoints, anti-afinidad), y del lado del código la cola
  y la DLQ declaradas `quorum` —el tipo lo fija quien declara, así que esto **no** se puede
  resolver desde afuera— con migración `teleflow.rules.v1` → `v2`. **Probado en kind con
  control:** matando el nodo que aloja la cola, la clásica pierde el mensaje (1→0) y la quorum lo
  conserva (2→2). **Postgres y Redis: una réplica, escrito como decisión** — no se escribe un
  patroni casero porque no se puede demostrar que funcione, y un organismo con base administrada
  ya tiene mejor HA; para eso el **camino externo pasó a ser de primera clase** (puerto,
  credenciales propias, TLS, `existingSecret` que saca la contraseña del spec del pod, y un
  install que corta nombrando lo que falta). Los probes ya existían.
- [x] **Autoescalado del executor (hecho 2026-08-18 → `hpa-executor`)**, decidido con medición y
  no con la señal obvia: ver [[2026-08-18-senal-de-escalado-del-executor]]. **La CPU quedó
  descartada** — el techo del executor es `WORKER_CONCURRENCY` (un semáforo por réplica) y el
  servicio es I/O-bound, así que con el mismo throughput saturado cuadruplicar la cola movió la
  CPU un **19 %** (296 m → 351 m), mientras que a media capacidad y sin nadie esperando ya
  tocaba el **94 % del request de 100 m**: sensible donde no importa, sorda donde importa. La
  señal es el backlog que compite por un worker (`teleflow_executor_backlog`, gauge nuevo que
  **excluye durable sleep**: con 225 instancias dormidas y el executor ocioso marca 0, verificado
  en vivo). **El HPA entra al chart apagado** (`autoscaling.enabled: false`) porque se puede
  demostrar que la cola crece pero **no** que sumar réplicas la drene — la instancia la ejecuta
  la réplica que recibió el `POST /execute`. Con el HPA prendido el Deployment deja de declarar
  `replicas` (si no, cada `upgrade` se lo pisa en silencio) y el install corta ante cuatro
  configuraciones que no podrían escalar. **Límite escrito:** el gauge se refresca cada 30 s, así
  que las ventanas de estabilización no pueden bajar de ahí.
- [x] Runbooks, backup/restore Postgres, disaster recovery, alertas Prometheus.
  Backup/restore ya está ([[estado-durable]]). **Observabilidad: el chart trae los puntos de
  integración** (anotaciones de scrape, `ServiceMonitor` y ConfigMap de dashboards, opt-in) y se
  verificó con un Prometheus real descubriendo los 11 pods. **Alertas: hechas** (2026-07-31 →
  work-stream `alerta-up-metrics-service`), y con más alcance del que decía este ítem: `up == 0`
  cubría el pod caído, pero no el caso peor —el pod **vivo** que no puede leer la base, donde el
  `except` del colector mantiene el servicio arriba y los gauges conservan el último valor bueno
  con `up` en 1—. Hizo falta emitir la señal primero
  (`teleflow_business_metrics_last_success_timestamp_seconds`, más un contador de fallos):
  ninguna de las 16 métricas del repo era un timestamp de último éxito. Tres reglas en
  `helm/teleflow/alerts/alerts.yml`, **una sola fuente** que consumen la imagen de Prometheus del
  compose y un `PrometheusRule` opt-in del chart, igual que los dashboards y por el mismo motivo.
  Ver [[fallas-silenciosas]] #14. **Runbooks y DR: hechos** el 2026-08-08 → [[runbooks-y-dr]],
  `docs/runbooks.md`, con cada comando ejecutado contra el stack real — y escribirlos funcionó
  como test de la documentación: encontró una tabla que no existe (`flow_versions`, es
  `flow_definitions`) que habría fallado justo después de un desastre.
- [x] Hardening: TLS, no exponer servicios internos, revisión de superficie de ataque.
  El gateway dejó de ser `LoadBalancer` fijo (Service configurable + Ingress opt-in) y la
  `review-ui` **dejó de publicarse**: era la UI desde la que se aprueba y despliega código, y
  estaba potencialmente expuesta sin que nadie lo hubiera decidido. **TLS del borde: hecho** el
  2026-08-08 — con el Ingress prendido el TLS es **obligatorio** y el install corta si falta,
  salvo que el organismo declare que lo termina más arriba (`allowInsecure: true`). Publicar el
  gateway en claro manda la API key en un header.
  **Límite consciente:** el TLS **interno** entre servicios no se hace y está escrito como
  decisión, no omitido.
- [x] **Que el pipeline verifique que las imágenes referenciadas existen** (hecho 2026-08-08 →
  `verificacion-imagenes-pipeline`). Salió partido en dos, y esa fue la decisión del work-stream:
  lo **determinista gatea los merges** (`tests/test_imagenes_contract.py`, sin red: que la capa
  de datos use la misma imagen en el compose y en el chart —estaba declarada dos veces y nada
  las ataba—, que el StatefulSet la tome de `values.yaml`, que ningún tag sea mutable) y lo que
  **depende del registry corre programado** (`scripts/verificar_imagenes.py` +
  `.github/workflows/imagenes.yml`, semanal, fuera de `ci.yml`). El trigger no se eligió por
  costo sino por el modo de falla: el artefacto no cambia y la dependencia se rompe sola, así
  que un job por `push` sería ciego por construcción — no hay push. El script distingue "no
  existe" (exit 1) de "no pude consultar" (exit 2), porque un detector también puede fallar
  **por ruidoso**: ver [[fallas-silenciosas]], modo gemelo del caso #14. **Límite consciente:**
  las imágenes que publica cada organismo no se verifican (son de su registry, no del repo).
- [x] **Criterio de salida: deploy reproducible por organismo (ADR-005) con checklist verde**
  (hecho 2026-08-18 → `criterio-salida-fase-e`). `docs/checklist-instalacion.md`, **ejecutado de
  punta a punta antes de escribirse** contra un kind limpio: 18 pods arriba, migración aplicada,
  **24 e2e verdes contra el cluster** y `helm upgrade` idempotente que los deja verdes de nuevo.
  Escribirlo ejecutando encontró cuatro cosas que leyendo no se veían — la peor: declarar
  `existingSecret` sin crearlo daba `Install complete` con **todos** los pods en
  `CreateContainerConfigError`, que es justo el modo de falla que el README declaraba evitado
  (ahora el install corta nombrando el Secret y el comando para crearlo).
  **Lo que el checklist NO declara verde, por escrito:** registry privado, base administrada
  real, Ingress con TLS real, Prometheus del organismo y RKE2 — todo depende de infraestructura
  del organismo y se cierra en la primera instalación real.
- **Estado de la fase: CERRADA** (2026-08-18), con sus límites conscientes escritos en cada ítem.

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
