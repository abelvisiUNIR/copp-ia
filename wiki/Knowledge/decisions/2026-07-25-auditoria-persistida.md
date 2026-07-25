---
project: copp-ia
date: 2026-07-25
status: accepted
provenance: copp-ia@devyos@8699d65
tags: [adr, gateway, auditoria, seguridad, trazabilidad]
---

# ADR (wiki): qué se audita, qué se guarda y dónde se escribe

> Provenance: `copp-ia@devyos@8699d65`. Decisión tomada al abrir el work-stream
> [[auditoria-persistida]]. **No** es un ADR del arquitecto (los suyos son ADR-001..005).
> Las decisiones 1 y 2 dependían del criterio de negocio del owner: **confirmadas el
> 2026-07-25** tal como se recomiendan acá (no auditar lecturas exitosas, no guardar el
> cuerpo). Si el marco del organismo cambia, los dos puntos están acotados a propósito.

## Context
El gateway sabe **quién** es cada request (`Identidad(name, scopes, key_id)`,
`auth.py:82-88`, dejada en `request.state.identidad` por el middleware, `main.py:97`) y sabe
**qué** intenta hacer (24 rutas declaran su scope con `Depends(auth.require(...))`). Esa
información se usa para autorizar y después se tira: lo único que queda es una línea de log
(`auth.py:81`: "`name` va a los logs").

De las 12 tablas del schema, ninguna es de auditoría — y sin embargo el diseño **ya la
anticipa**: al revocar una key, la fila no se borra "porque la identidad se conserva para la
auditoría" (`main.py:252`). La intención está escrita; el registro no existe.

Un `POST /flows/{name}` despliega código ejecutable en el organismo. Hoy, si alguien pregunta
"¿quién publicó la versión 1.4.0 del flow de altas y cuándo?", la respuesta depende de que
los logs de ese día no hayan rotado.

## Decision

### 1. Se audita toda acción de escritura, y **todo intento denegado**
- **Sí:** las acciones cubiertas por los 7 scopes de escritura — `flows:deploy`,
  `instances:trigger`, `instances:signal`, `instances:retry`, `entities:write`,
  `compose:write`, `keys:admin`.
- **Sí, siempre:** cualquier request que termine en **401 o 403**, sea de lectura o de
  escritura. Un intento fallido de desplegar es exactamente lo que una auditoría tiene que
  mostrar, y es la señal más barata de una credencial filtrada.
- **No:** las lecturas que salen bien (`flows:read`, `instances:read`, `entities:read`,
  `compose:read`). Son la mayoría del tráfico y su valor de auditoría es bajo.

> **Qué revisar si cambia el marco.** Si el organismo exige registrar también los **accesos a
> datos personales** (una vista 360 es exactamente eso), hay que sumar `entities:read` a la
> lista: un cambio de una línea en el código y de un orden de magnitud en el volumen de la
> tabla. Se empieza sin él justamente porque agregarlo es fácil y sacarlo después no devuelve
> el espacio.

### 2. No se guarda el cuerpo del request
Se guarda **quién, qué, sobre qué, cuándo y con qué resultado**:
`actor_name`, `actor_key_id`, `scope`, `method`, `path`, `operation_id`, `status_code`,
`occurred_at`, y un `subject` (el identificador del recurso que ya viaja en la ruta: nombre
del flow, `instance_id`, nombre de la entidad).

**El cuerpo no.** Por ahí pasan datos personales de ciudadanos, y una tabla de auditoría es
justamente la que más tiempo se conserva y más gente puede leer. Para el caso donde el cuerpo
importa de verdad —el deploy— se guarda el **checksum del source**, que el parser ya calcula
(`parser_service/main.py:44`) y que permite responder "¿esta versión es la que se publicó?"
sin almacenar el código.

> **Qué revisar si cambia el marco.** Si hiciera falta reconstruir *qué decía* un pedido y no
> solo que ocurrió, la alternativa es guardar el cuerpo con los campos sensibles enmascarados.
> Es bastante más trabajo y exige mantener una lista de campos a enmascarar que se
> desactualiza en silencio ([[fallas-silenciosas]]). No se hace sin un requisito concreto.

### 3. Se escribe en el gateway, después de la respuesta, en su propia transacción
El gateway es el único lugar por el que pasan todas las acciones, y es donde ya está resuelta
la identidad. Se escribe **después** de conocer el `status_code` (una auditoría sin resultado
sirve la mitad) y en una transacción propia: el gateway proxea a otros servicios y no comparte
transacción con ellos, así que "misma transacción que la acción" no es una opción disponible.

**El registro no se pierde en silencio.** Si la escritura falla: `log.error` + el contador
Prometheus `teleflow_audit_write_failures_total`, que es la señal alertable. La acción ya
ocurrió y no se puede deshacer, así que abortar el request no arregla nada — pero un organismo
que se quedó sin auditoría tiene que verlo en el dashboard, no descubrirlo cuando alguien
pregunta por un deploy.

> **Ajustado al implementar.** El borrador de este ADR decía que `/ready` pasaría a
> "degradado" ante un fallo de escritura. No se hizo así: `/ready` es binario y devolver 503
> saca al gateway de rotación, o sea que un problema de auditoría cortaría **todo** el
> servicio — una decisión de disponibilidad mucho más grande que la que este ADR discute. En
> cambio se descubrió que **el gateway no tenía readiness real** (`setup_observability` sin
> `ready_check`), pese a que sin Postgres no puede resolver ninguna key de la tabla `api_keys`
> ni escribir auditoría. Ahora `/ready` hace `db_ping`, que cubre el caso que importa (base
> caída → no listo) sin acoplar disponibilidad a un fallo puntual de escritura.

> **Límite consciente.** Esto es auditoría *best-effort en el margen*: si el proceso muere
> entre la acción y la escritura, esa acción no queda registrada. Para auditoría garantizada
> haría falta escritura en dos fases (intención antes, resultado después), que duplica las
> filas y agrega latencia a cada request. No se hace ahora; queda anotado por si el marco del
> organismo lo exige.

### 4. Append-only, consultable con un scope nuevo, sin purga automática
- Tabla `audit_log` **append-only**: sin `UPDATE` ni `DELETE` desde la API, mismo patrón que
  `instance_transitions` y `entity_events`.
- `GET /audit` con filtros por actor, scope, subject y rango de fechas, detrás de un scope
  nuevo **`audit:read`**, que **no** entra en el comodín por defecto de ninguna key existente
  salvo la global (que ya es `*`).
- **Sin purga automática.** La retención es política del organismo y borrar auditoría por un
  default nuestro es peor que la tabla creciendo. Se documenta que crece y se deja el borrado
  como tarea explícita del operador.

### 5. El registro se engancha donde no se pueda olvidar
La escritura **no** va ruta por ruta. `auth.require(...)` ya sabe qué scope exige cada ruta:
se lo hace anotar en `request.state`, y un único middleware escribe el registro con esa
información. Así, **una ruta nueva con scope de escritura queda auditada sin que su autor
haga nada**, y un test fija que ninguna ruta con scope de escritura pueda quedar afuera.

Auditar ruta por ruta sería una lista que alguien olvida actualizar, y el olvido no haría
ruido: sería una falla silenciosa en la capa de garantías, que es el peor lugar
([[fallas-silenciosas]]).

## Rationale
- **La taxonomía ya está hecha y curada.** Los 11 scopes salieron de `seguridad-api-keys`
  separando "lo que un tercero podría necesitar por separado" (`auth.py:23-25`). Inventar una
  segunda taxonomía de acciones para auditar sería la misma decisión tomada dos veces, con dos
  lugares donde puede divergir — el error que ya evitamos extrayendo `common/retry.py`.
- **Auditar los denegados es más barato que detectarlos de otro modo.** Sin esto, una key
  filtrada probando permisos solo deja rastro en logs.
- **No guardar el cuerpo es una decisión de privacidad, no de espacio.** La tabla que más se
  conserva no puede ser la que más datos personales acumula.
- **Enganchar en `require` en vez de en cada ruta** convierte la cobertura en estructural: no
  depende de que nadie se olvide.

## Consequences
- **Migración `0004`** — tercera desde el schema inicial.
- **Una tabla que crece sin techo.** Es deliberado (ver decisión 4), pero hay que decirlo en
  el README: un organismo con mucho tráfico de escritura va a querer una política de archivado.
- **`audit:read` es un scope nuevo**, así que `ALL_SCOPES` cambia y las keys con `*` lo
  reciben automáticamente. Las keys con scopes explícitos **no** — es lo correcto: leer la
  auditoría es un permiso que se otorga, no que se hereda.
- **`/ready` del gateway ahora depende de Postgres.** Es un cambio de comportamiento: antes
  respondía "listo" siempre, incluso con la base caída (cuando no podía resolver ninguna key
  de `api_keys`). **El orquestador concreto es el Helm chart**, que usa `/ready` como
  `readinessProbe` de todos los servicios (`helm/teleflow/templates/deployments.yaml:38-41`):
  en k8s, con Postgres caído los pods del gateway salen de rotación y el Service se queda sin
  endpoints, o sea que la API pasa de devolver 401 a no responder. Es la semántica correcta
  —sin base el gateway solo puede atender la key de bootstrap— pero conviene saberlo antes de
  la Fase E, que es cuando el chart se prueba de verdad (`roadmap.md:110`).
- **El middleware toca todos los requests.** Es un `INSERT` por acción de escritura; las
  lecturas exitosas no escriben nada, que es la mayoría del tráfico.

## Alternatives
- **Enviar la auditoría al bus de eventos y que la escriba un consumidor** — descartada por
  ahora: desacopla bien, pero agrega un modo de fallo (evento perdido) justo en el mecanismo
  cuyo valor es no perder nada. Reconsiderable si el `INSERT` sincrónico se vuelve un problema
  de latencia medido, no supuesto.
- **Auditar en cada servicio en vez de en el gateway** — descartada: la identidad se resuelve
  en el gateway y los servicios internos no la reciben. Auditar en cada uno exigiría propagar
  la identidad por todas las llamadas internas, que es un cambio mucho más grande.
- **Usar los logs estructurados como auditoría** (structlog ya emite JSON con el actor) —
  descartada: no es consultable sin un stack de logs que hoy no existe, y la retención
  quedaría atada a la rotación de archivos. Es exactamente la situación actual.
- **Guardar el cuerpo completo del request** — descartada salvo requisito explícito (ver
  decisión 2).

## Sources
`teleflow/gateway/auth.py:23-48,81-88,116-138` · `teleflow/gateway/main.py:34,80-97,252,329` ·
`teleflow/common/models.py` (12 tablas, ninguna de auditoría; `instance_transitions.actor_id`
como patrón) · `teleflow/parser_service/main.py:44` (checksum) ·
[[backlog-hardening]] (ítem 1) · [[seguridad-api-keys]] · [[fallas-silenciosas]] ·
[[2026-06-30-adr-005-aislamiento-instancia]]
