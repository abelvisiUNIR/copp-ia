---
project: copp-ia
date: 2026-07-25
status: accepted
provenance: copp-ia@devyos@3db6cd3
tags: [adr, backup, durabilidad, postgres, rabbitmq, produccion]
---

# ADR (wiki): qué se respalda, qué no, y por qué

> Provenance: `copp-ia@devyos@3db6cd3`. Decisión tomada durante el work-stream
> [[estado-durable]]. **No** es un ADR del arquitecto (los suyos son ADR-001..005).

## Context
El producto se instala **por organismo** ([[2026-06-30-adr-005-aislamiento-instancia]]), así
que el respaldo no es un servicio central: es un procedimiento que alguien va a correr en cada
instalación. No existía ninguno — ni script, ni documentación, ni prueba.

Inventario del estado durable (`docker-compose.yml` declara **dos** volúmenes):

| Servicio | Qué guarda | ¿Reconstruible? |
|---|---|---|
| **Postgres** (`pgdata`) | flows registrados, instancias y transiciones, entidades, señales, API keys, auditoría | **No** |
| Redis | pub/sub de señales, contadores de rate limit, cache de identidades | Sí — efímero por diseño |
| Grafana (`grafana-data`) | dashboards | Sí — viven en la imagen desde `eacc05d` |
| **RabbitMQ** | colas y **DLQ** | **No tenía volumen** |

## Decision

### 1. Se respalda Postgres, y nada más
Es el único lugar con estado que el producto no puede reconstruir. Redis es cache y coordinación
—si se pierde, el gateway resuelve identidades contra Postgres otra vez y los contadores del
rate limit arrancan de cero—; los dashboards viven en la imagen.

### 2. RabbitMQ **no se respalda, pero sí se hace durable**
Una cola no es un registro: respaldar mensajes en vuelo y reinyectarlos después duplicaría
trabajo ya hecho. Pero la DLQ **sí tiene que sobrevivir a un reinicio**: contiene los eventos
que fallaron, que son la evidencia de qué se rompió.

Hoy no sobrevive. El código declara todo durable —exchanges y colas `durable=True`, mensajes
`PERSISTENT`— pero el servicio no tiene volumen, así que `/var/lib/rabbitmq` vive en la capa
escribible del contenedor. Medido: sobrevive a `restart`, **se pierde con `--force-recreate`**,
que es lo que hace `docker compose up --build`. Se le agrega un volumen.

### 3. El backup se hace con la base **arriba**, con `pg_dump`
`pg_dump` toma una instantánea transaccionalmente consistente sin bloquear escrituras. Parar el
servicio para respaldar convertiría el respaldo en una interrupción, y un respaldo que cuesta
una ventana de mantenimiento se corre menos seguido — que es la peor forma de no tener respaldo.

Formato **custom** (`-Fc`), no SQL plano: permite restaurar selectivamente y comprime.

### 4. El restore se prueba **contra una base aparte**, y eso corre en la suite
Un backup sin restore probado no es un respaldo: es un archivo. El test crea datos conocidos,
respalda, restaura **en otra base** y verifica que los datos están.

Contra otra base y no sobre la de trabajo: un test que restaura encima de la base real sería un
test que puede destruir el entorno de quien lo corre.

### 5. La política de retención es del organismo
No se implementa rotación ni subida a un destino remoto. Dónde se guardan los dumps, cuántos y
por cuánto tiempo depende de la infraestructura de cada organismo y de su marco normativo. Lo
que el producto aporta es el procedimiento probado.

## Rationale
- **Respaldar solo lo irreconstruible** mantiene el procedimiento corto, y un procedimiento
  corto se corre. Un backup que abarca todo tarda más, falla más seguido y se abandona.
- **La DLQ es evidencia, no trabajo pendiente.** Por eso importa que sobreviva, y por eso no
  hace falta respaldarla: si se pierde con el contenedor, no hay a quién preguntarle qué falló.
- **Probar el restore y no el backup**, porque el backup "funciona" siempre: produce un archivo.
  Lo que puede estar roto es lo otro.

## Consequences
- **Un volumen más** (`rabbitmq-data`). Crece con los mensajes retenidos; la DLQ debería estar
  casi siempre vacía, así que el crecimiento esperado es mínimo — pero si la DLQ se llena y
  nadie la vacía, ese volumen crece sin techo. Es el mismo compromiso que la tabla de auditoría.
- **El `pgdata` de una instalación existente no se toca**: agregar el volumen de RabbitMQ no
  migra los mensajes que ya se perdieron.
- **El test de restore necesita `pg_dump`/`pg_restore`**, que están en la imagen de Postgres:
  se ejecutan con `docker compose exec`, sin pedirle al host que tenga el cliente instalado.

## Alternatives
- **Respaldar el volumen `pgdata` a nivel de archivos** (copiar el directorio) — descartada:
  copiar el directorio de datos de una base **encendida** produce un respaldo inconsistente
  salvo que se pare el servicio o se use snapshot del filesystem. `pg_dump` es consistente sin
  parar nada.
- **Respaldar también RabbitMQ** — descartada: ver decisión 2.
- **`pg_dumpall`** — descartada: incluye roles y otras bases del cluster, que en una instalación
  por organismo no aportan y hacen el restore más difícil de dirigir.
- **Rotación y subida a S3/objeto** — fuera de alcance a propósito (decisión 5).

## Sources
`docker-compose.yml:36,51-61,164-166` · `teleflow/executor_service/events.py:62,84,112,118` ·
[[backlog-hardening]] (ítem 6) · [[2026-06-30-adr-005-aislamiento-instancia]] ·
[[fallas-silenciosas]]
