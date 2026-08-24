# El contexto de build es la RAÍZ del repo (ver docker-compose.yml), no ./observability, para
# poder copiar los dashboards desde `helm/teleflow/dashboards/`.
#
# Están ahí y no acá porque Helm solo puede leer archivos de adentro del chart: si vivieran en
# `observability/`, el chart necesitaría su propia copia y habría dos que se desincronizan sin
# que nada avise. Una sola fuente, dos consumidores — el compose por este COPY, y el cluster
# por el ConfigMap que genera el chart.
FROM grafana/grafana:11.1.0
COPY observability/grafana/provisioning /etc/grafana/provisioning
# Fuera de /var/lib/grafana a propósito: ahí monta el volumen `grafana-data`, y Docker copia
# el contenido de la imagen al volumen **solo cuando lo crea vacío**. Con los dashboards ahí
# adentro, un dashboard nuevo nunca llegaba a una instalación ya existente: el volumen viejo
# tapaba la imagen nueva y la provisión quedaba silenciosamente desactualizada.
COPY helm/teleflow/dashboards /etc/grafana/dashboards
