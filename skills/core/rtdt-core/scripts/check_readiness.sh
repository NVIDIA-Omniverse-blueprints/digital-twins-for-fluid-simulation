#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.
#
# Profile-aware RTDT runtime preflight. This checks running Compose services,
# browser-facing HTTP endpoints, and standard-profile Triton models. It cannot
# establish a browser WebRTC session or prove that controls/rendering work.
#
# Usage:
#   check_readiness.sh [--profile standard|lite] [--web-port N] [--proxy-port N]
#                      [--triton-port N] [--wait-seconds N] [--interval N]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"

PROFILE="standard"
WEB_PORT="${WEB_HOST_PORT:-5173}"
PROXY_PORT="${RTWT_HTTP_HOST_PORT:-80}"
TRITON_PORT="${RTWT_TRITON_HOST_PORT:-8080}"
WAIT_SECONDS=0
INTERVAL=5

usage() {
    printf '%s\n' \
        "Usage:" \
        "  check_readiness.sh [--profile standard|lite] [--web-port N] [--proxy-port N]" \
        "                     [--triton-port N] [--wait-seconds N] [--interval N]"
}

require_value() {
    if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "check_readiness: $1 requires a value" >&2
        exit 2
    fi
}

require_port() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]] || (( 10#$value < 1 || 10#$value > 65535 )); then
        echo "check_readiness: $name must be an integer from 1 to 65535" >&2
        exit 2
    fi
}

require_nonnegative_integer() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "check_readiness: $name must be a non-negative integer" >&2
        exit 2
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            require_value "$@"
            PROFILE="$2"
            shift 2
            ;;
        --web-port)
            require_value "$@"
            WEB_PORT="$2"
            shift 2
            ;;
        --proxy-port)
            require_value "$@"
            PROXY_PORT="$2"
            shift 2
            ;;
        --triton-port)
            require_value "$@"
            TRITON_PORT="$2"
            shift 2
            ;;
        --wait-seconds)
            require_value "$@"
            WAIT_SECONDS="$2"
            shift 2
            ;;
        --interval)
            require_value "$@"
            INTERVAL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "check_readiness: unknown argument '$1'" >&2
            exit 2
            ;;
    esac
done

if [[ "$PROFILE" != "standard" && "$PROFILE" != "lite" ]]; then
    echo "check_readiness: --profile must be 'standard' or 'lite'" >&2
    exit 2
fi
require_port "--web-port" "$WEB_PORT"
require_port "--proxy-port" "$PROXY_PORT"
require_port "--triton-port" "$TRITON_PORT"
require_nonnegative_integer "--wait-seconds" "$WAIT_SECONDS"
require_nonnegative_integer "--interval" "$INTERVAL"
if (( INTERVAL == 0 )); then
    echo "check_readiness: --interval must be greater than zero" >&2
    exit 2
fi

command -v docker >/dev/null 2>&1 || {
    echo "check_readiness: docker is not available" >&2
    exit 2
}
docker compose version >/dev/null 2>&1 || {
    echo "check_readiness: the Docker Compose plugin is not available" >&2
    exit 2
}
command -v curl >/dev/null 2>&1 || {
    echo "check_readiness: curl is not available" >&2
    exit 2
}
if ! (cd "$REPO" && docker compose --profile "$PROFILE" config --quiet); then
    echo "check_readiness: the Compose configuration is invalid" >&2
    exit 2
fi

service_running() {
    local service="$1"
    grep -Fxq "$service" <<< "$RUNNING_SERVICES"
}

reachable() {
    curl -fsS --max-time 3 --output /dev/null "$1" 2>/dev/null
}

probe() {
    local kit_service
    if [[ "$PROFILE" == "lite" ]]; then
        kit_service="kit-lite"
    else
        kit_service="kit"
    fi

    if ! RUNNING_SERVICES="$(
        cd "$REPO" &&
        docker compose --profile "$PROFILE" ps --status running --services
    )"; then
        echo "check_readiness: unable to query Compose services" >&2
        return 2
    fi

    service_running "$kit_service" && KIT=true || KIT=false
    service_running "web" && WEB=true || WEB=false
    service_running "launch-proxy" && PROXY=true || PROXY=false
    reachable "http://localhost:${WEB_PORT}/" && WEB_REACHABLE=true || WEB_REACHABLE=false
    reachable "http://localhost:${PROXY_PORT}/" && PROXY_REACHABLE=true || PROXY_REACHABLE=false

    if [[ "$PROFILE" == "standard" ]]; then
        service_running "aeronim" && AERONIM=true || AERONIM=false
        reachable "http://localhost:${TRITON_PORT}/v2/health/ready" &&
            TRITON_READY=true || TRITON_READY=false
        reachable "http://localhost:${TRITON_PORT}/v2/models/rtwt/ready" &&
            RTWT_MODEL_READY=true || RTWT_MODEL_READY=false
        reachable "http://localhost:${TRITON_PORT}/v2/models/model/ready" &&
            UPSTREAM_MODEL_READY=true || UPSTREAM_MODEL_READY=false
    else
        AERONIM="n/a"
        TRITON_READY="n/a"
        RTWT_MODEL_READY="n/a"
        UPSTREAM_MODEL_READY="n/a"
    fi

    READY=false
    if [[ "$KIT" == true &&
          "$WEB" == true &&
          "$PROXY" == true &&
          "$WEB_REACHABLE" == true &&
          "$PROXY_REACHABLE" == true ]]; then
        if [[ "$PROFILE" == "lite" ||
              ( "$AERONIM" == true &&
                "$TRITON_READY" == true &&
                "$RTWT_MODEL_READY" == true &&
                "$UPSTREAM_MODEL_READY" == true ) ]]; then
            READY=true
        fi
    fi
    return 0
}

json_value() {
    if [[ "$1" == "n/a" ]]; then
        printf '"n/a"'
    else
        printf '%s' "$1"
    fi
}

deadline=$((SECONDS + WAIT_SECONDS))
while true; do
    if ! probe; then
        exit 2
    fi
    if [[ "$READY" == true || $SECONDS -ge $deadline ]]; then
        break
    fi
    remaining=$((deadline - SECONDS))
    delay=$INTERVAL
    if (( delay > remaining )); then
        delay=$remaining
    fi
    (( delay > 0 )) && sleep "$delay"
done

printf 'RTDT_READY_BEGIN\n'
printf '{'
printf '"profile":"%s",' "$PROFILE"
printf '"kit":%s,' "$KIT"
printf '"web":%s,' "$WEB"
printf '"launch_proxy":%s,' "$PROXY"
printf '"web_reachable":%s,' "$WEB_REACHABLE"
printf '"proxy_reachable":%s,' "$PROXY_REACHABLE"
printf '"aeronim":%s,' "$(json_value "$AERONIM")"
printf '"triton_ready":%s,' "$(json_value "$TRITON_READY")"
printf '"rtwt_model_ready":%s,' "$(json_value "$RTWT_MODEL_READY")"
printf '"upstream_model_ready":%s,' "$(json_value "$UPSTREAM_MODEL_READY")"
printf '"browser_stream_verified":false,'
printf '"ready":%s' "$READY"
printf '}\n'
printf 'RTDT_READY_END\n'

[[ "$READY" == true ]]
