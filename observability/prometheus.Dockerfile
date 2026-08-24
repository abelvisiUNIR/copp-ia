# Config horneada en la imagen: evita bind mounts (rutas con espacios en
# Windows rompen el file sharing de Docker Desktop).
FROM prom/prometheus:v2.53.0
COPY prometheus.yml /etc/prometheus/prometheus.yml
