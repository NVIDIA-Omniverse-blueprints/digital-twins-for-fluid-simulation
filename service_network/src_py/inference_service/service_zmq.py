import zmq
import zmq.asyncio
import json
import numpy as np
import asyncio

from .service import Service

ZMQ_CHUNK_SIZE = 2 * 1024 * 1024  # 2MB


class ServiceZMQ(Service):

    @staticmethod
    async def send_data(socket, metadata, data_array):
        '''Send data with ZMQ'''

        json_string = json.dumps(metadata)

        try:
            await socket.send(json_string.encode('utf-8'), zmq.DONTWAIT)
        except zmq.ZMQError as e:
            raise RuntimeError(f"Error sending metadata with ZMQ: {e}")

        chunk_size = data_array.nbytes if ZMQ_CHUNK_SIZE == 0 else ZMQ_CHUNK_SIZE
        num_chunks = (data_array.nbytes + chunk_size - 1) // chunk_size

        try:
            await socket.send(b"START", zmq.DONTWAIT)

            for i in range(num_chunks):
                start = i * chunk_size
                end = min(start + chunk_size, data_array.nbytes)
                chunk = data_array[start:end]
                await socket.send(chunk, zmq.DONTWAIT, copy=False)

            await socket.send(b"END")
        except zmq.ZMQError as e:
            raise RuntimeError(f"Error sending array with ZMQ: {e}")

    async def _receive_data(self, config_queue, context, url, first_port):

        if self.file_inferences:
            self._data_preloader()

        fields_cnt = len(self.field_names)

        # Set up ZeroMQ
        sockets = []
        port = first_port
        for i in range(fields_cnt):
            socket = context.socket(zmq.PUB)
            socket.bind(f"{url}{port}")
            sockets.append(socket)
            port += 1

        print(f"Created publisher sockets on ports {first_port} - {port - 1}")

        self._reset_config()

        while True:
            print("Waiting for a config...")
            config_request = await config_queue.get()
            print("Requesting config: ", config_request)

            file_index = self._request_data(config_request)

            for i in range(fields_cnt):
                field_name = self.field_names[i]
                metadata, array = self._get_data_to_send(file_index, field_name, config_request)
                if array is None:
                    continue

                print(f"Sending field '{field_name}'...")
                await ServiceZMQ.send_data(sockets[i], metadata, array)

    async def _receive_config_requests(self, config_queue, context, address):

        socket = context.socket(zmq.REP)
        socket.bind(address)
        socket.setsockopt(zmq.RCVHWM, 1)  # Limit incoming requests
        fields_cnt = str(len(self.field_names))

        while True:
            print("Waiting for a config request...")
            config_request = await socket.recv_json()
            if config_request['id'] < 0:
                print(f"Client has connected to {address}...")

                # confirm connection
                await socket.send_string("0")

            else:
                print("Config request received...")
                await config_queue.put(config_request)

                # reply with field name size (number of arrays sent)
                await socket.send_string(fields_cnt)

    async def run(self, port, zmq_dir=""):
        '''Run config receiver and data publisher in separate async functions'''

        # set up ZeroMQ
        context = zmq.asyncio.Context()

        if zmq_dir == "":
            protocol = "tcp"
            url = f"{protocol}://*:"
        else:
            protocol = "ipc"
            url = f"{protocol}://{zmq_dir}/"

        address = f"{url}{port}"

        # next ports are used for publisher sockets
        port += 1

        self._field_names_reader()

        config_queue = asyncio.Queue()
        await asyncio.gather(self._receive_config_requests(config_queue, context, address),
                             self._receive_data(config_queue, context, url, port))
