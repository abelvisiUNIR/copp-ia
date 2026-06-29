# TeleFlow Platform
## Business & Software as Code
### Documento de Arquitectura v1.0
*Junio 2026 · Confidencial*

---

## Tabla de contenidos

1. [Visión y propuesta de valor](#1-visión-y-propuesta-de-valor)
2. [Arquitectura general](#2-arquitectura-general)
3. [Arquitectura de microservicios](#3-arquitectura-de-microservicios)
4. [El lenguaje TeleFlow DSL v2](#4-el-lenguaje-teleflow-dsl-v2)
5. [Ciclos de vida](#5-ciclos-de-vida)
6. [Arquitectura event-driven](#6-arquitectura-event-driven)
7. [Vista 360 del objeto de negocio](#7-vista-360-del-objeto-de-negocio)
8. [Durable sleep — procesos de larga duración](#8-durable-sleep--procesos-de-larga-duración)
9. [Despliegue y operación](#9-despliegue-y-operación)
10. [Stack tecnológico](#10-stack-tecnológico)
11. [Decisiones de arquitectura (ADRs)](#11-decisiones-de-arquitectura-adrs)

---

## 1. Visión y propuesta de valor

TeleFlow es una plataforma de orquestación empresarial basada en el principio **Business & Software as Code**. Permite a organismos públicos y privados modelar, desplegar y ejecutar sus procesos de venta y post-venta como código declarativo, con el mismo rigor con que Terraform gestiona infraestructura.

**La propuesta de valor central:**

- Un analista de negocio describe un proceso en lenguaje natural
- Una IA configurable genera el archivo `.tflow` correspondiente
- Un desarrollador lo revisa y aprueba en una UI tipo pull-request
- El motor lo ejecuta de forma confiable, observable y recuperable
- Todo sin importar si el proceso dura segundos o semanas

TeleFlow no es SaaS. Es un producto que se instancia por organismo, como GitLab self-hosted. Cada OSE, Antel, Ceibal o Ministerio posee y opera su propia instancia con datos completamente aislados. El mismo `docker-compose.yml` y los mismos Helm charts sirven a todos.

### 1.1 Analogías de diseño

| Concepto TeleFlow | Analogía técnica | Analogía de negocio |
|---|---|---|
| Archivo `.tflow` | Helm chart / K8s manifest | Especificación del proceso |
| `entity` | Aggregate (DDD) | Niño, cliente, contrato |
| `process` | Kubernetes Deployment | Proceso de venta, soporte |
| `relation` | Join con estado propio | Inscripción, contrato activo |
| Registry Service | OCI Registry / Helm repo | Repositorio de procesos |
| Executor Service | Kubernetes controller loop | Motor de ejecución |
| Instance | Pod en ejecución | Venta en curso |
| State Store | etcd del cluster | Estado durable del negocio |

---

## 2. Arquitectura general

### 2.1 Vista de plataforma

```mermaid
graph TD
    subgraph ORGANISMOS["Organismos cliente (instancia propia por organismo)"]
        OSE["OSE"]
        ANTEL["Antel"]
        CEIBAL["Ceibal"]
        ME["Min. Economía"]
    end

    subgraph IA["Capa IA — Generación de procesos"]
        ANALISTA["Analista de negocio\n(lenguaje natural)"]
        LLM["LLM configurable\n(Claude / GPT-4o / self-hosted)"]
        REVIEW["UI revisión\n(PR-style · dev aprueba)"]
        ANALISTA --> LLM --> REVIEW
    end

    subgraph ENGINE["TeleFlow Engine"]
        GW["api-gateway :8000"]
        PARSER["parser-service :8001\nLark · AST · validación"]
        REGISTRY["registry-service :8003\nVersiones · inmutable"]
        EXECUTOR["executor-service :8002\nDAG async · durable sleep"]
        GW --> PARSER
        GW --> REGISTRY
        GW --> EXECUTOR
    end

    subgraph INFRA["Infraestructura de datos"]
        REDIS["Redis\ncache · pub/sub · sleep"]
        PG["PostgreSQL\ninstancias · audit log"]
        RMQ["RabbitMQ\neventos · integraciones ext."]
    end

    subgraph OBS["Observabilidad"]
        PROM["Prometheus"]
        GRAFANA["Grafana\ndashboards negocio"]
        PROM --> GRAFANA
    end

    ORGANISMOS --> IA
    REVIEW -->|"POST /flows/{name}"| GW
    EXECUTOR --> REDIS
    EXECUTOR --> PG
    EXECUTOR --> RMQ
    ENGINE --> OBS
```

### 2.2 Capas del sistema

**Capa 1 — Generación IA**

El analista de negocio describe el proceso en lenguaje natural. Un LLM configurable por organismo genera el borrador `.tflow`. Una UI web tipo pull-request presenta el diff al desarrollador, quien aprueba o rechaza con comentarios.

Componentes: `composer-service` (abstracción LLM) · `review-ui` (React + diff viewer)

**Capa 2 — TeleFlow Engine (microservicios Python)**

Cuatro servicios con responsabilidad única. Ver sección 3.

**Capa 3 — Infraestructura de datos**

- **Redis**: cache de ASTs frecuentes · pub/sub para eventos · durable sleep de instancias dormidas
- **PostgreSQL**: estado durable — flows, instancias, entity state, audit log inmutable
- **RabbitMQ**: bus de eventos de dominio. Permite que sistemas externos se suscriban sin acoplamiento directo

**Capa 4 — Observabilidad**

Prometheus scraping en `/metrics` de todos los servicios. Grafana con dashboards técnicos (latencia, tasa de error) y de negocio (procesos completados, backlog de human_tasks).

---

## 3. Arquitectura de microservicios

### 3.1 Diagrama de servicios

```mermaid
graph TD
    CLIENT["Cliente externo\n(CLI / API / CI-CD / UI revisión)"]

    subgraph GATEWAY["api-gateway :8000"]
        AUTH["Auth · Rate limit · Routing"]
    end

    subgraph CORE["Servicios core (red interna)"]
        PARSER["parser-service :8001\nLark LALR · AST JSON\nvalidación sintáctica + semántica"]
        REGISTRY["registry-service :8003\nPostgres · semver\nversiones inmutables"]
        EXECUTOR["executor-service :8002\nDAG engine · async/await\ndurable sleep · signals"]
    end

    subgraph ADAPTERS["Adapters (executor)"]
        REST["REST\n(TMF APIs)"]
        AMQP["AMQP\n(RabbitMQ)"]
        SMTP["SMTP\n(email)"]
        SMS["SMS\ngateway"]
    end

    subgraph DATA["Estado"]
        REDIS["Redis\ncache · pub/sub · sleep"]
        PG["PostgreSQL\ndurable state"]
        RMQ["RabbitMQ\nbus de eventos"]
    end

    CLIENT -->|"HTTPS + X-TeleFlow-API-Key"| GATEWAY
    GATEWAY --> PARSER
    GATEWAY --> REGISTRY
    GATEWAY --> EXECUTOR
    EXECUTOR --> ADAPTERS
    EXECUTOR --> REDIS
    EXECUTOR --> PG
    ADAPTERS --> RMQ
```

### 3.2 Responsabilidades por servicio

| Servicio | Puerto | Responsabilidad única |
|---|---|---|
| `api-gateway` | 8000 | Único punto de entrada externo. Auth, rate limiting, routing. Los clientes solo conocen este endpoint |
| `parser-service` | 8001 | Recibe source `.tflow`, produce AST validado en JSON. Valida sintaxis Y semántica. **Nunca ejecuta nada** |
| `registry-service` | 8003 | Almacena y versiona definiciones. Una versión registrada es **inmutable**. Expone `latest` como pointer mutable |
| `executor-service` | 8002 | Construye el DAG del flow, recorre cada step de forma async. Durable sleep para `human_task` de días/semanas |
| `composer-service` | 8004 | Abstracción LLM. Genera borradores `.tflow` desde lenguaje natural |
| `review-ui` | 3100 | UI React para revisión PR-style de flows generados por IA |

### 3.3 Contratos entre servicios

**Deploy de un flow:**

```
POST /flows/{name}
{
  "source": "process \"venta_...\" { ... }",
  "version": "1.3.0",
  "description": "Agrega validación de crédito en paso 2"
}

→ api-gateway → parser-service (valida) → registry-service (persiste)
← { flow_id, name, version, status: "registered" }
```

**Ejecución de proceso (async):**

```
POST /execute
{
  "flow_name": "venta_internet_hogar",
  "version": "latest",
  "payload": { "cliente_id": "...", "producto": "..." },
  "correlation_id": "uuid-externo"
}
← { instance_id, status: "TRIGGERED" }   // respuesta inmediata

GET /instances/{instance_id}
← { status: "IN_PROGRESS", current_step: "validar_identidad", context: {...} }
```

**Señal a human_task:**

```
POST /instances/{id}/signal
{
  "step_name": "aprobacion_gerencia",
  "signal": "approve",
  "actor_id": "juan.perez",
  "signal_data": { "comentario": "Aprobado con condiciones" }
}
```

**Vista 360:**

```
GET /entities/nino/{id}/360
← { estado, relaciones_activas, procesos_en_vuelo, eventos, alertas }
```

---

## 4. El lenguaje TeleFlow DSL v2

El DSL es el corazón del producto. Un archivo `.tflow` es una declaración completa del dominio de negocio: entidades, sus relaciones, los procesos que las transforman, las reglas que conectan eventos con procesos, y las integraciones externas.

### 4.1 Bloques disponibles

| Bloque | Estado | Descripción |
|---|---|---|
| `entity` | 🆕 NUEVO | Objeto de negocio con identidad, campos tipados, máquina de estados explícita, invariantes y eventos emitidos por transición |
| `relation` | 🆕 NUEVO | Vínculo entre dos entities con su propio estado y ciclo de vida. El "producto instanciado" (ej: inscripción niño↔curso) |
| `rule` | 🆕 NUEVO | Regla de negocio event-driven. Cuatro tipos: `on_event`, `on_state`, `on_timer`, `on_relation` |
| `view360` | 🆕 NUEVO | Declara la vista 360 de un entity: estado, relaciones activas, procesos en vuelo, historial de eventos, alertas |
| `process` | existente | Orquesta steps en stages (sequential, parallel, decision). Ahora puede emitir eventos de dominio y modificar estado de entities |
| `step` | existente | Tarea atómica reutilizable: `automated`, `human_task`, `decision`, `notification` |
| `integration` | existente | Conectores externos: REST, AMQP/Kafka, SMTP, SMS. Credenciales via `${env.VAR}` |
| `catalog` | existente | Productos ofertables. Puede referenciar una entity como su instancia al contratarse |
| `party` | existente | Actores del proceso. Puede vincularse a una entity |

### 4.2 Sintaxis — bloque `entity`

```hcl
entity "nino" {
  description: "Estudiante registrado en Ceibal"

  fields {
    ci:           string   required unique
    nombre:       string   required
    fecha_nac:    date     required
    departamento: string
    nivel:        enum["primaria", "secundaria", "utu"]
    dispositivo:  string   optional
  }

  lifecycle {
    initial: "REGISTRADO"
    states ["REGISTRADO", "ACTIVO", "INSCRIPTO", "GRADUADO", "INACTIVO"]

    transitions {
      REGISTRADO -> ACTIVO     via "activar"
      ACTIVO     -> INSCRIPTO  via "inscribir"
      INSCRIPTO  -> ACTIVO     via "desinscribir"
      ACTIVO     -> GRADUADO   via "graduar"
      ACTIVO     -> INACTIVO   via "desactivar"
    }
  }

  events {
    on_transition "activar"      emit "nino.activado"
    on_transition "inscribir"    emit "nino.inscripto"
    on_transition "graduar"      emit "nino.graduado"
    on_field_change "nivel"      emit "nino.nivel_cambiado"
  }

  invariants {
    "edad >= 5 AND edad <= 18"
    "nivel != null WHEN estado == INSCRIPTO"
  }
}
```

### 4.3 Sintaxis — bloque `relation`

```hcl
relation "inscripcion" {
  description: "Vínculo entre un niño y un curso activo"

  from: entity.nino
  to:   entity.curso
  cardinality: "many_to_many"
  constraint:  "nino puede estar en max 3 cursos simultáneos"

  lifecycle {
    initial: "PENDIENTE"
    states ["PENDIENTE", "ACTIVA", "COMPLETADA", "ABANDONADA"]
    transitions {
      PENDIENTE -> ACTIVA      via "activar"
      ACTIVA    -> COMPLETADA  via "completar"
      ACTIVA    -> ABANDONADA  via "abandonar"
    }
  }

  fields {
    fecha_inscripcion: date      required
    modalidad:         enum["presencial", "virtual"]
    progreso:          number    default(0) range(0, 100)
    ultimo_acceso:     datetime  optional
  }

  events {
    on_transition "activar"     emit "inscripcion.activada"
    on_transition "completar"   emit "inscripcion.completada"
    on_field_change "progreso"  emit "inscripcion.progreso_actualizado"
  }
}
```

### 4.4 Sintaxis — bloque `rule`

```hcl
// Regla simple: evento dispara proceso
rule "activar_acceso_al_inscribirse" {
  on_event: "inscripcion.activada"
  execute:  process.activacion_acceso_plataforma
  with {
    nino_id:  event.from_id
    curso_id: event.to_id
  }
}

// Regla con condición sobre campos del objeto
rule "prioridad_dispositivo" {
  on_event:  "nino.activado"
  condition: event.entity.dispositivo == null
  execute:   process.asignacion_dispositivo
}

// Regla temporal: si condición persiste N días
rule "detectar_abandono" {
  on_timer {
    after:     30 days
    since:     "inscripcion.activada"
    condition: days_since(relation.inscripcion.ultimo_acceso) >= 30
               OR relation.inscripcion.ultimo_acceso == null
  }
  execute: process.reenganche_estudiante
  with {
    nino_id:  relation.from_id
    curso_id: relation.to_id
  }
}

// Regla sobre completar un curso
rule "emitir_certificado_al_completar" {
  on_event:  "inscripcion.completada"
  condition: relation.inscripcion.progreso >= 80
  execute:   process.emision_certificado
}
```

### 4.5 Sintaxis — bloque `view360`

```hcl
view360 "nino" {
  entity: entity.nino

  relations {
    inscripciones_activas: relation.inscripcion
      where estado == "ACTIVA"
      include [curso.nombre, progreso, ultimo_acceso]

    historial_cursos: relation.inscripcion
      where estado in ["COMPLETADA", "ABANDONADA"]
      include [curso.nombre, fecha_inscripcion, estado]
  }

  active_processes {
    include: [
      process.activacion_acceso_plataforma,
      process.reenganche_estudiante,
      process.emision_certificado
    ]
    filter: instance.payload.nino_id == entity.id
  }

  event_timeline {
    events: all
    limit:  50
    order:  "desc"
  }

  alerts {
    rule: rule.detectar_abandono
    rule: rule.prioridad_dispositivo
  }
}
```

---

## 5. Ciclos de vida

### 5.1 Máquina de estados de una entity (ejemplo: niño en Ceibal)

```mermaid
stateDiagram-v2
    [*] --> REGISTRADO : crear

    REGISTRADO --> ACTIVO : activar\nemit nino.activado

    ACTIVO --> INSCRIPTO : inscribir\nemit nino.inscripto
    INSCRIPTO --> ACTIVO : desinscribir

    ACTIVO --> GRADUADO : graduar\nemit nino.graduado
    ACTIVO --> INACTIVO : desactivar

    GRADUADO --> [*]
    INACTIVO --> ACTIVO : reactivar
```

### 5.2 Máquina de estados de una relation (ejemplo: inscripción)

```mermaid
stateDiagram-v2
    [*] --> PENDIENTE : crear relación

    PENDIENTE --> ACTIVA : activar\nemit inscripcion.activada

    ACTIVA --> COMPLETADA : completar\nemit inscripcion.completada
    ACTIVA --> ABANDONADA : abandonar\nemit inscripcion.abandonada

    COMPLETADA --> [*]
    ABANDONADA --> [*]
```

### 5.3 Estados de una instancia de proceso

```mermaid
stateDiagram-v2
    [*] --> TRIGGERED : POST /execute

    TRIGGERED --> IN_PROGRESS : executor inicia DAG

    IN_PROGRESS --> WAITING_SIGNAL : step human_task\n(duerme en Postgres)
    WAITING_SIGNAL --> IN_PROGRESS : POST /signal\n(reactiva vía Redis)

    IN_PROGRESS --> COMPLETED : todos los steps OK
    IN_PROGRESS --> FAILED : step agota reintentos

    FAILED --> RETRYING : POST /retry
    RETRYING --> IN_PROGRESS : retoma desde step fallido
    RETRYING --> COMPENSATED : rollback exitoso

    COMPLETED --> [*]
    COMPENSATED --> [*]
```

---

## 6. Arquitectura event-driven

### 6.1 Modelo de tres capas

```mermaid
sequenceDiagram
    participant E as entity / relation
    participant BUS as RabbitMQ\n(teleflow.domain.events)
    participant R as rule engine
    participant EX as executor-service
    participant EXT as Sistema externo\n(SAP, CRM, etc.)

    E->>BUS: emit "nino.inscripto"\n{ nino_id, curso_id, ... }

    BUS->>R: routing key: nino.inscripto
    BUS->>EXT: routing key: nino.* (suscriptor AMQP)

    R->>R: evalúa condition
    R->>EX: POST /internal/execute\n{ flow: activacion_acceso, payload }

    EX->>EX: construye DAG
    EX->>EX: ejecuta steps async

    note over E,EXT: on_timer: el rule engine evalúa<br/>periódicamente condiciones temporales
```

### 6.2 Tipos de triggers

| Tipo | Cuándo dispara | Ejemplo |
|---|---|---|
| `on_event` | Inmediatamente al recibir el evento del bus | `nino.inscripto` → activar acceso en plataforma |
| `on_state` | Cuando entity/relation alcanza un estado específico | `inscripcion.COMPLETADA` → emitir certificado |
| `on_timer` | Si condición sigue siendo verdadera N días después de un evento | 30 días sin acceso desde `inscripcion.activada` → reenganche |
| `on_relation` | Al crear, modificar o eliminar una relation entre entities | Se crea `inscripcion` niño↔curso → notificar al tutor |

### 6.3 Flujo completo del dominio Ceibal

```mermaid
flowchart TD
    A["Ceibal publica curso\nentity.curso → DISPONIBLE\nemit curso.disponible"] 
    B["rule.notificar_oferta\non_event: curso.disponible"]
    C["process.notificacion_oferta_curso\nnotifica a alumnos elegibles"]
    D["Niño/tutor inicia inscripción\nPOST /execute inscripcion_curso"]
    E["relation.inscripcion creada\nestado: PENDIENTE → ACTIVA\nemit inscripcion.activada\nnino → INSCRIPTO\nemit nino.inscripto"]
    F["rule.activar_acceso\non_event: inscripcion.activada"]
    G["process.activacion_acceso_plataforma\nasigna credenciales LMS"]
    H{"30 días sin acceso?"}
    I["rule.detectar_abandono\non_timer: 30d"]
    J["process.reenganche_estudiante\nnotifica tutor + reminder"]
    K["Niño completa curso\nrelation → COMPLETADA\nemit inscripcion.completada"]
    L["rule.emitir_certificado\ncondition: progreso >= 80"]
    M["process.emision_certificado\ngenera y notifica"]

    A --> B --> C
    C --> D --> E
    E --> F --> G
    G --> H
    H -->|Sí| I --> J
    H -->|No| K
    K --> L --> M
```

---

## 7. Vista 360 del objeto de negocio

### 7.1 Arquitectura de la vista 360

```mermaid
graph LR
    subgraph API["GET /entities/nino/{id}/360"]
        GW["api-gateway"]
    end

    subgraph SOURCES["Fuentes de datos (en paralelo)"]
        ES["entity state\nPostgres"]
        RS["relations activas\ne históricas"]
        PS["procesos en vuelo\nexecutor-service"]
        EV["línea de tiempo\nde eventos"]
        AL["alertas de reglas\nactivas"]
    end

    subgraph RESPONSE["Respuesta agregada"]
        R360["Vista 360 completa\nJSON"]
    end

    GW --> ES
    GW --> RS
    GW --> PS
    GW --> EV
    GW --> AL
    ES --> R360
    RS --> R360
    PS --> R360
    EV --> R360
    AL --> R360
```

### 7.2 Ejemplo de respuesta — Niño Juan Pérez en Ceibal

```json
{
  "entity": "nino",
  "id": "uuid-juan-perez",
  "estado_actual": "INSCRIPTO",
  "campos": {
    "nombre": "Juan Pérez",
    "ci": "1.234.567-8",
    "nivel": "secundaria",
    "departamento": "Montevideo",
    "dispositivo": "XO-4 asignado"
  },
  "relaciones_activas": [
    {
      "tipo": "inscripcion",
      "curso": "Robótica Básica",
      "estado": "ACTIVA",
      "progreso": 65,
      "ultimo_acceso": "2026-06-10"
    },
    {
      "tipo": "inscripcion",
      "curso": "Matemática Digital",
      "estado": "ACTIVA",
      "progreso": 30,
      "ultimo_acceso": "2026-05-23"
    }
  ],
  "procesos_activos": [
    {
      "flow": "asignacion_dispositivo",
      "instance_id": "uuid",
      "status": "IN_PROGRESS",
      "current_step": "verificar_stock",
      "paso": "2/4"
    }
  ],
  "alertas": [
    {
      "rule": "detectar_abandono",
      "severidad": "warning",
      "mensaje": "Matemática Digital: 18 días sin acceso"
    }
  ],
  "timeline": [
    { "fecha": "2026-06-08", "evento": "nino.inscripto",      "detalle": "Robótica Básica" },
    { "fecha": "2026-05-20", "evento": "inscripcion.activa",  "detalle": "Matemática Digital" },
    { "fecha": "2026-05-15", "evento": "nino.activado",       "detalle": "" },
    { "fecha": "2026-05-15", "evento": "nino.registrado",     "detalle": "" }
  ]
}
```

---

## 8. Durable sleep — procesos de larga duración

### 8.1 Flujo de durable sleep

```mermaid
sequenceDiagram
    participant EX as executor-service
    participant PG as PostgreSQL
    participant RE as Redis
    participant ACT as Actor humano
    participant GW as api-gateway

    EX->>EX: llega a step human_task
    EX->>PG: instancia → WAITING_SIGNAL\nguarda contexto completo
    EX->>RE: SUBSCRIBE signal:{instance_id}
    note over EX: worker liberado\nsin polling, sin bloqueo

    note over ACT: días o semanas después...

    ACT->>GW: POST /instances/{id}/signal\n{ signal: "approve", actor_id: "juan.p" }
    GW->>PG: registra señal en audit log
    GW->>RE: PUBLISH signal:{instance_id}\n{ signal, actor_id, data }

    RE-->>EX: mensaje recibido
    EX->>PG: instancia → IN_PROGRESS
    EX->>EX: continúa DAG desde\nel step siguiente
```

### 8.2 Garantías del durable sleep

- El executor puede **reiniciarse sin perder instancias dormidas** — estado completo en Postgres
- La reactivación tiene **latencia de milisegundos** — Redis pub/sub
- **Sin polling activo** ni timers que consuman recursos
- La señal es **idempotente** — múltiples envíos del mismo `signal_id` no crean efectos duplicados
- El **audit log** registra quién envió la señal, cuándo, y con qué datos

---

## 9. Despliegue y operación

### 9.1 Modelo de despliegue

```mermaid
graph TD
    subgraph DEV["Desarrollo / Staging"]
        DC["docker compose up\n(un servidor)"]
    end

    subgraph PROD["Producción"]
        K8S["Kubernetes / Rancher RKE2"]
        subgraph NS["Namespace: teleflow"]
            D1["Deployment: api-gateway (2 pods)"]
            D2["Deployment: parser-svc (2 pods)"]
            D3["Deployment: registry-svc (2 pods)"]
            D4["Deployment: executor-svc (3 pods)"]
            S1["StatefulSet: redis"]
            S2["StatefulSet: postgres"]
            S3["StatefulSet: rabbitmq"]
        end
    end

    DEV -->|"mismo código\nvariables de entorno"| PROD
    DC -->|"docker-compose.yml\n→ Helm charts /helm/"| K8S
```

### 9.2 Servicios del stack

| Servicio | Puerto | Responsabilidad |
|---|---|---|
| `api-gateway` | 8000 | Único punto de entrada externo. Auth, rate limit, routing |
| `parser-service` | 8001 | Lark LALR → AST JSON. Validación sintáctica y semántica |
| `registry-service` | 8003 | Versionado inmutable de flows. Pointer `latest` mutable |
| `executor-service` | 8002 | DAG engine async. Durable sleep. Adapters REST/AMQP/SMTP/SMS |
| `composer-service` | 8004 | Abstracción LLM. Genera borradores `.tflow` desde lenguaje natural |
| `review-ui` | 3100 | UI React para revisión PR-style de flows generados por IA |
| `redis` | 6379 | Cache de ASTs · pub/sub · durable sleep de instancias |
| `postgres` | 5432 | Estado durable: flows, instancias, events, audit log |
| `rabbitmq` | 5672 | Bus de eventos de dominio. Integración con sistemas externos |
| `prometheus` | 9090 | Scraping de métricas de todos los servicios |
| `grafana` | 3000 | Dashboards técnicos y de negocio |

### 9.3 Variables de entorno clave

| Variable | Descripción |
|---|---|
| `TELEFLOW_API_KEY` | API key para autenticación en el gateway |
| `LLM_PROVIDER` | `anthropic` \| `openai` \| `ollama` |
| `LLM_API_KEY` | Clave del proveedor LLM configurado |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@postgres:5432/teleflow` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `RABBITMQ_URL` | `amqp://user:pass@rabbitmq:5672/` |
| `WORKER_CONCURRENCY` | Instancias concurrentes en el executor (default: 10) |

### 9.4 Schema de base de datos

```mermaid
erDiagram
    flow_definitions {
        uuid id PK
        varchar name
        varchar version
        text source
        jsonb ast
        varchar checksum
        varchar status
        timestamptz created_at
    }

    flow_latest {
        varchar name PK
        varchar version
        timestamptz updated_at
    }

    process_instances {
        uuid id PK
        varchar flow_name
        varchar flow_version
        varchar correlation_id
        varchar status
        jsonb trigger_payload
        jsonb context
        varchar current_step
        jsonb error
        timestamptz created_at
        timestamptz updated_at
    }

    instance_transitions {
        uuid id PK
        uuid instance_id FK
        varchar from_status
        varchar to_status
        varchar step_name
        jsonb step_output
        varchar actor_id
        timestamptz occurred_at
    }

    entity_state {
        uuid id PK
        varchar entity_type
        varchar entity_id
        varchar estado
        jsonb campos
        timestamptz updated_at
    }

    entity_events {
        uuid id PK
        varchar entity_type
        varchar entity_id
        varchar event_name
        jsonb payload
        timestamptz occurred_at
    }

    relation_state {
        uuid id PK
        varchar relation_type
        uuid from_id
        uuid to_id
        varchar estado
        jsonb campos
        timestamptz updated_at
    }

    flow_definitions ||--o{ process_instances : "ejecuta"
    process_instances ||--o{ instance_transitions : "registra"
    entity_state ||--o{ entity_events : "emite"
    entity_state ||--o{ relation_state : "participa en"
```

---

## 10. Stack tecnológico

| Componente | Tecnología | Justificación |
|---|---|---|
| Framework web | FastAPI + uvicorn | Async nativo, tipado con Pydantic v2, OpenAPI automático |
| Parser DSL | Lark (LALR) | Gramática EBNF en Python. Performance + legibilidad. Tree-sitter para VS Code en fase futura |
| DAG engine | networkx | Construcción y traversal del DAG del flow. Detección de ciclos |
| HTTP client | httpx | Async nativo, HTTP/2, timeouts configurables |
| AMQP client | aio-pika | RabbitMQ async, compatible con asyncio |
| ORM | SQLAlchemy async + asyncpg | Async I/O nativo hacia Postgres |
| Migraciones | Alembic | Versionado de schema. No `create_all()` en producción |
| Logging | structlog | Logging estructurado JSON. Siempre incluye `instance_id`, `flow_name`, `step_name` |
| Type checking | mypy --strict | Sin `Any` sin justificar. Pydantic v2 para modelos API |
| Testing | pytest-asyncio | Sin unittest. Fixtures async para todos los tests de integración |
| Frontend revisión | React + diff viewer | UI liviana para PR-style review de `.tflow` generados por IA |
| Observabilidad | Prometheus + Grafana | Dashboards técnicos y de negocio |

### Convenciones de código

- **Tipado estricto**: `mypy --strict` en todos los servicios. Sin `Any` sin justificar
- **Pydantic v2** para todos los modelos de entrada/salida de la API
- **Dataclasses** para nodos del AST (no Pydantic — son internas, no serializadas)
- **structlog** para logging estructurado. Siempre incluir `instance_id`, `flow_name`, `step_name`
- **pytest-asyncio** para todos los tests. No `unittest`
- **Alembic** para migraciones. No `create_all()` en producción
- Cada servicio expone `GET /health` (liveness) y `GET /ready` (readiness)
- Cada servicio expone `GET /metrics` en formato Prometheus

---

## 11. Decisiones de arquitectura (ADRs)

### ADR-001: Lark + LALR para el parser

| | |
|---|---|
| **Decisión** | Lark con algoritmo LALR como parser del DSL `.tflow` |
| **Alternativas** | PLY (lex/yacc), Parsimonious (PEG), Tree-sitter |
| **Razón** | Lark ofrece la mejor relación entre legibilidad de gramática (EBNF nativo en Python), performance LALR en producción, y extensibilidad. La gramática vive como documentación viva en `teleflow.lark`. Tree-sitter se reserva para el plugin de VS Code en Fase 4 |
| **Consecuencias** | La gramática EBNF es la fuente de verdad del lenguaje. Cualquier extensión del DSL requiere modificar `teleflow.lark` primero |

### ADR-002: Durable sleep vía Redis pub/sub + Postgres

| | |
|---|---|
| **Decisión** | Instancias en `WAITING_SIGNAL` duermen en Postgres. Redis pub/sub las reactiva |
| **Alternativas** | Polling activo, timer externo (cron), Temporal.io como runtime |
| **Razón** | El estado durable en Postgres garantiza que el executor puede reiniciarse sin perder instancias en espera. Redis pub/sub provee reactivación con latencia de milisegundos. Sin polling activo, sin timers externos. El modelo es idéntico al de Temporal.io pero con componentes estándar |
| **Consecuencias** | El executor debe suscribirse a Redis al arrancar para recuperar instancias dormidas. La señal es idempotente por diseño (`signal_id` único) |

### ADR-003: LLM configurable por instancia

| | |
|---|---|
| **Decisión** | El proveedor LLM se configura en variables de entorno de cada instancia |
| **Razón** | Cada organismo tiene restricciones propias. OSE puede usar Claude API; Antel puede tener modelo self-hosted por regulación; el Ministerio puede requerir datos en territorio nacional. La interfaz `LLMProvider` abstrae el proveedor |
| **Consecuencias** | `composer-service` implementa la interfaz `LLMProvider` para cada proveedor soportado. El cambio de proveedor es una variable de entorno, no código |

### ADR-004: RabbitMQ incluido en el stack

| | |
|---|---|
| **Decisión** | RabbitMQ como broker propio, no depender del broker del organismo |
| **Razón** | Simplifica la instalación inicial (`docker compose up` funciona sin configuración externa). Los organismos que ya tienen broker propio pueden configurar TeleFlow para usarlo vía variables de entorno, desactivando el RabbitMQ del Compose |
| **Consecuencias** | El stack es autosuficiente desde el primer día. La migración a broker externo es un cambio de configuración, no de código |

### ADR-005: Aislamiento por instancia (no multi-tenant)

| | |
|---|---|
| **Decisión** | Cada organismo tiene su propia instancia de TeleFlow con su propia base de datos |
| **Razón** | Modelo más simple de operar para organismos con equipos IT propios. Evita la complejidad de multi-tenancy (row-level security, schema switching). El producto es el mismo; la instancia es de cada organismo |
| **Consecuencias** | Los templates se actualizan vía Git pull + `tflow deploy`. No hay mecanismo automático de actualización entre instancias |

---

## Roadmap de implementación

```mermaid
gantt
    title TeleFlow — Fases de implementación
    dateFormat  YYYY-MM
    section Fase 1 — Motor básico
    parser-service (Lark + AST)         :f1a, 2026-07, 3w
    registry-service (CRUD Postgres)    :f1b, after f1a, 2w
    executor-service (sequential + REST):f1c, after f1b, 3w
    api-gateway (auth + routing)        :f1d, after f1c, 1w

    section Fase 2 — Dominio + long-running
    entity + relation + rule en parser  :f2a, after f1d, 3w
    executor: parallel + durable sleep  :f2b, after f2a, 3w
    Adapters AMQP + SMTP + SMS          :f2c, after f2b, 2w
    Prometheus + Grafana                :f2d, after f2c, 1w

    section Fase 3 — IA + 360
    composer-service (LLM abstraction)  :f3a, after f2d, 3w
    review-ui (React PR-style)          :f3b, after f3a, 3w
    view360 endpoint                    :f3c, after f3b, 2w
    Templates TMForum (6 templates)     :f3d, after f3c, 2w

    section Fase 4 — Producción
    Helm charts K8s/RKE2                :f4a, after f3d, 3w
    CLI tflow                           :f4b, after f4a, 2w
    Plugin VS Code (Tree-sitter)        :f4c, after f4b, 3w
```

---

*TeleFlow Platform · Documento de Arquitectura v1.0 · Junio 2026*
