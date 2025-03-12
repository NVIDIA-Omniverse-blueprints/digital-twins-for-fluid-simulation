import asyncio
import argparse
import os
import time

# package path
from inference_service import ServiceZMQ


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Process file and network parameters.')

    parser.add_argument('port', type=int, metavar='PORT',
                        help='Port for ZMQ')
    parser.add_argument('--zmq_port_offset', type=int, default=10,
                        help="Port offset for the next service (default=10)")
    parser.add_argument('--zmq_protocol', type=str, default='tcp',
                        help="Protocol for ZMQ (default=tcp)")
    parser.add_argument('--zmq_tmp', type=str, default="",
                        help=f"Tmp dir for ZMQ (default='')")
    parser.add_argument('--unnormalization', action='store_true',
                        help='Unnormalize dataset (default: False)')
    parser.add_argument("--num_points", type=int, default=1_255_000,
                        help="Number of requested sampled points (1.255.000)")

    args = parser.parse_args()

    zmq_first_port = args.port
    zmq_port_offset = args.zmq_port_offset
    zmq_protocol = args.zmq_protocol
    zmq_tmp = args.zmq_tmp

    unnormalize_data = args.unnormalization
    num_points = args.num_points

    # define fields which will be sent as an array ('bounding_box_dims' are only used locally)
    field_names = ["coordinates", "velocity", "pressure", "sdf"]

    # paths are relative and are added to the path in STL_ROOT in inference.py
    stl_ids = (
        #100-400 currently unused
        list(range(100, 124)) +
        list(range(200, 224)) +
        list(range(300, 316)) +
        list(range(400, 416)) +
        #concept car
        list(range(500, 516))
    )
    stl_path_format = "design_%d_1/aero_suv_low.stl"
    stream_velocity = 30    # default value

    rank = 0

    print(f"Current config: unnormalize dataset: {unnormalize_data}")
    print(f"                num_points: {num_points:,}")

    zmq_port = zmq_first_port + rank * zmq_port_offset
    zmq_tmp_dir = zmq_tmp if zmq_protocol == "ipc" else ""

    print("                communication library: ZMQ")
    print(f"                config request port: {zmq_port}")
    print(f"                zmpq protocol: {zmq_protocol}")
    print(f"                tmp dir: {zmq_tmp_dir}")

    service_zmq = ServiceZMQ(
        field_names=field_names,
        unnormalize=unnormalize_data,
        num_points=num_points
    )
    asyncio.run(service_zmq.run(zmq_port, zmq_dir=zmq_tmp_dir))   
