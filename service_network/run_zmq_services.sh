#!/bin/bash

port=${ZMQ_PORT:-5555}
port_offset=${ZMQ_PORT_OFFSET:-10}
protocol=${ZMQ_PROTOCOL:-"tcp"}
tmp_dir=${ZMQ_TMP_DIR:-"/tmp/service"}
points=${POINT_CNT:-1255000}

echo "Starting service..."

cd ..

python -u service_network/main.py $port \
    --zmq_port_offset $port_offset --zmq_protocol $protocol --zmq_tmp $tmp_dir \
    --num_points $points
