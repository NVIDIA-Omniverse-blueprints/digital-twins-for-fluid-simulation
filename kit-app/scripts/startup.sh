#!/usr/bin/env bash
set -e
set -u

# Check for libGLX_nvidia.so.0 (needed for vulkan)
ldconfig -p | grep libGLX_nvidia.so.0 || NOTFOUND=1
if [[ -v NOTFOUND ]]; then
    cat << EOF > /dev/stderr

Fatal Error: Can't find libGLX_nvidia.so.0...

Ensure running with NVIDIA runtime. (--gpus all) or (--runtime nvidia)

EOF
    exit 1
fi

# Detect NVIDIA Vulkan API version, and create ICD:
export VK_ICD_FILENAMES=/tmp/nvidia_icd.json

USER_ID="${USER_ID:-""}"
if [ -z "${USER_ID}" ]; then
  echo "User id is not set"
fi

# export __GL_a011d7=1   # OGL_VULKAN_GFN_SHADER_CACHE_CONTROL=ON
# export __GL_43787d32=0 #  OGL_VULKAN_SHADER_CACHE_TYPE=NONE
# export __GL_3489FB=1   # OGL_VULKAN_IGNORE_PIPELINE_CACHE=ON

export OPENBLAS_NUM_THREADS=10 
export SenderTimeout=${SenderTimeout:-100000}

KIT_APP_BASE=${KIT_APP:-"omni.rtwt.app.webrtc.kit"}
KIT_APP_FILE="/app/apps/${KIT_APP_BASE}"

CMD="/app/kit/kit"
ARGS=(
    "${KIT_APP_FILE}"
    "--no-window"
    "--/app/viewport/forceHideFps=true"
    "--/app/auto_load_usd=${USD_URL}"
    "--/exts/omni.cgns/zmq_ip_address=${ZMQ_IP}"
    "--/exts/omni.cgns/zmq_first_port=${ZMQ_FIRST_PORT}"
    "--/exts/omni.cgns/zmq_request_timeout_ms=${ZMQ_REQUEST_TIMEOUT}"
    "--/exts/omni.cgns/request_queue_size=${ZMQ_REQUEST_QUEUE_SIZE}"
    "--/exts/omni.cgns/services_count=1"
    "--/exts/omni.cgns/array_pool_dump=true"
    "--/exts/omni.kit.benchmark.main/carb_profiling_enabled=false"
)

echo "==== Print out kit config ${KIT_APP_FILE} for debugging ===="
cat ${KIT_APP_FILE}
echo "==== End of kit config ${KIT_APP_FILE} ===="

while true; do
    echo "Starting viewport streamer with $CMD ${ARGS[@]} $@"
    "$CMD" "${ARGS[@]}" "$@"
done