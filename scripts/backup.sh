#!/usr/bin/env bash
# Respaldo de la base de TeleFlow.
#
# Postgres es el único estado que el producto no puede reconstruir (ver el ADR "qué se
# respalda"): Redis es cache y coordinación, los dashboards viven en la imagen, y las colas
# son trabajo en vuelo, no un registro.
#
# Se ejecuta con la base **arriba**: `pg_dump` toma una instantánea transaccionalmente
# consistente sin bloquear escrituras. Parar el servicio convertiría el respaldo en una
# interrupción, y un respaldo que cuesta una ventana de mantenimiento se corre menos seguido.
#
# Uso:
#   scripts/backup.sh                    # -> backups/teleflow-YYYYmmdd-HHMMSS.dump
#   scripts/backup.sh /ruta/salida.dump
set -euo pipefail

DESTINO="${1:-backups/teleflow-$(date +%Y%m%d-%H%M%S).dump}"
SERVICIO="${POSTGRES_SERVICE:-postgres}"
USUARIO="${POSTGRES_USER:-teleflow}"
BASE="${POSTGRES_DB:-teleflow}"

mkdir -p "$(dirname "$DESTINO")"

# Formato custom (-Fc): comprime y permite restaurar selectivamente.
# El dump sale por stdout del contenedor para no dejar archivos adentro.
docker compose exec -T "$SERVICIO" pg_dump -U "$USUARIO" -d "$BASE" -Fc > "$DESTINO"

TAMANIO=$(wc -c < "$DESTINO")
if [ "$TAMANIO" -lt 1024 ]; then
  echo "ERROR: el dump quedó en $TAMANIO bytes — algo falló y el archivo no sirve." >&2
  exit 1
fi

echo "Respaldo en $DESTINO ($(( TAMANIO / 1024 )) KB)"
echo "Restaurar con: scripts/restore.sh $DESTINO <base_destino>"
