{{/*
SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: LicenseRef-NvidiaProprietary
*/}}

{{/* Chart name, truncated to the Kubernetes 63-char limit. */}}
{{- define "rtdt.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Fully-qualified release name used as the prefix for every rendered object. */}}
{{- define "rtdt.fullname" -}}
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

{{- define "rtdt.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels applied to every rendered object. */}}
{{- define "rtdt.labels" -}}
helm.sh/chart: {{ include "rtdt.chart" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: {{ include "rtdt.name" . }}
{{- end }}

{{- define "rtdt.kit.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rtdt.name" . }}-kit
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: kit
{{- end }}

{{- define "rtdt.web.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rtdt.name" . }}-web
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: web
{{- end }}

{{- define "rtdt.aeronim.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rtdt.name" . }}-aeronim
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: aeronim
{{- end }}

{{/*
Name of the Kubernetes Secret holding NGC_API_KEY (standard mode only).
Returns `.Values.ngcSecret.apiSecretName` when set, otherwise a name derived
from the release. Used both by the Secret resource and by the deployments
that reference it, so both sides stay in sync automatically.
*/}}
{{- define "rtdt.ngcApiSecretName" -}}
{{- if .Values.ngcSecret.apiSecretName -}}
{{- .Values.ngcSecret.apiSecretName -}}
{{- else -}}
{{ include "rtdt.fullname" . }}-ngc-api-key
{{- end -}}
{{- end }}

{{/*
Profile derivation. Single source of truth for "is aeronim present?" and
"does the kit container run in offline (cached) mode?". Templates should always
consult these helpers rather than poking at .Values.mode directly.
*/}}
{{- define "rtdt.aeronimEnabled" -}}
{{- eq .Values.mode "standard" | ternary "true" "" -}}
{{- end }}

{{- define "rtdt.offlineMode" -}}
{{- eq .Values.mode "lite" | ternary "true" "" -}}
{{- end }}

{{/*
Validate .Values.mode up front. Using fail() here causes helm lint / template /
install to error with a clear message when a typo slips in, instead of silently
rendering a half-enabled chart.
*/}}
{{- define "rtdt.validateMode" -}}
{{- if not (or (eq .Values.mode "standard") (eq .Values.mode "lite")) -}}
{{- fail (printf "Invalid .Values.mode %q: expected \"standard\" or \"lite\"" .Values.mode) -}}
{{- end -}}
{{- end }}
