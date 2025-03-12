# Use a lightweight Python image as the base
FROM python:3.10

# Set the working directory
WORKDIR /workspace/service_network/

# Copy the service code into the container
COPY service_network /workspace/service_network

# Install ZeroMQ
RUN pip install .

RUN pip install \
    trimesh \ 
    tritonclient[http]

# Copy demo data into the image
COPY rtwt-files/demo_data_all/ /data/

# Command to run the Python service
CMD ["./run_zmq_services.sh"]
