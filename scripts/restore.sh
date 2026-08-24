#!/usr/bin/env bash
# Restaura un respaldo de TeleFlow.
#
# **Pide la base destino explícitamente y no tiene default.** Restaurar es la operación que
# destruye datos, no la que los salva: un default apuntando a `teleflow` haría que un error de
# tipeo se lleve puesta la base de trabajo.
#
# Uso:
#   scripts/restore.sh backups/teleflow-20260725-120000.dump teleflow_restore_test
#   scripts/restore.sh backups/....dump teleflow --confirmar   # sobre la base real
set -euo pipefail

DUMP="${1:?falta el archivo de dump}"
DESTINO="${2:?falta la base destino (a propósito: no hay default)}"
CONFIRMAR="${3:-}"
SERVICIO="${POSTGRES_SERVICE:-postgres}"
USUARIO="${POSTGRES_USER:-teleflow}"
BASE_TRABAJO="${POSTGRES_DB:-teleflow}"

[ -f "$DUMP" ] || { echo "ERROR: no existe $DUMP" >&2; exit 1; }

if [ "$DESTINO" = "$BASE_TRABAJO" ] && [ "$CONFIRMAR" != "--confirmar" ]; then
  echo "ERROR: '$DESTINO' es la base en uso. Esto la reemplaza entera." >&2
  echo "Si es lo que querés, repetí el comando con --confirmar al final." >&2
  exit 1
fi

echo "Recreando la base '$DESTINO'..."
docker compose exec -T "$SERVICIO" psql -U "$USUARIO" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$DESTINO\" WITH (FORCE);" \
  -c "CREATE DATABASE \"$DESTINO\";" >/dev/null

echo "Restaurando desde $DUMP..."
# --exit-on-error: sin esto pg_restore reporta los errores y termina con código 0, así que un
# restore a medias se vería como exitoso — que es justo lo que no se quiere de un respaldo.
docker compose exec -T "$SERVICIO" pg_restore -U "$USUARIO" -d "$DESTINO" \
  --no-owner --exit-on-error < "$DUMP"

TABLAS=$(docker compose exec -T "$SERVICIO" psql -U "$USUARIO" -d "$DESTINO" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")

echo "Restaurado en '$DESTINO': $(echo "$TABLAS" | tr -d '[:space:]') tablas."
