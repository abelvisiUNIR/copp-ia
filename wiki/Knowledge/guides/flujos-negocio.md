---
project: copp-ia
type: guide
provenance: copp-ia@devyos (ejecutado en vivo 2026-07-11, stack docker)
created: 2026-07-11
updated: 2026-07-11
tags: [guia, flujos, durable-sleep, event-driven, view360, demo]
---

# Guía: flujos de negocio end-to-end por API

> Recorridos **ejecutados en vivo** (2026-07-11) contra el stack Docker. Cierra el ítem de
> flujos de Fase A del [[roadmap]]. Ver arquitectura en [[teleflow-plataforma]].

## Prerrequisitos
- Stack arriba (`docker compose up --build -d`).
- Header en toda llamada: `X-TeleFlow-API-Key: dev-key-change-me`.
- CLI: exportar `PYTHONIOENCODING=utf-8` (si no, el CLI crashea al imprimir ✓ en consola Windows cp1252).
- **Cache de dominio 30 s**: tras un `deploy`, esperar ~30 s antes del primer `execute`/regla nueva
  (`domain_cache_ttl`, `config.py:36`).

---

## Flujo 1 — Durable sleep + human_task (`venta_internet_hogar`)

Demuestra ADR-002: una instancia que **duerme en `WAITING_SIGNAL`** en un paso de aprobación
humana y se **reactiva por señal** (Redis pub/sub), sin polling ni bloquear worker.

### Pasos
```bash
export TELEFLOW_API_KEY=dev-key-change-me PYTHONIOENCODING=utf-8
TF=./.venv/Scripts/tflow.exe

# 1. Deploy y (esperar 30s por el cache) ejecutar
$TF deploy examples/venta_internet_hogar.tflow --name venta_internet_hogar --version 1.0.0
$TF execute venta_internet_hogar --payload '{"cliente_id":"cli-001","producto":"fibra-300","direccion":"18 de Julio 1234"}'
# -> { instance_id, status: "TRIGGERED" }

# 2. Estado: corre validacion (2 steps noop) y DUERME en aprobacion_gerencia
$TF status <instance_id>
# -> status: WAITING_SIGNAL, current_step: aprobacion_gerencia

# 3. El gerente aprueba -> despierta y completa
curl.exe -s -X POST http://localhost:8000/instances/<id>/signal \
  -H "X-TeleFlow-API-Key: dev-key-change-me" -H "Content-Type: application/json" \
  -d '{"step_name":"aprobacion_gerencia","signal":"approve","actor_id":"gerente.perez","signal_id":"sig-abc-001"}'
# -> { status: "SIGNALED", duplicate: false }
$TF status <instance_id>   # -> COMPLETED
```

### Qué se observó (lifecycle real)
```
TRIGGERED → IN_PROGRESS → (validar_identidad noop) → (verificar_cobertura noop)
→ WAITING_SIGNAL(aprobacion_gerencia)          ← duerme; contexto persistido en Postgres
→ IN_PROGRESS(aprobacion_gerencia)             ← señal approve la despierta (Redis)
→ (decidir: signal==approve → activacion) → (activar_servicio noop) → (notificar_alta logged)
→ COMPLETED
```

### Idempotencia
- La respuesta de la señal trae `"duplicate": false`: el mecanismo es `signal_key` UNIQUE
  (ADR-002). Reenviar el **mismo `signal_id` mientras espera** devolvería `duplicate: true`
  sin re-procesar.
- En esta corrida el reenvío fue **después** de completar → respondió
  `"la instancia está en COMPLETED, no espera señal"` (protección por estado, complementaria).

---

## Flujo 2 — Event-driven Ceibal (entity → rule → process → 360)

Demuestra el modelo de dominio: transiciones de entities/relations **emiten eventos** →
el **rule engine** (consumidor RabbitMQ, async) evalúa y **dispara procesos**.

### Pasos
```bash
H='-H "X-TeleFlow-API-Key: dev-key-change-me" -H "Content-Type: application/json"'
# (deploy previo: tflow deploy examples/ceibal.tflow --name ceibal --version 1.0.0)

# 1-2. Crear entidades
curl.exe -s -X POST http://localhost:8000/entities/nino ... \
  -d '{"entity_id":"nino-juan","fields":{"ci":"1.234.567-8","nombre":"Juan Perez","fecha_nac":"2014-03-01","departamento":"Montevideo","nivel":"primaria"}}'
curl.exe -s -X POST http://localhost:8000/entities/curso ... \
  -d '{"entity_id":"curso-robotica","fields":{"nombre":"Robotica Basica","area":"robotica"}}'

# 3. Activar nino: emite nino.activado -> regla prioridad_dispositivo (dispositivo==null)
curl.exe -s -X POST http://localhost:8000/entities/nino/nino-juan/transition ... -d '{"via":"activar"}'

# 4-5. Crear inscripcion y activarla: emite inscripcion.activada -> regla activar_acceso
curl.exe -s -X POST http://localhost:8000/relations/inscripcion ... \
  -d '{"from_id":"nino-juan","to_id":"curso-robotica","fields":{"fecha_inscripcion":"2026-06-10","modalidad":"virtual"}}'
curl.exe -s -X POST http://localhost:8000/relations/inscripcion/<rid>/transition ... -d '{"via":"activar"}'

# 6-7. (esperar ~5s: reglas async) Vista 360 + instancias
curl.exe -s http://localhost:8000/entities/nino/nino-juan/360 ...
curl.exe -s http://localhost:8000/instances ...
```

### Qué se observó
- **Vista 360** agrega: estado (`ACTIVO`), `relaciones_activas` (la inscripción con datos del
  curso embebidos), `timeline` de eventos (`nino.registrado → nino.activado →
  inscripcion.pendiente → inscripcion.activada`) y `alertas` (reglas activas).
- **Reglas disparadas** (async, vía RabbitMQ):
  - `prioridad_dispositivo` (on `nino.activado`, condición `dispositivo==null`) →
    proceso `asignacion_dispositivo` → **COMPLETED** (steps noop).
  - `activar_acceso_al_inscribirse` (on `inscripcion.activada`) →
    proceso `activacion_acceso_plataforma` → **FAILED**: su step `crear_credenciales_lms`
    llama a `integration.lms` (REST) con `base_url=${env.LMS_URL}` **sin configurar** → falla.
    Comportamiento correcto y realista (integración externa no provista).
- `procesos_activos` en el 360 salió **vacío**: solo lista instancias **no terminales**; las
  dos ya habían terminado (una COMPLETED, otra FAILED) al momento de consultar.

---

## Aprendizajes / gotchas (hechos)
- **Adapters sin integración** (`adapters.py`): step `automated` sin integration → **noop**
  (eco); `notification` sin integration → **logged**. Por eso los procesos "de demo" completan
  sin servicios externos.
- **REST real falla sin env**: los steps que usan `integration.lms`/`email_ceibal` requieren
  `LMS_URL`, `SMTP_HOST`, etc. Sin ellos, el proceso queda **FAILED** (recuperable con `/retry`).
- **Reglas son async**: tras una transición hay que esperar unos segundos a que el consumidor
  RabbitMQ dispare el proceso.
- **Cache 30 s** y **CLI utf-8**: ver prerrequisitos.
- **Sin UI operativa**: todo esto es API/CLI; la review-ui solo cubre borradores IA.

## Relacionado
[[teleflow-plataforma]] · [[roadmap]] · [[2026-07-09-validacion-doc-vs-codigo]] ·
[[2026-06-30-adr-002-durable-sleep]]
