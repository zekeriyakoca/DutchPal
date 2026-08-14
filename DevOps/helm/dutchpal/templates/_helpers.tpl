{{/*
Build a full image reference.
Usage: {{ include "dutchpal.image" (dict "Values" .Values "imageName" .Values.agentApi.image) }}
*/}}
{{- define "dutchpal.image" -}}
{{- printf "%s/%s:%s" .Values.global.imageRegistry .imageName .Values.global.imageTag -}}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "dutchpal.labels" -}}
app.kubernetes.io/name: dutchpal
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: Helm
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Traefik API version supports both v3 and older Traefik CRDs.
*/}}
{{- define "dutchpal.traefikApiVersion" -}}
{{- if .Capabilities.APIVersions.Has "traefik.io/v1alpha1" -}}
traefik.io/v1alpha1
{{- else -}}
traefik.containo.us/v1alpha1
{{- end -}}
{{- end }}
