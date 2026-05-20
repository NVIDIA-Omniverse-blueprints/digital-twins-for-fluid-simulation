#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# Thin wrapper around `helm upgrade --install`. Picks up MODE from the env
# (default: standard) and forwards NGC_API_KEY for the standard profile.
# Extra args are passed through to helm, so you can do e.g.
#   MODE=lite ./deploy.sh --set kit.image.repository=my-registry/rtdt-kit-app

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_NAME="${RELEASE_NAME:-rtdt-fluid-sim}"
MODE="${MODE:-standard}"

if ! command -v helm &> /dev/null; then
  echo "ERROR: helm is not installed or not in PATH." >&2
  exit 1
fi

# Validate config before touching the cluster. Faster feedback, and makes the
# placeholder guardrail below run even when kubeconfig isn't set yet.
case "$MODE" in
  standard)
    if [ -z "${NGC_API_KEY:-}" ]; then
      echo "ERROR: standard mode requires NGC_API_KEY for the AeroNIM runtime." >&2
      echo "       export NGC_API_KEY=<your-ngc-api-key>  (or set MODE=lite)" >&2
      exit 1
    fi
    # Placeholder-detection guardrail. Real NGC keys don't contain these
    # tokens; catches the "I copy-pasted from the docs and forgot to fill
    # in the value" class of mistake before it ships the literal string
    # into a Secret resource on the cluster.
    case "$NGC_API_KEY" in
      *"<"*|*">"*|"your-"*|"REPLACE"*|"REDACTED"*|"xxxxx"*)
        echo "ERROR: NGC_API_KEY looks like a placeholder: '${NGC_API_KEY}'" >&2
        echo "       Set it to a real key (nvapi-... or similar) before deploying." >&2
        exit 1
        ;;
    esac
    EXTRA_ARGS=(--set-string "ngcSecret.apiKey=${NGC_API_KEY}")
    ;;
  lite)
    EXTRA_ARGS=()
    ;;
  *)
    echo "ERROR: unknown MODE '$MODE'. Expected 'standard' or 'lite'." >&2
    exit 1
    ;;
esac

if ! kubectl cluster-info &> /dev/null 2>&1; then
  echo "ERROR: Cannot connect to Kubernetes cluster. Check your kubeconfig." >&2
  exit 1
fi

echo "Deploying NVIDIA Digital Twins for Fluid Simulation (mode=${MODE})..."

helm upgrade --install "$RELEASE_NAME" "$SCRIPT_DIR" \
  --set "mode=${MODE}" \
  "${EXTRA_ARGS[@]}" \
  "$@"
