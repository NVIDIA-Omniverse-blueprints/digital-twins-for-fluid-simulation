#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# Local-first Helm validation for the RTDT Fluid Simulation chart.
#
# Default behavior is intentionally cluster-free: lint the chart and render the
# supported profiles. Pass --cluster to install into the current kubeconfig
# context, wait for rollout, and run the Helm smoke test hook.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_NAME="${RELEASE_NAME:-rtdt-fluid-sim}"
NAMESPACE="${NAMESPACE:-default}"
MODE="${MODE:-lite}"
TIMEOUT="${TIMEOUT:-20m}"
DUMMY_NGC_API_KEY="nvapi-render-test-key-not-a-secret"
RUN_CLUSTER=0
USE_MICROK8S=0
HELM_BIN="${HELM_BIN:-}"
KUBECTL_BIN="${KUBECTL_BIN:-}"
HELM_TEST_LOGS="${HELM_TEST_LOGS:-1}"
EXTRA_ARGS=()
RENDER_WORK_DIR=""

cleanup_render_checks() {
  if [ -n "${RENDER_WORK_DIR}" ] && [ -d "${RENDER_WORK_DIR}" ]; then
    rm -rf "${RENDER_WORK_DIR}"
  fi
}

trap cleanup_render_checks EXIT

usage() {
  cat <<'USAGE'
Usage:
  ./test.sh [options] [-- <extra helm upgrade args>]

Default:
  Run cluster-free chart checks:
    - helm lint for lite and standard modes
    - helm template for lite, standard with generated secrets, and standard
      with pre-created secrets
    - invalid mode guardrail check

Options:
  --cluster            Also install into the current kubeconfig context, wait,
                       and run `helm test`.
  --microk8s           Use MicroK8s helm/kubectl commands directly and run the
                       cluster smoke test.
  --mode MODE          Cluster install mode for --cluster: lite or standard.
                       Default: lite.
  --release-name NAME  Helm release name. Default: rtdt-fluid-sim.
  --namespace NAME     Kubernetes namespace. Default: default.
  --timeout DURATION   Helm/kubectl wait timeout. Default: 20m.
  --no-test-logs       Run `helm test` without `--logs`. Useful on reused
                       MicroK8s/Horde hosts with stale kubelet serving certs.
  -h, --help           Show this help.

Examples:
  ./test.sh
  ./test.sh --cluster --mode lite
  ./test.sh --microk8s --mode lite
  NGC_API_KEY=nvapi-... ./test.sh --cluster --mode standard
  ./test.sh --microk8s --mode lite -- --set web.service.type=LoadBalancer
USAGE
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" > /dev/null 2>&1; then
    echo "ERROR: ${command_name} is not installed or not in PATH." >&2
    exit 1
  fi
}

resolve_microk8s_command() {
  local command_name="$1"
  local snap_path="$2"

  if command -v "${command_name}" > /dev/null 2>&1; then
    command -v "${command_name}"
    return
  fi

  if [ -x "${snap_path}" ]; then
    echo "${snap_path}"
    return
  fi

  echo "ERROR: ${command_name} was not found. Is MicroK8s installed?" >&2
  exit 1
}

configure_commands() {
  if [ "${USE_MICROK8S}" -eq 1 ]; then
    HELM_BIN="${HELM_BIN:-$(resolve_microk8s_command microk8s.helm3 /snap/bin/microk8s.helm3)}"
    KUBECTL_BIN="${KUBECTL_BIN:-$(resolve_microk8s_command microk8s.kubectl /snap/bin/microk8s.kubectl)}"
  else
    HELM_BIN="${HELM_BIN:-helm}"
    KUBECTL_BIN="${KUBECTL_BIN:-kubectl}"
  fi

  require_command "${HELM_BIN}"
  if [ "${RUN_CLUSTER}" -eq 1 ]; then
    require_command "${KUBECTL_BIN}"
  fi
}

validate_mode() {
  case "$MODE" in
    lite|standard)
      ;;
    *)
      echo "ERROR: --mode must be 'lite' or 'standard', got '${MODE}'." >&2
      exit 1
      ;;
  esac

  case "$HELM_TEST_LOGS" in
    0|1|false|true)
      ;;
    *)
      echo "ERROR: HELM_TEST_LOGS must be 0/1 or false/true, got '${HELM_TEST_LOGS}'." >&2
      exit 1
      ;;
  esac
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  local description="$3"

  if ! grep -Fq "$pattern" "$file"; then
    echo "ERROR: expected rendered chart to contain ${description}." >&2
    echo "       Missing pattern: ${pattern}" >&2
    exit 1
  fi
}

assert_not_contains() {
  local file="$1"
  local pattern="$2"
  local description="$3"

  if grep -Fq "$pattern" "$file"; then
    echo "ERROR: rendered chart unexpectedly contains ${description}." >&2
    echo "       Pattern: ${pattern}" >&2
    exit 1
  fi
}

run_render_checks() {
  local lite_manifest
  local standard_manifest
  local standard_external_secret_manifest
  local expected_fullname
  local invalid_mode_log

  RENDER_WORK_DIR="$(mktemp -d)"
  lite_manifest="${RENDER_WORK_DIR}/lite.yaml"
  standard_manifest="${RENDER_WORK_DIR}/standard.yaml"
  standard_external_secret_manifest="${RENDER_WORK_DIR}/standard-external-secret.yaml"
  invalid_mode_log="${RENDER_WORK_DIR}/invalid-mode.log"
  if [[ "${RELEASE_NAME}" == *"rtdt-fluid-sim"* ]]; then
    expected_fullname="${RELEASE_NAME}"
  else
    expected_fullname="${RELEASE_NAME}-rtdt-fluid-sim"
  fi

  echo "==> helm lint (lite)"
  "${HELM_BIN}" lint "${SCRIPT_DIR}" --set mode=lite

  echo "==> helm lint (standard)"
  "${HELM_BIN}" lint "${SCRIPT_DIR}" \
    --set mode=standard \
    --set-string "ngcSecret.apiKey=${DUMMY_NGC_API_KEY}"

  echo "==> helm template (lite)"
  "${HELM_BIN}" template "${RELEASE_NAME}" "${SCRIPT_DIR}" --set mode=lite > "${lite_manifest}"
  assert_contains "${lite_manifest}" "name: ${expected_fullname}-kit" "kit deployment"
  assert_contains "${lite_manifest}" "name: ${expected_fullname}-web" "web deployment"
  assert_contains "${lite_manifest}" "name: RTWT_OFFLINE_MODE" "lite offline mode env var"
  assert_not_contains "${lite_manifest}" "component: aeronim" "AeroNIM resources in lite mode"

  echo "==> helm template (standard, generated NGC secrets)"
  "${HELM_BIN}" template "${RELEASE_NAME}" "${SCRIPT_DIR}" \
    --set mode=standard \
    --set-string "ngcSecret.apiKey=${DUMMY_NGC_API_KEY}" > "${standard_manifest}"
  assert_contains "${standard_manifest}" "name: ${expected_fullname}-aeronim" "AeroNIM deployment"
  assert_contains "${standard_manifest}" "image: \"rtdt-aeronim:latest\"" "custom AeroNIM image"
  assert_contains "${standard_manifest}" "mountPath: /opt/data" "AeroNIM data mount"
  assert_contains "${standard_manifest}" "mountPath: /opt/stages" "AeroNIM stages mount"
  assert_contains "${standard_manifest}" "name: NGC_API_KEY" "NGC_API_KEY env var"
  assert_contains "${standard_manifest}" "type: kubernetes.io/dockerconfigjson" "NGC image pull secret"
  assert_not_contains "${standard_manifest}" "name: RTWT_OFFLINE_MODE" "lite offline mode env var in standard mode"

  echo "==> helm template (standard, pre-created secrets)"
  "${HELM_BIN}" template "${RELEASE_NAME}" "${SCRIPT_DIR}" \
    --set mode=standard \
    --set ngcSecret.create=false > "${standard_external_secret_manifest}"
  assert_contains "${standard_external_secret_manifest}" "name: ${expected_fullname}-aeronim" "AeroNIM deployment"
  assert_not_contains "${standard_external_secret_manifest}" "type: kubernetes.io/dockerconfigjson" "generated NGC image pull secret"

  echo "==> helm template rejects invalid mode"
  if "${HELM_BIN}" template "${RELEASE_NAME}" "${SCRIPT_DIR}" --set mode=invalid > /dev/null 2> "${invalid_mode_log}"; then
    echo "ERROR: chart accepted invalid mode." >&2
    exit 1
  fi
  assert_contains "${invalid_mode_log}" "Invalid .Values.mode" "invalid mode failure"

  cleanup_render_checks
  RENDER_WORK_DIR=""
}

run_cluster_smoke() {
  local install_args
  local deployments
  local fullname
  local svc_type
  local node_ip
  local node_port
  local lb_ip
  local test_args

  if ! "${KUBECTL_BIN}" cluster-info > /dev/null 2>&1; then
    echo "ERROR: ${KUBECTL_BIN} cannot reach a cluster. For MicroK8s, run:" >&2
    echo "       ./test.sh --microk8s --mode lite" >&2
    echo "       Or export MicroK8s kubeconfig and use --cluster:" >&2
    echo "       microk8s config > ~/.kube/microk8s-rtdt.yaml" >&2
    echo "       export KUBECONFIG=~/.kube/microk8s-rtdt.yaml" >&2
    exit 1
  fi

  install_args=(
    upgrade
    --install "${RELEASE_NAME}" "${SCRIPT_DIR}"
    --namespace "${NAMESPACE}"
    --create-namespace
    --wait
    --timeout "${TIMEOUT}"
    --set "mode=${MODE}"
  )

  if [ "${MODE}" = "standard" ] && [ -n "${NGC_API_KEY:-}" ]; then
    install_args+=(--set-string "ngcSecret.apiKey=${NGC_API_KEY}")
  fi
  if [[ "${RELEASE_NAME}" == *"rtdt-fluid-sim"* ]]; then
    fullname="${RELEASE_NAME}"
  else
    fullname="${RELEASE_NAME}-rtdt-fluid-sim"
  fi

  echo "==> helm upgrade --install ${RELEASE_NAME} ${SCRIPT_DIR} (mode=${MODE}, namespace=${NAMESPACE})"
  if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
    echo "    applying ${#EXTRA_ARGS[@]} extra helm arg(s)"
  fi
  "${HELM_BIN}" "${install_args[@]}" "${EXTRA_ARGS[@]}"

  deployments=("${fullname}-kit" "${fullname}-web")
  if [ "${MODE}" = "standard" ]; then
    deployments+=("${fullname}-aeronim")
  fi

  for deployment in "${deployments[@]}"; do
    echo "==> kubectl wait deployment/${deployment}"
    "${KUBECTL_BIN}" -n "${NAMESPACE}" wait \
      --for=condition=Available \
      "deployment/${deployment}" \
      --timeout="${TIMEOUT}"
  done

  echo "==> helm test ${RELEASE_NAME}"
  test_args=(
    test "${RELEASE_NAME}"
    --namespace "${NAMESPACE}"
    --timeout "${TIMEOUT}"
  )
  case "$HELM_TEST_LOGS" in
    1|true)
      test_args+=(--logs)
      ;;
    *)
      echo "    skipping helm test log retrieval"
      ;;
  esac
  "${HELM_BIN}" "${test_args[@]}"

  echo "==> Current pods"
  "${KUBECTL_BIN}" -n "${NAMESPACE}" get pods -l "app.kubernetes.io/instance=${RELEASE_NAME}"

  svc_type="$("${KUBECTL_BIN}" -n "${NAMESPACE}" get svc "${fullname}-web" -o jsonpath='{.spec.type}')"
  case "${svc_type}" in
    NodePort)
      node_ip="$("${KUBECTL_BIN}" get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')"
      node_port="$("${KUBECTL_BIN}" -n "${NAMESPACE}" get svc "${fullname}-web" -o jsonpath='{.spec.ports[0].nodePort}')"
      echo "Web UI: http://${node_ip}:${node_port}/"
      ;;
    LoadBalancer)
      lb_ip="$("${KUBECTL_BIN}" -n "${NAMESPACE}" get svc "${fullname}-web" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
      if [ -n "${lb_ip}" ]; then
        echo "Web UI: http://${lb_ip}/"
      else
        echo "Web UI: LoadBalancer is pending; run: kubectl -n ${NAMESPACE} get svc ${fullname}-web -w"
      fi
      ;;
    *)
      echo "Web UI: kubectl -n ${NAMESPACE} port-forward svc/${fullname}-web 5173:80"
      echo "Then open: http://localhost:5173/"
      ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --cluster|--microk8s)
      RUN_CLUSTER=1
      if [ "$1" = "--microk8s" ]; then
        USE_MICROK8S=1
      fi
      shift
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --release-name)
      RELEASE_NAME="$2"
      shift 2
      ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --no-test-logs)
      HELM_TEST_LOGS=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

validate_mode
configure_commands
run_render_checks

if [ "${RUN_CLUSTER}" -eq 1 ]; then
  run_cluster_smoke
else
  echo "Render-only Helm checks passed. Run with --cluster to install and smoke test the current kubeconfig context."
fi
