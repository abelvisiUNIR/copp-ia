{{- define "teleflow.labels" -}}
app.kubernetes.io/part-of: teleflow
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "teleflow.env" -}}
{{- range $key, $value := .Values.env }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
- name: TELEFLOW_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.apiKeySecret }}
      key: TELEFLOW_API_KEY
- name: LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.apiKeySecret }}
      key: LLM_API_KEY
      optional: true
{{- end }}
