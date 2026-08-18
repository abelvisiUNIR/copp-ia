---
project: copp-ia
date: 2026-08-18
status: accepted
---

# Con qué señal escala el executor, y por qué el HPA viene apagado

## Context

Fase E cerró todo menos el HPA del executor, y el roadmap ya lo marcaba como su ítem más débil:
no hay instalación productiva ni problema de capacidad medido, y la señal obvia —CPU— es
sospechosa en un servicio I/O-bound. El orden que fijó el propio roadmap fue **medir antes de
construir**.

El chart no tenía ningún HorizontalPodAutoscaler y las réplicas eran fijas
(`executor-service.replicas: 3`). El request declarado es `cpu: 100m`, sin límite de CPU.

Lo que se midió, contra el stack real, con un flow sonda de un solo step `automated` contra un
endpoint que tarda 1 s (I/O puro) y `docker stats` calibrado antes (un core ocupado marca
~103 %, así que el request de 100 m son 10 %):

- **El techo no es la CPU: es un semáforo.** `asyncio.Semaphore(worker_concurrency)`, 10 por
  réplica. De n=10 a n=400 la concurrencia real que llega a la integración se clava en **10**,
  el throughput satura en ~8/s y el resto espera. Confirmado también contra la base:
  `IN_PROGRESS` fijo en 10 mientras `TRIGGERED` drenaba 329 → 271 → 211.
- **La CPU es sorda donde importa.** Entre n=100 y n=400 —mismo throughput saturado, 4× de
  backlog, 4× de espera (12 s → 48 s)— la CPU pasó de **296 m a 351 m: +19 %**.
- **Y sensible donde no importa.** Con n=5, a media capacidad y sin nadie esperando, el pico ya
  tocaba 94 m ≈ **94 % del request de 100 m**.
- **Además son ráfagas** de menos de 2 s sobre un piso de ~2 m, que un scrape de 15-30 s
  promedia hasta hacerlas desaparecer.

## Decision

1. **La CPU queda descartada como señal de escalado del executor.** No se declara ninguna
   métrica `Resource` en el HPA.
2. **La señal es el backlog de trabajo que compite por un worker**, publicado como
   `teleflow_executor_backlog`: instancias en `TRIGGERED`, `IN_PROGRESS` o `RETRYING`,
   **excluyendo `WAITING_SIGNAL`**.
3. **El HPA existe en el chart y viene apagado** (`autoscaling.enabled: false`), como métrica
   externa con objetivo `AverageValue` por pod.
4. Mientras esté apagado, la capacidad se ajusta con las dos perillas que sí están medidas:
   `WORKER_CONCURRENCY` y la cantidad de réplicas.

## Rationale

**Por qué el backlog y no la CPU:** está medido arriba. La CPU no distingue estar al límite de
estar 4× pasado, que es justo la distinción que un autoscaler tiene que hacer.

**Por qué se excluye `WAITING_SIGNAL`:** una instancia dormida en durable sleep no ocupa nada —
`_run` hace `return` y suelta semáforo y lease. Contarla haría escalar por humanos que no
contestaron, y las réplicas nuevas no podrían hacer nada al respecto. En el stack de medición
había 225 instancias dormidas con el executor ocioso: con el gauge nuevo desplegado, el backlog
marcó **0**. La distinción no es teórica.

**Por qué un gauge propio y no una query sobre `teleflow_instances_current`:** esa métrica lleva
labels por `flow_name` y `status`, así que la decisión de qué cuenta como saturación quedaría
escrita en la query del adapter del organismo, donde nadie la revisa — y donde, como se vio, es
fácil que se cuele `WAITING_SIGNAL`. Un escalar sin labels deja la decisión en el repo.

**Por qué apagado, que es la parte que más se puede discutir:** el criterio que ya fijó
[[2026-08-08-alcance-del-ha-de-la-capa-de-datos]] es *solo entra lo que se puede probar
rompiéndolo*. Acá se puede probar la mitad: que la cola crece, y que el gauge la ve. La otra
mitad **no** está probada: que sumar réplicas la drene. El trabajo no sale de una cola
compartida — `trigger` hace `_spawn(_drive(...))` y devuelve, así que la instancia la ejecuta la
réplica que recibió el `POST /execute`. Un pod nuevo atiende disparos nuevos y no toca lo que ya
está encolado en otro. Prenderlo por default prometería una elasticidad que nadie demostró.

## Consequences

- El ítem de Fase E se cierra **con una decisión medida**, no con un objeto de configuración que
  nadie probó.
- El chart corta el install si el autoscaling se prende mal: `maxReplicas < minReplicas`, sin
  `metricName`, `backlogPorPod: 0`, o una ventana de estabilización más corta que el refresco de
  la métrica. Un HPA que no puede escalar es peor que ninguno, porque se ve en `kubectl get hpa`
  y no hace nada.
- Con el HPA prendido, el `Deployment` del executor **deja de declarar `replicas`**. Sin eso,
  cada `helm upgrade` devolvería la escala al número de `values.yaml` y el HPA la volvería a
  subir, en silencio.
- **Límite consciente y escrito:** el gauge se refresca cada `BUSINESS_METRICS_INTERVAL` (30 s),
  así que el HPA nunca ve un backlog más fresco que eso — medido: con la base en 69 encolados el
  gauge todavía decía 319, de 26 s antes. Por eso las ventanas de estabilización no pueden bajar
  del intervalo, y el chart lo verifica.
- **Segundo límite, verificado en un cluster y no supuesto:** prender el HPA requiere que el
  organismo publique la métrica externa (Prometheus Adapter o equivalente). Aplicado en kind sin
  adapter, el HPA queda en `<unknown>/20 (avg)` con `ScalingActive: False` /
  `FailedGetExternalMetric`, y el Deployment **se queda en sus 3 réplicas**: no escala, y
  tampoco colapsa a `minReplicas` ni oscila. No rompe nada, tampoco hace nada — que es
  exactamente el modo de falla que este ADR acepta.
- Queda pendiente, para quien retome esto: **demostrar que sumar réplicas drena la cola**. Si se
  demuestra, prender el HPA por default es un cambio de una línea. Si se demuestra que no, lo
  que corresponde es repartir el trabajo por cola compartida, y eso es otro diseño.

## Alternatives

- **HPA sobre CPU.** Descartado con medición, no por opinión: ver *Context*.
- **Cerrarlo sin HPA, como límite consciente.** Era una salida legítima y cierra Fase E igual.
  Se prefirió dejar el mecanismo listo y apagado porque la parte cara es la señal —y la señal
  sirve igual para dashboard y alerta aunque el HPA no se prenda nunca.
- **Publicar solo la métrica, sin HPA.** Misma idea, un paso más corto. Se descartó porque
  obligaba a quien lo retome a rederivar el diseño del HPA (tipo de métrica, objetivo por pod,
  ventanas contra el refresco), que es donde está el conocimiento que dejó la medición.
- **Escalar por `teleflow_instances_current` agregando en el adapter.** Descartado: deja la
  definición de saturación fuera del repo.

## Sources

- Work-stream [[hpa-executor]] (medición completa, tablas y método).
- Medido sobre `copp-ia@devyos@3469734`; los archivos de abajo son los que cambia esta decisión.
- `helm/teleflow/values.yaml`, bloque `autoscaling`; `helm/teleflow/templates/hpa.yaml`.
- `teleflow/executor_service/business_metrics.py` (`EXECUTOR_BACKLOG`, `WORKER_STATUSES`).
- `teleflow/executor_service/engine.py` (semáforo, `trigger`, durable sleep).
- [[2026-08-08-alcance-del-ha-de-la-capa-de-datos]] — de donde sale el criterio de alcance.
- [[2026-07-30-scanner-de-negocio-multi-replica]] — por qué el colector vive en un solo pod.
