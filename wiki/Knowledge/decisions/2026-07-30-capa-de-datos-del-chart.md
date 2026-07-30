---
project: copp-ia
date: 2026-07-30
status: accepted
provenance: copp-ia@devyos@54f3f23 (+ cambios del chart sin commitear, work-stream fase-e-helm-kind)
tags: [adr, fase-e, helm, kubernetes, postgres, redis, rabbitmq, cadena-de-suministro, despliegue]
---

# ADR (wiki): de dónde salen Postgres, Redis y RabbitMQ en el chart de Helm

> Decisión abierta durante el work-stream [[fase-e-helm-kind]] (Fase E). **No** es un ADR del
> arquitecto (los suyos son ADR-001..005): es una decisión del equipo sobre el despliegue.
> **Aceptado por el owner el 2026-07-30.** Se escribió en `proposed` porque una de las tres
> opciones cuesta dinero y otra cuesta trabajo, y ese balance no lo decidía la evidencia técnica.

## Context
El chart declara los tres servicios de datos como subcharts de Bitnami (`Chart.yaml`:
`postgresql 15.x`, `redis 19.x`, `rabbitmq 14.x`, desde `charts.bitnami.com/bitnami`). Nunca
se había instalado. Al hacerlo por primera vez apareció esto:

```
bitnami/postgresql:16.4.0-debian-12-r14  -> no such manifest
bitnami/redis:7.2.5-debian-12-r4         -> no such manifest
bitnami/rabbitmq:3.13.7-debian-12-r2     -> no such manifest
bitnamilegacy/postgresql:16.4.0-debian-12-r14  -> OK  (idem redis y rabbitmq)
```

**El chart no se puede instalar tal como está.** `helm dependency update` funciona —los charts
siguen publicados y `Chart.lock` se genera bien— y el fallo recién aparece cuando un pod intenta
bajar la imagen. Ni `helm template` ni un lint lo detectan.

Es la variante más limpia de [[fallas-silenciosas]] vista hasta ahora, y trae una forma nueva:
**el artefacto no cambió y dejó de funcionar solo.** Todos los casos anteriores del catálogo
eran código nuestro que ocultaba un fallo; este es una dependencia externa que se movió debajo.

Tres hechos más, que salieron de mirar la doc y el compose:

1. **La doc de arquitectura no menciona Bitnami.** `grep -rni bitnami docs/` → cero. La doc pide
   "StatefulSets para Postgres, Redis y RabbitMQ" (`docs/teleflow-deployment.typ:61`) y da
   réplicas y notas de HA (§10.2: patroni, Sentinel, quorum queues) sin decir de dónde salen las
   imágenes. **Elegir Bitnami fue una decisión del chart, sin respaldo en la arquitectura ni ADR.**
2. **El compose usa las imágenes oficiales**: `postgres:16-alpine`, `redis:7-alpine`,
   `rabbitmq:3.13-management-alpine` (`docker-compose.yml:30,44,52`). O sea **dev/CI y producción
   no comparten la capa de datos**: lo que prueban los 22 e2e y el job e2e de CI no es lo que se
   despliega en un organismo.
3. **Los StatefulSets que la doc pide existen hoy solo porque los subcharts los traen.**
   `helm template` renderiza los 6 servicios propios como Deployments y
   `teleflow-postgresql` / `teleflow-rabbitmq` / `teleflow-redis-master` como StatefulSets, todos
   aportados por Bitnami. Irse de Bitnami implica escribirlos.

Contexto de producto que pesa: TeleFlow se instancia **por organismo**
([[2026-06-30-adr-005-aislamiento-instancia]]), varios de ellos públicos. La procedencia y el
soporte de las imágenes de la base de datos no es un detalle de empaquetado.

## Decision
**Alinear el chart con las imágenes oficiales que ya usa el `docker-compose.yml`**, escribiendo
los tres StatefulSets en el propio chart y sacando los tres subcharts de Bitnami.

Mientras se implementa, el desbloqueo transitorio es `bitnamilegacy/*` **por `--set` o por un
values de scratchpad, nunca en `values.yaml`**, para que la deuda no se convierta en el default
del producto. Así se hizo en el Chunk 1 del work-stream.

La decisión **no** incluye el HA de la capa de datos (patroni / Sentinel / quorum queues, §10.2).
Eso es un ítem aparte de Fase E: acá se decide **de dónde salen las imágenes y quién declara los
StatefulSets**, no cuántos nodos tiene cada uno.

## Rationale
- **Borra la divergencia dev/prod, que es el problema de fondo.** El síntoma que forzó este ADR
  fue de cadena de suministro, pero lo que apareció al investigarlo es peor y es permanente: los
  e2e prueban `postgres:16-alpine` y el organismo corre otra cosa. Cualquier defecto que dependa
  de la capa de datos no reproduce en local, y encima nadie lo sospecha porque "los e2e pasan".
  Ninguna de las otras dos opciones arregla esto.
- **No contradice la doc.** La doc pide StatefulSets, no Bitnami. Cumplirla escribiéndolos
  nosotros es tan válido como heredarlos, y encima deja explícito en el repo lo que hoy es un
  efecto secundario de una dependencia.
- **`bitnamilegacy` es un destino inaceptable, no una alternativa.** Está congelado: no recibe
  parches de seguridad. Poner eso en la base de datos de un organismo público es difícil de
  defender ante cualquier revisión, y sería exactamente la clase de decisión que este proyecto
  viene evitando escribir como "límite conocido" para no decidirla.
- **Baja el acoplamiento a una política de distribución de terceros.** Ya nos movió el piso una
  vez sin aviso; las imágenes oficiales de Postgres/Redis/RabbitMQ tienen otro tipo de
  compromiso de continuidad. `(inferencia)`
- **El costo es acotado y conocido.** Tres StatefulSets + sus Services + PVCs, con la
  configuración que el chart ya declara (usuarios, passwords, `architecture: standalone`). El
  chart ya renderiza 6 Deployments desde una plantilla con `range`, así que el patrón está.
- **Contra:** perdemos lo que los subcharts de Bitnami traen gratis y que nadie había pedido pero
  ya estaba renderizando — NetworkPolicies, PodDisruptionBudgets, ServiceAccounts, los
  ConfigMaps de health de Redis y el endpoint-reader RBAC de RabbitMQ. Hay que decidir cuáles de
  esos vale reescribir. Es trabajo real y hay que contarlo.

## Consequences
- **El chart deja de tener dependencias**: `Chart.lock` y `helm/teleflow/charts/` desaparecen, y
  con ellos el paso `helm dependency update` que documenta el `README.md:248`. Un clon del repo
  pasa a instalar con un solo comando.
- **Los 22 e2e y el job e2e de CI pasan a probar la misma capa de datos que producción.** Es el
  beneficio grande y no requiere tests nuevos: los que hay dejan de mentir por omisión.
- **Hay que reescribir a mano lo que Bitnami daba de arriba** (ver el "Contra"). Lo que no se
  reescriba, se pierde — y conviene anotar explícitamente qué se decidió no traer, para que no
  quede como un hueco silencioso.
- **La migración de una instalación existente no es trivial** `(inferencia)`: cambiar el
  StatefulSet que administra un PVC con datos no es un `helm upgrade` cualquiera. Hoy no hay
  ninguna instalación productiva, así que la ventana para hacerlo barato es **ahora**. Es el mismo
  argumento de costo que cerró [[2026-07-25-idempotencia-execute]]: bajo ahora, alto después.
- **Los passwords de Postgres y RabbitMQ siguen viajando en `values` en texto plano.** Este ADR
  no lo arregla; queda para el ítem de secrets de Fase E (`roadmap.md:117`), y ahora que el chart
  crea Secrets ([[fase-e-helm-kind]], Chunk 1) hay dónde apoyarlo.
- **Regla que sale de acá, aplicable más allá de Helm:** una dependencia externa puede romper un
  artefacto que nadie tocó, y ni los tests ni el lint lo ven porque el fallo ocurre al
  desplegar. Vale que algo del pipeline verifique que las imágenes referenciadas **existen**, no
  solo que los manifiestos son válidos.

## Alternatives
- **Quedarse en `bitnamilegacy/*`, fijado en `values.yaml`** — descartada. Es la opción de cero
  trabajo hoy, y consiste en fijar por escrito imágenes de base de datos sin parches de
  seguridad para instalaciones de organismos públicos. Tampoco arregla la divergencia con el
  compose, así que paga el costo de decidir sin cobrar el beneficio.
- **Bitnami Secure Images (la continuación comercial)** — descartada como recomendación, no como
  imposibilidad. Es la opción de menor trabajo técnico —los subcharts siguen sirviendo— pero
  cuesta dinero, ata cada organismo a una suscripción de un tercero para poder instalar el
  producto, y **sigue sin arreglar la divergencia con el compose**. Si el owner prefiere esta,
  la divergencia dev/prod queda abierta como ítem propio.
- **Otros charts mantenidos por la comunidad** (CloudNativePG para Postgres, el operator de
  RabbitMQ) — descartada por ahora. Son mejores que un StatefulSet nuestro en HA y en
  operación, pero sustituyen una dependencia externa por otra y suman un operator al stack de
  cada organismo. Vale reconsiderarlos cuando se aborde el HA de §10.2, que es su terreno.
- **Asumir que la base es externa** (`postgresql.enabled=false` + `externalDatabase.host`, que el
  chart ya soporta desde el Chunk 1) y que cada organismo trae la suya — descartada como default.
  Es razonable para un organismo con DBAs, y por eso el gancho queda; pero como única opción
  contradice el modelo de "se instala por organismo" y deja al chart sin un camino que funcione
  solo.

## Sources
`helm/teleflow/Chart.yaml` · `helm/teleflow/Chart.lock` · `docker-compose.yml:30,44,52` ·
`docs/teleflow-deployment.typ:61,71-84` · `README.md:248` · `roadmap.md:116-122` ·
[[fase-e-helm-kind]] (hallazgo 7) · [[fallas-silenciosas]] ·
[[2026-06-30-adr-005-aislamiento-instancia]] · [[2026-07-25-idempotencia-execute]]
