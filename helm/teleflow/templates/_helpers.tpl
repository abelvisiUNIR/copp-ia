{{- define "teleflow.labels" -}}
app.kubernetes.io/part-of: teleflow
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
  Nombre del Secret con las credenciales. Si el organismo lo administra por fuera
  (`existingSecret`), se usa ese; si no, el que crea el chart, prefijado con el release para
  no colisionar con otra instalación en el mismo namespace.
*/}}
{{- define "teleflow.secretName" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.existingSecret -}}
{{- end }}

{{/*
  Nombre de un recurso de la plataforma, prefijado con el release.

  Antes los Deployments y Services propios se llamaban `api-gateway`, `executor-service`, …
  sin prefijo, mientras los subcharts sí prefijaban (`teleflow-postgresql`). De ese supuesto
  mezclado salían dos problemas: dos releases en el mismo namespace colisionaban, y el comando
  que documenta la arquitectura (`kubectl scale deployment teleflow-executor-service`,
  docs/teleflow-deployment.typ §10.1) daba NotFound.
*/}}
{{- define "teleflow.name" -}}
{{- printf "%s-%s" .release .svc -}}
{{- end }}

{{/*
  Host y puerto de cada servicio de datos, derivados del release.
  Antes estaban hardcodeados en values.yaml como `teleflow-postgresql`, lo que ataba el chart
  a instalarse con el release name `teleflow` sin decirlo en ninguna parte.
*/}}
{{- define "teleflow.postgresHost" -}}
{{- if .Values.postgres.enabled -}}
{{- printf "%s-postgres" .Release.Name -}}
{{- else -}}
{{- required "postgres.enabled=false exige externalDatabase.host" .Values.externalDatabase.host -}}
{{- end -}}
{{- end }}

{{- define "teleflow.redisHost" -}}
{{- if .Values.redis.enabled -}}
{{- printf "%s-redis" .Release.Name -}}
{{- else -}}
{{- required "redis.enabled=false exige externalRedis.host" .Values.externalRedis.host -}}
{{- end -}}
{{- end }}

{{- define "teleflow.rabbitmqHost" -}}
{{- if .Values.rabbitmq.enabled -}}
{{- printf "%s-rabbitmq" .Release.Name -}}
{{- else -}}
{{- required "rabbitmq.enabled=false exige externalRabbitmq.host" .Values.externalRabbitmq.host -}}
{{- end -}}
{{- end }}

{{- define "teleflow.databaseUrl" -}}
{{- printf "postgresql+asyncpg://%s:%s@%s:5432/%s" .Values.postgres.auth.username .Values.postgres.auth.password (include "teleflow.postgresHost" .) .Values.postgres.auth.database -}}
{{- end }}

{{/*
  URLs internas entre servicios. Se derivan del release por el mismo motivo que los hosts de
  la capa de datos: estaban fijas en values.yaml (`http://parser-service:8001`) y dejaban de
  resolver en cuanto los Services pasaron a llevar prefijo.
*/}}
{{- define "teleflow.serviceUrls" -}}
{{- $r := .Release.Name }}
- name: PARSER_URL
  value: {{ printf "http://%s-parser-service:8001" $r | quote }}
- name: REGISTRY_URL
  value: {{ printf "http://%s-registry-service:8003" $r | quote }}
- name: EXECUTOR_URL
  value: {{ printf "http://%s-executor-service:8002" $r | quote }}
- name: COMPOSER_URL
  value: {{ printf "http://%s-composer-service:8004" $r | quote }}
- name: GATEWAY_URL
  value: {{ printf "http://%s-api-gateway:8000" $r | quote }}
{{- end }}

{{/*
  initContainer que espera a que un host TCP acepte conexiones.
  Se usa para Postgres, que en un install nuevo tarda en estar listo.
*/}}
{{- define "teleflow.waitForDb" -}}
- name: wait-for-db
  image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  command:
    - python
    - -c
    - |
      import socket, sys, time
      host, port = "{{ include "teleflow.postgresHost" . }}", 5432
      plazo = time.monotonic() + {{ .Values.migrations.waitForDbSeconds }}
      while time.monotonic() < plazo:
          try:
              with socket.create_connection((host, port), timeout=3):
                  print(f"{host}:{port} acepta conexiones", flush=True)
                  sys.exit(0)
          except OSError as e:
              print(f"esperando a {host}:{port} ({e})", flush=True)
              time.sleep(2)
      print(f"{host}:{port} no respondio en {{ .Values.migrations.waitForDbSeconds }}s", file=sys.stderr)
      sys.exit(1)
{{- end }}

{{/*
  initContainer que espera a que el schema esté en `head`.

  Existe porque los servicios revientan al arrancar si les falta una tabla (el executor
  consulta `process_instances` en el startup), y el Job de migraciones no puede garantizar
  llegar antes: como hook `pre-install` no tiene Postgres, y como hook `post-install` corre
  DESPUÉS de que Helm espera a los Deployments — que nunca se ponen listos. Con este espera
  cada pod a su propio schema y el orden deja de depender del orden de Helm.

  Chequea `(head)` en la salida de `alembic current`: si la tabla `alembic_version` todavía no
  existe, `alembic current` no imprime nada y termina con 0, así que mirar el exit code no
  alcanza.
*/}}
{{- define "teleflow.waitForSchema" -}}
- name: wait-for-schema
  image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  env:
    {{- include "teleflow.env" . | nindent 4 }}
  command:
    - sh
    - -c
    - |
      plazo=$(( $(date +%s) + {{ .Values.migrations.waitForSchemaSeconds }} ))
      while [ "$(date +%s)" -lt "$plazo" ]; do
        if alembic current 2>/dev/null | grep -q '(head)'; then
          echo "schema en head"
          exit 0
        fi
        echo "esperando las migraciones..."
        sleep 3
      done
      echo "el schema no llego a head en {{ .Values.migrations.waitForSchemaSeconds }}s" >&2
      exit 1
{{- end }}

{{- define "teleflow.env" -}}
{{- range $key, $value := .Values.env }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- include "teleflow.serviceUrls" . }}
- name: DATABASE_URL
  value: {{ include "teleflow.databaseUrl" . | quote }}
- name: REDIS_URL
  value: {{ printf "redis://%s:6379/0" (include "teleflow.redisHost" .) | quote }}
- name: RABBITMQ_URL
  value: {{ printf "amqp://%s:%s@%s:5672/" .Values.rabbitmq.auth.username .Values.rabbitmq.auth.password (include "teleflow.rabbitmqHost" .) | quote }}
- name: TELEFLOW_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "teleflow.secretName" . }}
      key: TELEFLOW_API_KEY
- name: LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "teleflow.secretName" . }}
      key: LLM_API_KEY
      optional: true
{{- end }}
