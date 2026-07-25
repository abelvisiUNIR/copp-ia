---
project: copp-ia
date: 2026-07-25
status: accepted
provenance: copp-ia@devyos@0697d7c
tags: [adr, executor, gateway, idempotencia, integridad]
---

# ADR (wiki): idempotencia de `/execute`

> Provenance: `copp-ia@devyos@0697d7c`. Decisión tomada al abrir el work-stream
> [[idempotencia-execute]]. **No** es un ADR del arquitecto (los suyos son ADR-001..005).

## Context
`engine.trigger(...)` crea una `ProcessInstance` en cada llamada, sin deduplicar. Un cliente
que reintenta por timeout —el reintento más común y más razonable— dispara el proceso dos
veces. En orquestación de negocio eso no es un problema de performance: son dos expedientes,
dos notificaciones al ciudadano y dos llamadas a la integración, y no se deshace.

`correlation_id` ya existe pero **no sirve** para esto: no es único y es un id de traza, así
que una misma transacción puede legítimamente disparar varios procesos con el mismo valor.

## Decision

### 1. La clave viaja en el header `Idempotency-Key`, y el gateway la reenvía explícitamente
Es la convención que los clientes ya conocen. **Pero el proxy del gateway arma los headers
desde cero** (`gateway/main.py:291`) — una buena decisión de seguridad, porque evita colar
headers del exterior a los servicios internos. Sin tocar nada, un `Idempotency-Key` mandado al
gateway se perdería en el camino: el cliente creería estar protegido y no lo estaría.

Se resuelve **en la ruta `/execute`, no en el proxy**: esa ruta pasa el header explícitamente.
No se agrega una lista blanca general de headers a reenviar, porque una lista es algo que
alguien olvida actualizar ([[fallas-silenciosas]]). El executor también acepta la clave en el
cuerpo, para quien lo llame directo.

### 2. La clave es global y opcional
Sin clave, el comportamiento es el de hoy: cada llamada crea una instancia. Con clave, la
primera crea y las repeticiones devuelven **la misma instancia**, con `idempotent_replay:
true` para que el cliente sepa que no creó nada nuevo.

Global —y no por flow— porque el cliente genera un UUID por operación; exigirle que además
sepa que el alcance es por flow es una regla más para equivocarse, y la unicidad global es
más estricta, nunca menos.

### 3. La misma clave con otro pedido es un **409**, no un replay
Si llega una clave ya usada pero con otro `flow_name` o distinto payload, se rechaza con 409
en vez de devolver la instancia vieja.

Devolver la vieja sería lo "amable" y es la peor opción: el cliente pidió **A**, recibe el
resultado de **B** y cree que A se disparó. Un 409 es un bug del cliente que se ve; un replay
silencioso es un proceso de negocio que nunca ocurrió y nadie sabe.

### 4. La clave vive con la instancia, sin expiración
Es una columna `idempotency_key` en `process_instances` con índice único, no una tabla aparte
con TTL. La ventana de protección es entonces **para siempre**, no unas horas.

Una tabla con TTL es más ortodoxa, pero acá agrega una tabla, un proceso de limpieza y una
ventana en la que la garantía deja de valer sin que nadie lo note. Reusar la fila que ya
existe hace que la clave y lo que protege vivan y mueran juntos.

## Rationale
- **La carrera la corta la base, no el chequeo.** Igual que en el registry: leer antes de
  insertar deja una ventana. El `UNIQUE` sobre `idempotency_key` es la garantía real; el
  `IntegrityError` se atrapa y se devuelve la instancia que ganó. Mismo patrón, mismo criterio.
- **El header explícito en la ruta, y no una lista blanca en el proxy**, porque la lista es
  justo la clase de mecanismo que se desactualiza en silencio.
- **409 sobre replay silencioso** es la misma regla que viene ordenando todo este trabajo: un
  error visible es mejor que un resultado plausible y equivocado.

## Consequences
- **Migración `0005`** — cuarta desde el schema inicial.
- **Sin clave no hay protección.** Es opcional a propósito (no se rompe ningún cliente), pero
  significa que la garantía existe solo si el cliente colabora. Hay que decirlo en el README.
- **`process_instances` gana un índice único** sobre una columna nullable. En Postgres varios
  `NULL` no colisionan, así que las instancias sin clave —la mayoría— no se estorban.
- **La clave no expira**, así que dos operaciones distintas con la misma clave a meses de
  distancia dan 409. Es el precio de no tener ventana; se documenta.

## Alternatives
- **Hacer único `correlation_id`** — descartada: cambia el significado de un campo existente y
  rompe a quien lo reutilice legítimamente para varios procesos de la misma transacción.
- **Tabla `idempotency_keys` aparte con TTL** — descartada por ahora (ver decisión 4).
  Reconsiderable si alguna vez hay que idempotizar operaciones que no crean una instancia.
- **Deduplicar por hash del payload, sin clave explícita** — descartada: dos altas idénticas y
  legítimas (el mismo trámite pedido dos veces a propósito) serían indistinguibles de un
  reintento. La intención la tiene que declarar el cliente.
- **Lista blanca de headers a reenviar en `_proxy`** — descartada: una lista que alguien
  olvida actualizar, con el olvido silencioso.

## Sources
`teleflow/gateway/main.py:282-296,449-452` · `teleflow/executor_service/main.py:96-113` ·
`teleflow/executor_service/engine.py:133-170` · `teleflow/common/models.py:54-72` ·
[[backlog-hardening]] (ítem 4) · [[fallas-silenciosas]]
