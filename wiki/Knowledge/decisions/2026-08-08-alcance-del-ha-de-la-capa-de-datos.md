---
project: copp-ia
date: 2026-08-08
status: proposed
provenance: copp-ia@devyos@84a4f4f
tags: [adr, fase-e, ha, disponibilidad, rabbitmq, postgres, redis, kubernetes, helm]
---

# ADR (wiki): hasta dónde llega el HA de la capa de datos que entrega la plataforma

> Sale del work-stream [[ha-capa-de-datos]] (Fase E). **Complementa
> [[2026-07-30-capa-de-datos-del-chart]]**, que decidió de dónde salen las imágenes y quién
> declara los StatefulSets, y que dejó explícitamente afuera cuántos nodos tiene cada uno.
> Se escribe en `proposed` porque **contradice la lectura literal de §10.2** del documento de
> arquitectura: eso lo confirma el owner, no la evidencia técnica.

## Context

`docs/teleflow-deployment.typ:80-82` (§10.2, "Réplicas recomendadas en producción") pide para la
capa de datos:

| Servicio | Réplicas mínimas | Nota de la doc |
|---|---|---|
| postgres | `1+` | "PVC dedicado. Recomendado: HA con patroni" |
| redis | `1` | "Sentinel para HA en prod" |
| rabbitmq | `3` | "Cluster quorum queue recomendado" |

Estado real en `copp-ia@devyos@84a4f4f`: los tres StatefulSets están en `replicas: 1`
(`helm/teleflow/templates/datos.yaml:44,133,203`), el Service de RabbitMQ es `ClusterIP` y **no
headless** y no hay erlang cookie ni peer discovery (`datos.yaml:167-180`), las colas se declaran
**clásicas** —`durable=True` + DLX, sin `x-queue-type`— (`executor_service/events.py:112-118`), y
el cliente de Redis es `aioredis.from_url()`, que **no habla Sentinel**
(`gateway/main.py:57`).

Tres hechos más, que son los que mueven la decisión:

1. **El tipo de cola lo declara la aplicación, no el operador.** Un organismo que traiga un
   RabbitMQ administrado en cluster **sigue sin HA de la cola** mientras `events.py` la declare
   clásica: la cola vive en un nodo. Es lo único de los tres que nadie puede arreglar desde
   afuera. Y ahí vive la DLQ, o sea la garantía construida en `resiliencia-executor` y
   `estado-durable`.
2. **El chart ya tiene un camino externo, a medio abrir.** `enabled: false` +
   `external*.host` (`values.yaml:31-36`) es **solo un hostname**: sin puerto, sin TLS, sin
   credenciales por `existingSecret`. Un organismo con una base administrada —que ya tiene HA
   real, con guardia que la opera— hoy entra por una puerta angosta.
3. **Lo que Redis guarda no es estado de negocio**: contadores de rate limit, el pub/sub de
   revocación de keys (`gateway/main.py:293`) y estado compartido del gateway. Perderlo
   **degrada**; el durable sleep vive en Postgres (ADR-002).

## Decision

La plataforma entrega HA **donde solo ella puede hacerlo**, y hace de primera clase el camino
para apoyarse en el HA que el organismo ya opera. En concreto:

- **RabbitMQ: sí.** Cluster de 3 con **quorum queues**, declaradas así por el código.
- **Postgres: no se escribe un patroni casero.** Se completa el camino externo (puerto, TLS,
  credenciales por Secret, validación que falle diciendo qué falta) y se documenta la
  recomendación operativa. El StatefulSet de una réplica sigue siendo el default de
  desarrollo/instalación chica.
- **Redis: se queda en una réplica**, documentado como límite consciente.

**Criterio que ordena todo lo anterior: solo entra el HA que se pueda probar rompiéndolo.**

## Rationale

- **Un HA que no se puede demostrar fallando no es una garantía, es la próxima falla
  silenciosa.** Este repo lleva quince casos de mecanismos que *parecían* proteger
  ([[fallas-silenciosas]]). Un cluster de RabbitMQ se prueba en kind borrando el pod líder con un
  mensaje en vuelo. Un patroni escrito a mano —DCS, elección de líder, failover, promoción,
  fencing— no se prueba con honestidad en kind ni en un e2e de CI: entregaríamos un `replicas: 3`
  que se lee como HA y del que no podríamos afirmar que promociona bien bajo partición.
- **El tipo de cola es nuestro, el failover de Postgres es del operador.** Es la asimetría clave
  y la que decide el reparto: hay una parte del HA de RabbitMQ que **ningún** organismo puede
  aportar por más que administre su propio broker, y no hay ninguna parte del HA de Postgres que
  solo nosotros podamos aportar.
- **Coherente con ADR-005 (instancia por organismo).** El producto se instala en organismos que
  suelen tener base administrada y gente que la opera. Competir contra eso con manifiestos
  propios agrega superficie sin agregar disponibilidad.
- **El costo no es simétrico.** Cluster de RabbitMQ: Service headless, cookie por Secret, peer
  discovery, PVC por pod, y del lado del código un argumento en la declaración más una cola
  nueva. Patroni: un componente de operación permanente que este equipo no opera.
- **La deuda queda nombrada, no escondida.** El error que el ADR del 30/07 marcó fue no anotar
  lo que se perdía al salir de Bitnami. Acá se anota de entrada: Postgres y Redis quedan en una
  réplica y eso **es** un punto único de fallo ([[supuesto-de-proceso-unico]]).

## Consequences

- **La DLQ y los eventos de rules dejan de depender de un pod.** Es el beneficio concreto.
- **Hay migración de colas, y es obligatoria**: los argumentos de una cola son **inmutables**
  (gotcha ya pagado en `resiliencia-executor`), así que la cola pasa a `teleflow.rules.v2`. Sale
  barato porque el nombre ya es configurable y versionado (`common/config.py:68`).
- **La instalación default deja de ser la de producción en un punto**: 3 nodos de RabbitMQ pesan
  más que uno. Hay que decidir si el default del chart es 1 o 3 `(inferencia: probablemente 3 en
  el chart y 1 por values de desarrollo, para que producción no dependa de acordarse)`.
- **`docs/teleflow-deployment.typ` §10.2 queda contradicha en un punto** (patroni) y hay que
  anotarlo en la tabla de discrepancias doc-vs-código del README, que existe justamente para esto.
- **Postgres y Redis siguen siendo punto único de fallo** en la instalación default. Escrito acá
  para que sea una decisión y no un hueco.
- **No cierra el ítem de secrets de Fase E**, pero lo empuja: el camino externo necesita
  `existingSecret`, que es la misma pieza que ese ítem necesita.

## Alternatives

- **Los tres con HA propio en el chart (§10.2 literal)** — descartada por lo de arriba: el
  componente más caro es el que menos podemos probar y el que más organismos ya tienen resuelto.
  Reconsiderable si aparece un organismo sin base administrada y con exigencia de RPO/RTO.
- **Un operator de terceros para Postgres** (CloudNativePG, Zalando) — no descartada, **diferida**.
  Resuelve el failover con algo probado en vez de casero, pero mete una dependencia de CRDs y de
  su ciclo de vida en cada organismo, y el proyecto acaba de salir de una dependencia externa que
  le movió el piso ([[2026-07-30-capa-de-datos-del-chart]]). Es la primera alternativa a mirar si
  esta decisión se revisa.
- **No hacer nada y documentar todo como límite** — descartada. Deja la DLQ, que es una garantía
  que el producto **afirma** tener, apoyada en un solo pod.
- **Solo RabbitMQ, sin tocar el camino externo** — descartada por poco: el camino externo es
  barato y es lo único que le da HA de Postgres a un organismo **hoy**.

## Sources

- `docs/teleflow-deployment.typ:68-83` (§10.2) · [[roadmap]] Fase E.
- [[2026-07-30-capa-de-datos-del-chart]] (excluye HA explícitamente) · ADR-002 · ADR-005.
- [[fallas-silenciosas]] · [[supuesto-de-proceso-unico]].
- `copp-ia@devyos@84a4f4f`: `helm/teleflow/templates/datos.yaml`, `helm/teleflow/values.yaml`,
  `teleflow/executor_service/events.py`, `teleflow/common/config.py`, `teleflow/gateway/main.py`.
- Work-stream [[ha-capa-de-datos]].
