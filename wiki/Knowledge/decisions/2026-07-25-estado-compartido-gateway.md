---
project: copp-ia
date: 2026-07-25
status: proposed
provenance: copp-ia@devyos@90c58bc
tags: [adr, gateway, escalado, redis, seguridad]
---

# ADR (wiki): el estado del gateway va a Redis, no a la memoria del proceso

> Provenance: `copp-ia@devyos@90c58bc`. Decisión tomada durante el work-stream
> [[estado-compartido-gateway]]. **No** es un ADR del arquitecto (los suyos son ADR-001..005).
> **`status: proposed`** por la **decisión 2** (rate limit en Redis), que agrega un round-trip
> a **todos** los requests: se implementa después de medirlo, no antes.
>
> **La decisión 4 (revocación por pub/sub) ya está implementada y verificada en vivo**
> (`chore/estado-compartido-gateway`): no tiene la pregunta de latencia —solo publica en el
> `DELETE`, que es rarísimo— y restauraba una promesa que el producto ya hacía.

## Context
El gateway guarda **dos cosas en memoria del proceso**, y las dos son mecanismos de seguridad:

| Estado | Dónde | Para qué |
|---|---|---|
| `_buckets` | `gateway/main.py:81` | Rate limit: un `TokenBucket` por API key, 120 rpm |
| `_cache_keys` | `gateway/main.py:194` | Identidad de la key, TTL 30 s, para no ir a la DB en cada request |

El código ya documenta el límite, con honestidad (`main.py:198-203`): la purga del cache es
del proceso, y con varias réplicas haría falta invalidación por Redis pub/sub.

**Lo que obliga a decidir ahora:** `helm/teleflow/values.yaml:28` **ya declara `replicas: 2`**
para el api-gateway. El despliegue que el repo describe **contradice** el supuesto que el
código asume. Con 2 réplicas:

- **El rate limit efectivo se duplica**: 240 rpm en vez de 120. Cada réplica cuenta por su
  lado y nadie suma.
- **Revocar una key no la corta**: el `DELETE` purga el cache de la réplica que atendió ese
  request; la otra sigue aceptando la credencial hasta 30 s más. Para una key filtrada, esos
  30 s son exactamente lo que la revocación existe para evitar.

No explotó porque el chart todavía no se probó en k8s (Fase E) y el compose levanta una sola
instancia. Es un supuesto no escrito que ya apareció **dos veces** ([[seguridad-api-keys]] y
el rate limit); la tercera es cuestión de tiempo.

## Decision

### 1. El gateway corre con N réplicas, y el estado compartido va a Redis
Se descarta "single-process por diseño". El gateway es el **único punto de entrada externo**:
con una sola instancia, un reinicio es una caída total de la API. Bajar a `replicas: 1` para
proteger un contador sería pagar disponibilidad del producto por una limitación interna.

Redis ya está en el stack y el executor ya lo usa para pub/sub de señales
([[2026-06-30-adr-002-durable-sleep]]): no se agrega infraestructura, se usa la que hay.

### 2. Rate limit: contador en Redis, con ventana fija por key
`INCR` + `EXPIRE` sobre `ratelimit:{hash_de_key}:{minuto}`. Ventana fija y no token bucket:
el bucket necesita leer-modificar-escribir con estado propio (tokens y timestamp), que en
Redis pide script Lua o transacción; la ventana fija es **dos comandos y ningún estado que
mantener**. Se pierde el suavizado en los bordes de la ventana; para un límite antiabuso de
120 rpm eso no cambia nada práctico.

La clave se guarda **hasheada** (`auth.hash_key`), no en claro: Redis no es lugar para
credenciales, ni siquiera como parte de un nombre de clave.

### 3. Si Redis no responde, se **deja pasar** — y se ve
Un limitador caído no puede convertirse en una caída del producto: se responde el request y se
incrementa `teleflow_rate_limit_degraded_total` + `log.error`.

**Pero eso es precisamente una falla silenciosa si nadie mira el contador**, así que el
contador es la señal alertable y queda documentado como tal ([[fallas-silenciosas]]). Es el
mismo criterio que se tomó hoy para la escritura de auditoría: degradar sí, en silencio no.

### 4. Revocación de keys: invalidación por Redis pub/sub, manteniendo el cache local
El cache local **se mantiene** —es lo que evita una consulta a Postgres por request— pero
`purgar_cache()` pasa a publicar en un canal (`teleflow:keys:revocadas`) y cada réplica se
suscribe y purga la suya. El TTL de 30 s queda como red de seguridad para el caso de que un
mensaje se pierda, no como el mecanismo principal.

Es exactamente el patrón que el propio comentario del código señalaba como necesario, y el que
el executor ya usa para las señales.

### 5. El chart y el código tienen que decir lo mismo
`replicas: 2` se queda, y este ADR es lo que lo justifica. Si en algún momento hubiera que
volver a una réplica, tiene que ser una decisión escrita, no un supuesto.

## Rationale
- **La disponibilidad del único punto de entrada gana sobre la exactitud del contador.** Un
  rate limit aproximado es un problema menor; un gateway que se cae al reiniciar es un
  problema del producto.
- **Ventana fija sobre token bucket** porque el estado compartido cambia el costo relativo: lo
  que en memoria era trivial, en Redis es un round-trip y un script. Menos exactitud a cambio
  de mucha menos superficie.
- **Cache local + pub/sub, y no "sacar el cache"**, porque quitarlo mandaría cada request a
  Postgres. El cache no es el problema; el problema era que la invalidación no cruzaba réplicas.
- **Fail-open con contador** en vez de fail-closed: es un limitador antiabuso, no un control
  de acceso. El control de acceso (la validez de la key y sus scopes) sigue exigiendo Postgres,
  y para eso `/ready` ya hace `db_ping`.

## Consequences
- **Un round-trip a Redis por request autenticado.** Es la consecuencia que más pesa y por la
  que este ADR está en `proposed`: hay que medirla, no suponerla. Redis en la misma red
  responde en submilisegundos, y el gateway ya hace I/O por request (proxy al servicio
  interno), así que *(inferencia)* el impacto relativo debería ser bajo — pero conviene
  medirlo antes de dar el número por bueno.
- **Redis pasa a ser dependencia del gateway**, que hoy solo depende de Postgres. Habrá que
  decidir si entra en `/ready`: **no**, según la decisión 3 — sin Redis el gateway sigue
  sirviendo, degradado y visible.
- **`_buckets` y el TTL dejan de ser la verdad**, así que los comentarios que documentan el
  límite actual hay que actualizarlos: si quedan, documentarían un problema ya resuelto.
- **Los tests del gateway tendrán que fingir Redis**, como hoy fingen la sesión de base
  (`sink_auditoria` en `conftest.py`).

## Alternatives
- **Single-process por diseño (`replicas: 1`)** — descartada: convierte cada reinicio del
  único punto de entrada en una caída total. Sería elegir un problema peor para evitar uno
  menor.
- **Dividir el límite por la cantidad de réplicas** (`rate_limit_rpm / N`) — descartada:
  exige que el proceso sepa cuántas réplicas hay, dato que cambia con el autoescalado y que
  nadie mantiene. Es exacta solo mientras nadie toque el `replicas:`.
- **Sticky sessions en el balanceador** (misma key → misma réplica) — descartada: resuelve el
  rate limit por accidente, no resuelve la revocación, y ata el comportamiento del producto a
  la configuración del ingress de cada organismo.
- **Sacar el cache de identidades** — descartada: mandaría cada request a Postgres. El cache
  no era el problema.
- **Token bucket en Redis con script Lua** — descartada por ahora: más exacto, más superficie
  (un script que mantener y versionar) para un beneficio que a 120 rpm no se nota.

## Sources
`teleflow/gateway/main.py:64-101,194-210` · `teleflow/common/config.py:26,74` ·
`helm/teleflow/values.yaml:26-30` · `teleflow/executor_service/engine.py:86-97` (pub/sub ya en
uso) · [[backlog-hardening]] (ítem 3) · [[seguridad-api-keys]] ·
[[2026-06-30-adr-002-durable-sleep]] · [[fallas-silenciosas]]
