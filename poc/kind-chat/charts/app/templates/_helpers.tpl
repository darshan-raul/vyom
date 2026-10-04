{{- define "kindchat.name" -}}
{{- .Release.Name | trunc 54 | trimSuffix "-" -}}
{{- end -}}
{{- define "kindchat.labels" -}}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/part-of: vyom-kind-chat-poc
{{- end -}}
