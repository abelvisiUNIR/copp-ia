# Checklist de instalación por organismo

Criterio de salida de la fase de producción: **una instalación reproducible por organismo**
(aislamiento por instancia — cada organismo tiene su propia base y su propia instalación).

Este checklist **se ejecutó de punta a punta** contra un cluster limpio antes de escribirse.
Lo que no se pudo verificar está marcado explícitamente en la última sección; el resto se
verificó corriendo los comandos que están acá.

> Ante conflicto entre este archivo y el chart, manda el chart. Los valores citados salen de
> `helm/teleflow/values.yaml` y `helm/teleflow/values-production.yaml`.

---

## 0. Antes de empezar

- [ ] **Cluster Kubernetes** con acceso `kubectl` y permisos para crear namespace, Secrets,
      Deployments, StatefulSets y Jobs.
- [ ] **Un StorageClass por default.** Postgres, Redis y RabbitMQ son StatefulSets con PVC; sin
      StorageClass los pods quedan en `Pending` esperando volumen.
- [ ] **Ingress controller**, si se va a publicar el gateway por Ingress (paso 4).
- [ ] `helm` 3.x.

## 1. Imágenes en un registry que el cluster pueda leer

El chart **no construye nada**: espera imágenes ya publicadas. Son dos.

```bash
docker build -t <registry>/teleflow:<tag> .
docker build -t <registry>/review-ui:<tag> review-ui

docker push <registry>/teleflow:<tag>
docker push <registry>/review-ui:<tag>
```

- [ ] Las dos imágenes están en el registry.
- [ ] **El tag es inmutable** (`1.4.2`, un SHA — no `latest` ni `dev`). Con un tag que se
      reescribe y `pullPolicy: IfNotPresent`, un `helm upgrade` reporta `deployed` y los pods
      siguen con el código viejo: el pod spec no cambió, así que no hay rollout ni aviso.
- [ ] Si el registry es privado: `imagePullSecrets` configurado en el namespace.

## 2. Namespace y Secret de aplicación

**El Secret va primero.** Si se declara `existingSecret` y el Secret no existe, el install corta
nombrándolo (esa guarda se agregó justamente porque antes decía `Install complete` y dejaba
todos los pods en `CreateContainerConfigError`, con el motivo enterrado en sus eventos).

```bash
kubectl create namespace teleflow

kubectl -n teleflow create secret generic teleflow-secrets \
  --from-literal=TELEFLOW_API_KEY='<valor>' \
  --from-literal=LLM_API_KEY='<valor>'      # solo si el composer usa un proveedor real
```

- [ ] Namespace creado.
- [ ] Secret creado, con `TELEFLOW_API_KEY`.
- [ ] La API key **no** quedó en ningún archivo del repo ni en un `values` versionado.

> La alternativa es `--set apiKey=<valor>` y que el chart cree el Secret. Sirve para una
> instalación chica; en producción es peor, porque el valor pasa por la línea de comandos y por
> el historial de shell. Sin ninguno de los dos, el install falla diciendo cuál falta.

## 3. Capa de datos: propia o del organismo

**Decisión previa al install.** La plataforma entrega HA solo donde nadie más puede hacerlo.

| | Cuándo | Cómo |
|---|---|---|
| **Propia** (default) | No hay base administrada | Nada que configurar. Postgres y Redis quedan en **1 réplica a propósito**; RabbitMQ va en cluster de 3 con quorum queues |
| **Del organismo** (recomendado) | Ya opera Postgres administrado | `postgres.enabled=false` + bloque `externalDatabase` |

Con base administrada, la contraseña **no** tiene que pasar por `values`:

```bash
kubectl -n teleflow create secret generic pg-creds \
  --from-literal=DATABASE_URL='postgresql+asyncpg://usuario:clave@host:5432/base?ssl=verify-full'
```

- [ ] Decidido cuál de los dos caminos.
- [ ] Si es del organismo: `externalDatabase.host` y `externalDatabase.existingSecret` definidos.
      El `host` es obligatorio aun con `existingSecret` — los initContainers esperan a que
      acepte conexiones antes de arrancar los pods.
- [ ] Si es propia: se aceptó por escrito que Postgres y Redis quedan en una réplica.

## 4. Entrada externa y TLS

`values-production.yaml` viene con `gateway.ingress.enabled: true`. Con el Ingress prendido, el
chart **exige TLS**: publicar el gateway en claro manda la API key en un header.

Dos salidas válidas:

```bash
# (a) El TLS lo termina este Ingress
--set gateway.ingress.tls[0].secretName=teleflow-tls \
--set gateway.ingress.tls[0].hosts[0]=teleflow.organismo.gub.uy

# (b) Lo termina un balanceador del organismo, más arriba
--set gateway.ingress.allowInsecure=true
```

- [ ] `gateway.ingress.host` es el dominio real del organismo.
- [ ] TLS resuelto por (a) o por (b), **declarado a propósito** y no por descarte.
- [ ] Si es (a): el `hosts` del bloque TLS coincide con `host`. Si no coinciden, el Ingress se
      crea igual y el controller sirve su certificado default.

## 5. Instalar

```bash
helm upgrade --install teleflow ./helm/teleflow \
  --namespace teleflow \
  -f helm/teleflow/values-production.yaml \
  --set image.repository=<registry>/teleflow \
  --set image.tag=<tag-inmutable> \
  --set uiImage.repository=<registry>/review-ui \
  --set uiImage.tag=<tag-inmutable> \
  --set existingSecret=teleflow-secrets \
  --set gateway.ingress.host=teleflow.organismo.gub.uy \
  --set gateway.ingress.allowInsecure=true      # o el bloque tls del paso 4
```

- [ ] `helm install` termina en `STATUS: deployed`.
- [ ] El Job de migración quedó en `Completed`:
      `kubectl -n teleflow get jobs`
- [ ] **Todos** los pods en `Running`:
      `kubectl -n teleflow get pods`

> El schema lo aplica un Job normal con initContainers que esperan a Postgres, no un hook de
> Helm. Efecto práctico: en un upgrade los pods nuevos no arrancan hasta que el schema está en
> `head`, así que el orden "schema primero, código después" lo garantiza el pod.

## 6. Verificar que **ejecuta**, no que levantó

Que los pods estén `Running` no dice que la plataforma funcione.

```bash
kubectl -n teleflow port-forward svc/teleflow-api-gateway 8000:8000

curl -s http://localhost:8000/health
curl -s http://localhost:8000/flows -H "X-TeleFlow-API-Key: <valor>"
```

- [ ] `/health` responde `{"status":"ok"}`.
- [ ] `/flows` responde `200` con la API key, y `401` sin ella.
- [ ] **Un proceso de negocio corre end-to-end.** Con el repo a mano:
      `TELEFLOW_GATEWAY_URL=http://localhost:8000 TELEFLOW_API_KEY=<valor> pytest tests/e2e`
      Los tests de Prometheus se saltan salvo que el organismo tenga uno accesible (paso 7).
- [ ] Un `helm upgrade` con los mismos valores deja la instalación sana (idempotencia).

## 7. Observabilidad (opcional, opt-in)

El chart trae los **puntos de integración**, no el stack: anotaciones de scrape, `ServiceMonitor`
y ConfigMap de dashboards, más las reglas de alerta como `PrometheusRule`. Todo apagado por
default.

- [ ] Si el organismo tiene Prometheus: `observabilidad.serviceMonitor=true` y/o
      `observabilidad.prometheusRule=true`.
- [ ] La alerta de **frescura** de las métricas de negocio está activa. `up == 0` no alcanza: con
      la base caída el pod queda vivo y los gauges siguen publicando el último valor bueno.

## 8. Después de instalar

- [ ] Backup de Postgres programado y **restore probado** (`scripts/backup.sh`, `docs/runbooks.md`).
- [ ] Runbooks operativos revisados con quien vaya a estar de guardia.
- [ ] Rotación de `TELEFLOW_API_KEY` acordada. Las keys se administran por API con scope
      `keys:admin`; la key del Secret es el **bootstrap**.
- [ ] Autoescalado del executor: **queda apagado** salvo decisión explícita. Ver el bloque
      `autoscaling` de `values.yaml` — la CPU está descartada como señal con medición, y prenderlo
      requiere que el organismo publique la métrica externa.

---

## Qué de este checklist NO está verificado

Honestidad sobre el alcance de la verificación: lo de arriba se ejecutó en un cluster **kind**
limpio, con imágenes locales y la capa de datos propia del chart. En esa configuración se
verificó la instalación completa, los 18 pods arriba, la migración aplicada, **24 tests e2e
verdes contra el cluster** y un `helm upgrade` idempotente que los deja verdes de nuevo.

No se verificó, y no se declara verde:

- **Registry privado y `imagePullSecrets`** (paso 1): las imágenes se cargaron directo al nodo.
- **Base administrada del organismo** (paso 3, camino externo): se renderiza en CI y se prueba
  que toma puerto, credenciales y TLS, pero nunca se instaló contra un Postgres administrado real.
- **Ingress con TLS real** (paso 4): el cluster de prueba no tenía Ingress controller; se instaló
  con `allowInsecure=true`.
- **Prometheus del organismo** (paso 7): los tres e2e de métricas se saltaron por eso.
- **RKE2** específicamente, que es lo que nombra la documentación de arquitectura.

Cada uno de esos puntos depende de infraestructura del organismo. La forma de cerrarlos es
correr este mismo checklist en la primera instalación real y anotar acá lo que aparezca.
