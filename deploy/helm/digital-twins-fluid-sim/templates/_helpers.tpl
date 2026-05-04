{{/*
Expand the name of the chart.
*/}}
{{- define "digital-twins-fluid-sim.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncated at 63 chars (DNS label limit).
*/}}
{{- define "digital-twins-fluid-sim.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "digital-twins-fluid-sim.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "digital-twins-fluid-sim.labels" -}}
helm.sh/chart: {{ include "digital-twins-fluid-sim.chart" . }}
{{ include "digital-twins-fluid-sim.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels (shared by Deployments and Services).
*/}}
{{- define "digital-twins-fluid-sim.selectorLabels" -}}
app.kubernetes.io/name: {{ include "digital-twins-fluid-sim.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Docker-registry secret data from values.
*/}}
{{- define "digital-twins-fluid-sim.dockerconfigjson" -}}
{{- $registry := .Values.imagePullSecret.registry -}}
{{- $username := .Values.imagePullSecret.username -}}
{{- $password := .Values.imagePullSecret.password -}}
{{- printf "{\"auths\":{\"%s\":{\"auth\":\"%s\"}}}" $registry (printf "%s:%s" $username $password | b64enc) | b64enc }}
{{- end }}
