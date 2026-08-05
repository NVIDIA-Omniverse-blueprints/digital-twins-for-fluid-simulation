#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.
#
# Validate a workflow manifest against its USD AppState schema(s).
#
# Runs the controller's own validator inside the app via repo.sh launch --exec, so it uses only
# what the app already ships — no extra dependencies, repeatable on any built checkout.
#
# Usage:
#   tools/validate/rtdt-validate.sh [--manifest <workflow.toml>] [--stage <stage.usda>]
#                                   [--schemas <Api...>] [--callbacks <name...>]
#                                   [--schema-plugins <dir...>]
#                                   [--format text|json] [--app <kit_app>]
#
# With no arguments it validates the app's configured manifest. Exit status: 0 valid,
# 1 validation errors, 2 launch/usage error.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

APP="omni.rtwt.editor.kit"
export RTDT_VALIDATE_FORMAT="text"
unset RTDT_VALIDATE_MANIFEST RTDT_VALIDATE_STAGE RTDT_VALIDATE_SCHEMAS RTDT_VALIDATE_CALLBACKS

# Resolve a path argument to absolute (the app launches from the repo root).
_abs() { case "$1" in /*) echo "$1";; *) echo "$PWD/$1";; esac; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest) export RTDT_VALIDATE_MANIFEST="$(_abs "$2")"; shift 2;;
        --stage)    export RTDT_VALIDATE_STAGE="$(_abs "$2")"; shift 2;;
        --format)   export RTDT_VALIDATE_FORMAT="$2"; shift 2;;
        --app)      APP="$2"; shift 2;;
        --schemas)  shift; v=""; while [[ $# -gt 0 && "$1" != --* ]]; do v="$v $1"; shift; done; export RTDT_VALIDATE_SCHEMAS="${v# }";;
        # A schema not loaded by the app (e.g. an example bringing its own) must be on USD's plugin
        # path before launch, since the schema registry aggregates definitions at startup.
        --schema-plugins) shift; v=""; while [[ $# -gt 0 && "$1" != --* ]]; do v="$v:$(_abs "$1")"; shift; done; export PXR_PLUGINPATH_NAME="${v#:}${PXR_PLUGINPATH_NAME:+:$PXR_PLUGINPATH_NAME}";;
        --callbacks) shift; v=""; while [[ $# -gt 0 && "$1" != --* ]]; do v="$v $1"; shift; done; export RTDT_VALIDATE_CALLBACKS="${v# }";;
        -h|--help) sed -n '12,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0;;
        *) echo "rtdt-validate: unknown argument '$1'" >&2; exit 2;;
    esac
done

out="$(cd "$REPO" && ./repo.sh launch -n "$APP" -- --exec "$HERE/rtdt_validate.py" --no-window 2>&1)" || true

# The script prints its report between these markers, then a status line.
report="$(awk '/RTDT_VALIDATE_BEGIN/{f=1;next} /RTDT_VALIDATE_END/{f=0} f' <<< "$out")"
status="$(awk '/^RTDT_VALIDATE_STATUS /{print $2}' <<< "$out" | tail -1)"

if [[ -z "$status" ]]; then
    echo "rtdt-validate: the validator did not produce a result. Launch output (tail):" >&2
    tail -n 30 <<< "$out" >&2
    exit 2
fi

printf '%s\n' "$report"
[[ "$status" == "ok" ]] && exit 0 || exit 1
