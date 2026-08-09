# Runbooks de operación — TeleFlow

Qué hacer cuando algo suena. Pensado para quien está de guardia y **no** escribió el sistema.

Todos los comandos de esta página se ejecutaron contra el stack real. Lo que no se probó está
marcado como **no probado** en vez de omitido: un runbook que mezcla pasos verificados con
suposiciones sin distinguirlos es peor que uno corto, porque a las 3 AM no hay forma de saber
cuál es cuál.

Los ejemplos usan `docker compose`. En Kubernetes el equivalente es `kubectl exec -n <ns>
<pod> -- <mismo comando>`.

---

## Antes que nada: los tres puertos que no son los que parecen

| Servicio | Puerto interno | En el host |
|---|---|---|
| Prometheus | 9090 | **9091** |
| Grafana | 3000 | **3001** |
| RabbitMQ (AMQP) | 5672 | **no se publica** |
| metrics-service | 8005 | **no se publica** |

Los dos últimos no son un olvido: no hace falta que estén expuestos. La consecuencia práctica es
que a RabbitMQ y a `/metrics` **se les entra desde adentro** (`docker compose exec`), y que la
foto del estado se mira por Prometheus, que sí está publicado.

---

## Alerta: `TeleFlowServicioCaido`

**Qué significa.** Un target de TeleFlow no responde al scrape hace 2 minutos.

**Qué NO significa.** Que el sistema esté caído. Los servicios sin estado corren con 2-3
réplicas: puede haber una sola caída y el usuario no notar nada.

**Confirmar:**

```bash
curl -s "localhost:9091/api/v1/query?query=up==0"     # qué target, exactamente
docker compose ps                                      # qué contenedor no está Up
docker compose logs --tail=100 <servicio>
```

**Qué hacer.** Si el contenedor está caído o reiniciando, los logs dicen por qué antes de tocar
nada. Dos causas ya vistas en este repo:

- **El servicio no arranca porque le falta el schema.** Los servicios consultan tablas al
  iniciar; si las migraciones no llegaron, revientan en el arranque. Ver `alembic current` — si
  no dice `(head)`, el problema es la migración, no el servicio.
- **Falta configuración obligatoria.** El composer no arranca sin proveedor real configurado, a
  propósito: es preferible que no levante a que conteste borradores falsos.

---

## Alerta: `TeleFlowMetricasDeNegocioCongeladas`

**La más importante de las tres, y la menos obvia.**

**Qué significa.** Los gauges de negocio llevan más de 3 minutos sin refrescarse. El pod está
**vivo**, `/metrics` responde y `up` vale 1 — pero los números que muestra son viejos.

**Qué NO significa.** Que el negocio esté parado. Significa que **dejamos de saberlo**. Un
backlog congelado en 10 se ve exactamente igual que un backlog estable de 10: los paneles siguen
mostrando números plausibles. Por eso existe esta alerta.

**Confirmar** — la antigüedad real, en segundos:

```bash
curl -s "localhost:9091/api/v1/query?query=time()-teleflow_business_metrics_last_success_timestamp_seconds"
```

En un sistema sano da decenas de segundos (el refresh es periódico). Si da cientos o miles, está
congelado. El acompañante dice **por qué**:

```bash
curl -s "localhost:9091/api/v1/query?query=teleflow_business_metrics_refresh_failures_total"
```

- **Sube** → el colector está corriendo y **falla** al leer la base. Mirar Postgres.
- **Quieto en 0 y la antigüedad crece** → el colector no está corriendo. Mirar el pod.

```bash
docker compose logs --tail=100 metrics-service
```

**Qué hacer.** Casi siempre el problema es Postgres (inalcanzable, sin conexiones libres,
caído), no el metrics-service: el colector atrapa el error y sigue **a propósito**, porque un
fallo de métricas no debe bajar un servicio. Esa decisión es la que produce el silencio, y esta
alerta es su contrapeso.

Ojo: `metrics-service` corre en **una sola réplica** por diseño. No tiene quien lo reemplace.

---

## Alerta: `TeleFlowSinPublicadorDeMetricasDeNegocio`

**Qué significa.** No existe la serie de frescura hace más de 5 minutos: nadie está publicando
métricas de negocio.

**Diferencia con la anterior:** aquella dice "el publicador está y se atrasó"; esta dice "no hay
publicador". Suele ser un despliegue donde `metrics-service` no se levantó, o un scrape mal
configurado (el target no existe para Prometheus).

**Confirmar:**

```bash
curl -s "localhost:9091/api/v1/targets" | head -c 2000    # ¿aparece metrics-service?
docker compose ps metrics-service
```

---

## La DLQ: eventos que fallaron y nadie procesó

Los eventos que agotan sus reintentos van a `teleflow.rules.v2.dlq`. **Que la DLQ tenga 0 no
siempre significa que no hubo fallas** — significa que no hay nada ahí *ahora*.

**Mirar:**

```bash
docker compose exec -T rabbitmq rabbitmqctl list_queues name messages
```

Salida real de un sistema sano (las `v1` son de antes de la migración a colas quorum):

```
teleflow.rules.v2        0
teleflow.rules.v2.dlq    0
teleflow.rules.v1        0
teleflow.rules.v1.dlq    0
```

**Leer un mensaje sin consumirlo** (`ackmode=reject_requeue_true` lo devuelve a la cola):

```bash
docker compose exec -T rabbitmq rabbitmqadmin -u teleflow -p teleflow \
  get queue=teleflow.rules.v2.dlq count=5 ackmode=reject_requeue_true
```

Cada mensaje trae un header `x-death` con cuántas veces se intentó y por qué murió: eso es lo
que dice si el fallo fue transitorio (y conviene reprocesar) o permanente (y reprocesar solo lo
va a mandar de vuelta a la DLQ).

**Reprocesar:** hoy **no hay un comando hecho** para devolver mensajes de la DLQ a la cola
principal. **No probado** — el camino sería republicar el body al exchange
`teleflow.domain.events`. Antes de hacerlo hay que entender por qué falló, o se repite el ciclo.

---

## Disaster recovery: restaurar la base

**Qué se respalda y qué no.** Solo Postgres. Es el único estado que el producto no puede
reconstruir: Redis es cache y coordinación, los dashboards viven en la imagen, y las colas son
trabajo en vuelo, no un registro.

**Consecuencia directa, y hay que decirla en voz alta:** un restore **no recupera los eventos en
vuelo** que estaban en RabbitMQ ni lo que hubiera en la DLQ. Recupera expedientes, entidades,
flows registrados, keys y auditoría.

**Respaldar** (con la base arriba — `pg_dump` toma una instantánea consistente sin bloquear
escrituras, así que no hace falta ventana de mantenimiento):

```bash
scripts/backup.sh
# -> backups/teleflow-20260808-211521.dump (416 KB)
```

**Restaurar — primero a una base de prueba, siempre:**

```bash
scripts/restore.sh backups/teleflow-20260808-211521.dump teleflow_verificacion
```

Recién con eso verde, sobre la base real:

```bash
scripts/restore.sh backups/teleflow-....dump teleflow --confirmar
```

El `--confirmar` es obligatorio a propósito: pisar la base real no puede ser un typo.

**Orden para levantar desde cero:**

1. Postgres arriba y `healthy`.
2. Restaurar el dump.
3. `alembic upgrade head` — el dump trae el schema de **su** momento; si el código es más nuevo,
   faltan migraciones.
4. El resto de los servicios. Cada uno espera a su schema antes de arrancar, así que si algo
   quedó a medias los pods no levantan en vez de correr contra una base incompleta.

**Verificar que la restauración sirvió** — no que el comando salió con 0:

```bash
docker compose exec -T postgres psql -U teleflow -d teleflow \
  -c "select count(*) from process_instances;" \
  -c "select count(*) from flow_definitions;" \
  -c "select count(*) from audit_log;"
```

Los tres tienen que dar números coherentes con lo que había antes del incidente. `audit_log` es
el que más sirve para fechar hasta dónde llegó la restauración: su última fila dice qué momento
recuperaste.

---

## Un nodo de RabbitMQ caído (Kubernetes)

Con el cluster de 3 nodos y colas quorum, perder un nodo **no pierde mensajes**: está medido —
matando el nodo que aloja la cola, una cola clásica pierde el mensaje y la quorum lo conserva,
con el líder migrando solo.

```bash
kubectl exec <pod-rabbitmq> -- rabbitmqctl cluster_status
kubectl exec <pod-rabbitmq> -- rabbitmqadmin -u teleflow -p teleflow list queues name type messages
```

Lo que hay que mirar es que la cola diga `quorum` y no `classic`, y que el nodo que volvió
aparezca en *Running Nodes*. Un nodo que vuelve y no encuentra a los demás **no arranca solo** a
propósito (`cluster_partition_handling = pause_minority`): es preferible que espere a que se
formen dos clusters que se creen ambos el bueno.

**No probado:** perder una **máquina** entera. Lo verificado fue en un cluster de un solo nodo,
así que prueba el consenso de RabbitMQ, no la tolerancia a que se caiga un servidor.
