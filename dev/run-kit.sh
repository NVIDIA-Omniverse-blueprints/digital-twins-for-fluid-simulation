#!/bin/bash

set -e
# Longer timeout for streamsdk
export SenderTimeout=100000

# Run the Kit application
../kit-app/_build/linux-x86_64/release/omni.rtwt.editor.kit.sh --/app/viewport/forceHideFps=true --/app/auto_load_usd=$(pwd)/../rtwt-files/Collected_world_rtwt_Main_v1/world_rtwt_Main_v1.usda --/exts/omni.cgns/zmq_ip_address=localhost --/exts/omni.cgns/zmq_first_port=5555 --/exts/omni.cgns/zmq_request_timeout_ms=5000 --/exts/omni.cgns/request_queue_size=1 --/exts/omni.cgns/services_count=1  --/exts/omni.kit.benchmark.main/carb_profiling_enabled=false --/exts/omni.cgns/array_pool_dump=true --/exts/omni.kit.benchmark.main/carb_profiling_enabled=false