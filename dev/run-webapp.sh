#!/bin/bash

set -e

# Cleanup function to kill background processes on exit
cleanup() {
    echo "Shutting down..."
    kill $KIT_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

#Run the headless kit application in the background
CMD="../kit-app/_build/linux-x86_64/release/omni.rtwt.webrtc.kit.sh"
ARGS=(
    "--no-window"
    "--/app/viewport/forceHideFps=true"
    "--/exts/omni.kit.benchmark.main/carb_profiling_enabled=false"
    "--/exts/omni.rtwt.controller/usd_file=$(pwd)/../rtwt-files/Collected_world_rtwt_Main_v1/world_rtwt_minimal.usda" 
    "--/exts/omni.rtwt.controller/triton_http_url=localhost:8080" 
    '--/exts/omni.rtwt.controller/stl_path_format='"$(pwd)"'/../rtwt-files/demo_data_all/low_res/detailed_car_{}/aero_suv_low.stl'
)

echo "Starting Kit application with $CMD ${ARGS[@]} $@"
"$CMD" "${ARGS[@]}" "$@" &
KIT_PID=$!

# Wait a moment for kit to initialize
sleep 5

# Run the web app (foreground)
cd ../web-app
npm run dev