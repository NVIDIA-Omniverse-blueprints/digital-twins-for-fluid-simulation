#!/bin/bash

set -e
# Longer timeout for streamsdk
export SenderTimeout=100000

# Run the Kit application after build.sh

CMD="../kit-app/_build/linux-x86_64/release/omni.rtwt.editor.kit.sh"
ARGS=(
    "--/exts/omni.rtwt.controller/usd_file=$(pwd)/../rtwt-files/Collected_world_rtwt_Main_v1/world_rtwt_minimal.usda" 
    "--/exts/omni.rtwt.controller/triton_http_url=localhost:8080" 
    '--/exts/omni.rtwt.controller/stl_path_format='"$(pwd)"'/../rtwt-files/demo_data_all/low_res/detailed_car_{}/aero_suv_low.stl'
)

echo "Starting Kit application with $CMD ${ARGS[@]} $@"
"$CMD" "${ARGS[@]}" "$@"