# El contexto de build es la RAÍZ del repo (ver docker-compose.yml), no ./observability, para
# poder copiar las reglas de alerta desde `helm/teleflow/alerts/`.
#
# Están ahí y no acá por el mismo motivo que los dashboards: Helm solo puede leer archivos de
# adentro del chart, así que unas reglas en `observability/` obligarían al chart a tener su
# propia copia — y dos copias de un archivo de alertas se desincronizan sin que nada avise. Una
# sola fuente, dos consumidores: el compose por este COPY, y el cluster por el `PrometheusRule`
# que genera el chart.
#
# Config horneada en la imagen: evita bind mounts (rutas con espacios en
# Windows rompen el file sharing de Docker Desktop).
FROM prom/prometheus:v2.53.0
COPY observability/prometheus.yml /etc/prometheus/prometheus.yml
# La ruta destino es la que declara `rule_files`. Si falta este COPY, Prometheus **no arranca**
# (`error loading rules`) en vez de arrancar sin alertas — que es el fallo que uno quiere de un
# archivo de alertas ausente.
COPY helm/teleflow/alerts/alerts.yml /etc/prometheus/alerts.yml
