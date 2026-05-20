#!/usr/bin/env bash
# =============================================================================
# startup.sh — container entrypoint for the RTWT Kit app
# =============================================================================
#
# Runs inside the `kit` / `kit-lite` services (see compose.yml). Responsible
# for:
#   1. Verifying the NVIDIA runtime is wired up (fails fast otherwise).
#   2. Building the kit command line from environment variables.
#   3. Launching the kit app in a restart loop so a crash doesn't kill the
#      container — handy during development when extension code is under edit.
#
# Environment variables consumed (all optional unless noted):
#   KIT_APP                  — kit app bundle to launch (default: omni.rtwt.webrtc.kit)
#   NIM_TRITON_IP_ADDRESS    — Triton host (default: localhost; compose sets "aeronim")
#   NIM_TRITON_HTTP_PORT     — Triton port (default: 8080)
#   RTWT_OFFLINE_MODE        — if set, run omni.rtwt.inference in offline/cache mode
#   SenderTimeout            — StreamSDK watchdog in ms (default: 100000)
#   USER_ID                  — informational only; warns if unset
#
# Extra CLI args passed to this script are forwarded verbatim to kit, so you
# can do `docker compose run kit --/some/setting=value` for one-off overrides.
# =============================================================================

set -e
set -u

# -----------------------------------------------------------------------------
# Preflight: confirm the NVIDIA userspace libraries are visible. Without these
# Vulkan init silently fails deep inside kit, so fail loudly up front instead.
# -----------------------------------------------------------------------------
ldconfig -p | grep libGLX_nvidia.so.0 || NOTFOUND=1
if [[ -v NOTFOUND ]]; then
    cat << EOF > /dev/stderr

Fatal Error: Can't find libGLX_nvidia.so.0...

Ensure running with NVIDIA runtime. (--gpus all) or (--runtime nvidia)

EOF
    exit 1
fi

# Point Vulkan loader at the NVIDIA ICD generated during image build.
export VK_ICD_FILENAMES=/tmp/nvidia_icd.json

USER_ID="${USER_ID:-""}"
if [ -z "${USER_ID}" ]; then
  echo "User id is not set"
fi

# Cap OpenBLAS thread fan-out — it defaults to every core on the host, which
# oversubscribes when several containers share the box.
export OPENBLAS_NUM_THREADS=10
# Raise StreamSDK sender watchdog so pausing in a debugger doesn't drop the stream.
export SenderTimeout=${SenderTimeout:-100000}

# Kit app bundle to launch. Override via $KIT_APP to swap front-ends.
KIT_APP_BASE=${KIT_APP:-"omni.rtwt.webrtc.kit"}
KIT_APP_FILE="/app/apps/${KIT_APP_BASE}"

CMD="/app/kit/kit"
# Base kit command line. Each "--/path/to/setting=value" is a Carbonite
# setting override; these take precedence over the .kit file contents.
ARGS=(
    "${KIT_APP_FILE}"
    "--no-window"                                                  # headless — streaming only
    "--/app/viewport/forceHideFps=true"                            # hide FPS overlay in stream
    "--/exts/omni.kit.benchmark.main/carb_profiling_enabled=false" # no perf tracing overhead
    "--/exts/omni.rtwt.inference/triton_http_url=${NIM_TRITON_IP_ADDRESS:-localhost}:${NIM_TRITON_HTTP_PORT:-8080}"
    "--/persistent/app/usd/muteUsdDiagnostics=false"               # surface USD composition warnings
)

# Normalize a truthy/falsy env value to kit's boolean syntax (true/false).
# Unknown values pass through so we don't silently mask a typo.
to_bool() {
    case "${1,,}" in
        1|true|yes|on) echo "true" ;;
        0|false|no|off|"") echo "false" ;;
        *) echo "$1" ;;
    esac
}

# Offline-mode overrides — only applied when RTWT_OFFLINE_MODE is set (i.e.
# the kit-lite compose profile). In offline mode the inference extension
# reads pre-baked results from data/cache/ instead of calling Triton.
if [[ -n "${RTWT_OFFLINE_MODE:-}" ]]; then
    ARGS+=("--/exts/omni.rtwt.inference/offline_mode=$(to_bool "${RTWT_OFFLINE_MODE}")")
    ARGS+=("--/exts/omni.rtwt.inference/offline_cache_dir=/app/rtwt/data/cache")

    # Cache generation is always disabled inside the container: writing to
    # ./data/cache via a bind mount runs into host/container UID mismatches.
    # Run the cache-gen workflow on the host instead.
    ARGS+=("--/exts/omni.rtwt.inference/generate_if_missing=false")
fi

# Dump the resolved .kit config for post-mortem debugging of startup failures.
echo "==== Print out kit config ${KIT_APP_FILE} for debugging ===="
cat ${KIT_APP_FILE}
echo "==== End of kit config ${KIT_APP_FILE} ===="

# Restart loop: if kit exits (crash, manual quit, signal) we relaunch it so a
# developer editing extension code doesn't have to `docker compose up` again.
# Extra args to this script ("$@") are appended so ad-hoc overrides work.
while true; do
    echo "Starting viewport streamer with $CMD ${ARGS[@]} $@"
    "$CMD" "${ARGS[@]}" "$@"
done
