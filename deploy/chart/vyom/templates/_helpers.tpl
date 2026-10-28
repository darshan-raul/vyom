{{- define "vyom.labels" -}}
app.kubernetes.io/part-of: vyom
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Restricted container security context shared by every Vyom-owned container. */}}
{{- define "vyom.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{- define "vyom.podSecurity" -}}
runAsNonRoot: true
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{/* "1h" or "30m" in values; the API wants seconds. */}}
{{- define "vyom.tokenSeconds" -}}
{{- $d := .Values.collector.tokenDuration -}}
{{- if hasSuffix "h" $d -}}{{ mul (trimSuffix "h" $d | int) 3600 }}
{{- else if hasSuffix "m" $d -}}{{ mul (trimSuffix "m" $d | int) 60 }}
{{- else -}}{{ $d | int }}{{- end -}}
{{- end -}}
