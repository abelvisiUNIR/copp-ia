FROM grafana/grafana:11.1.0
COPY grafana/provisioning /etc/grafana/provisioning
# Fuera de /var/lib/grafana a propósito: ahí monta el volumen `grafana-data`, y Docker copia
# el contenido de la imagen al volumen **solo cuando lo crea vacío**. Con los dashboards ahí
# adentro, un dashboard nuevo nunca llegaba a una instalación ya existente: el volumen viejo
# tapaba la imagen nueva y la provisión quedaba silenciosamente desactualizada.
COPY grafana/dashboards /etc/grafana/dashboards
