<h2><img align="center" src=images/NVIDIA_image.png> Omniverse Blueprint for Real-time Computer-aided Engineering Digital Twins

## Overview

The Omniverse Blueprint for Real-time Computer-aided Engineering Digital Twins offers a reference workflow for building real-time digital twins for external aerodynamic Computational Fluid Dynamics (CFD) workflows combining CUDA-X accelerated solvers, PhysicsNeMo for physics AI, and Omniverse for high quality rendering. 

This blueprint offers a comprehensive reference workflow for building real-time digital twins, specifically tailored for external aerodynamic CFD simulations. This workflow leverages CUDA-X accelerated solvers for high-performance computing, PhysicsNeMo for advanced simulation AI, and Omniverse for high-quality, real-time rendering. 

The digital twin tool is available to test either through build.nvidia.com or by deploying it yourself using this set of instructions. The build.nvidia.com version is deployed as a live, interactive blueprint on build.nvidia.com, where you can work through a prebuild environment, selecting different configurations and seeing the outputs from a real-time inference against a pre-trained machine learning (ML) model through Omniverse. If you want to deploy this blueprint locally and/or customize it for your own needs you can follow these set of instructions. The installation and management of the blueprint software and hardware infrastructure are intended for on-premis deployment. 

Please note that this blueprint is designed to provide an example of integrating the workflow for developers and demonstrate key concepts and patterns. It is not a turn-key application ready for production deployment without customization.

Developers are expected to use this guide as a starting point and extend the blueprint according to their specific requirements, potentially making significant architectural or implementation changes as needed for their particular use cases.


## Workflow
![Architecture](images/RTWT_light.png)


The blueprint for a successful real-time wind tunnel digital twin requires several key components:

- Web Front-End: This interface allows users to interact with the digital twin, input parameters, and visualize results in real-time.
- Omniverse Kit CAE Application: This application provides the computational tools and environment for rendering the results within Omniverse.
- NVIDIA Inference Microservices (NIM) pre-trained automotive aerodynamics model: This is the AI surrogate model trained on computational fluid dynamics simulations. 

The core AI model used in this blueprint is available as a standalone NIM on the [NGC Catalog](https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/domino-automotive-aero) with detailed documentation available [here](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/overview.html).


## Target audience 
Setting up the digital twin requires a technical team with expertise in different areas of the software stack.

- Persona-1: End-User (e.g. design engineer)
- Persona-2: CFD Engineer
- Persona-3: Design Engineer/Creative Artist
- Persona-4: Application Developer
- Persona-5: AI Engineer

## Getting Started
 The sections below cover what is needed to start using this blueprint, they consist of:
- Prerequisites 
- Configuration
- Customization
- Evaluation 

### Prerequisites

#### Minimum System Requirements
**Hardware**
- At least 2x RTX (TM) GPUs with at least 40GB of memory each, e.g., 2xL40S or 2xA6000
- 128 GB RAM
- 32 CPU Cores
- 100 GB Storage

**OS requirements**
- Linux - Ubuntu 22.04 or 24.04

**Software Requirements**
- Git: For version control and repository management.
- Git Large File System (LFS): For large files that are too large to efficiently store in a Git repository.
- Python 3: For scripting and automation.
- Docker: For containerized development and deployment. Ensure non-root users have Docker permissions.
- NVIDIA Container Toolkit: For GPU-accelerated containerized development and deployment. Installation and configuring docker steps are required.
- build-essentials: A package that includes make and other essential tools for building applications. For Ubuntu, install with ``sudo apt-get install build-essential``

#### NVIDIA Container Toolkit
The NVIDIA Container Toolkit is a set of tools and libraries that enable GPU-accelerated applications to run in containers. It provides the necessary components and configurations to access NVIDIA GPUs within containerized environments, such as Docker or Kubernetes. This toolkit allows developers to leverage the computational power of NVIDIA GPUs for applications in AI, machine learning, data analytics, and high-performance computing, while benefiting from the portability and isolation provided by containers.

[Install NVIDIA container toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

Ensure you configure the toolkit after installing. 

#### NVIDIA GPU Cloud (NGC) Access
Follow the steps to authenticate and generate an API Key to NGC on Docker.  This is needed to check out the NIM.

[Docker with NGC](https://docs.nvidia.com/launchpad/ai/base-command-coe/latest/bc-coe-docker-basics-step-02.html)

Once you have the NGC API Key, you can export it to your environment. 

```bash
export NGC_API_KEY=<ngc-api-key>
```

By default, the environment variable will only be available in the current shell session. Run one of the following commands to make the key available at startup:

**If using bash**
```sh
echo "export NGC_API_KEY=<ngc-api-key>" >> ~/.bashrc
```

**If using zsh**
```sh
echo "export NGC_API_KEY=<ngc-api-key>" >> ~/.zshrc
```

Then source or restart your shell.

The NIM performs a runtime check for the NGC API key to ensure it is valid. Therefore, make sure to add the NGC API Key as an environment variable to allow the application to run smoothly.

Login to the NGC in order to download the necessary containers following the steps here:

[Docker NGC](https://docs.nvidia.com/launchpad/ai/base-command-coe/latest/bc-coe-docker-basics-step-01.html#installing-docker-locally)

### Configuration

#### Build the Blueprint
Clone the repository using the following command:

```sh
git clone ssh://github.com/NVIDIA-Omniverse-Blueprints/digital-twins-for-fluid-simulation $HOME/digital_twins_for_fluid_simulation
```

Change to the resulting directory:

```sh
cd $HOME/digital_twins_for_fluid_simulation
```

Run the below to build the docker containers:

```sh
./build-docker.sh
```

Copy the `.env_template` file to `.env`:

```sh
cp .env_template .env
```

#### Open Required Ports

This blueprint uses [Omniverse Kit App Streaming](https://docs.omniverse.nvidia.com/ovas/latest/index.html) and the `@nvidia/omniverse-webrtc-streaming-library` client library to stream the simulation to the client application. The following ports must be open to the client system, i.e. the system running the web browser displaying the wind tunnel:

- web: `5273/tcp, 1024/udp`
- kit: `8011/tcp, 8111/tcp, 47995-48012/tcp, 47995-48012/udp, 49000-49007/tcp, 49100/tcp, 49000-49007/udp`
- other: `1024/udp`


#### Configuration for Clouds and VPNs
Cloud-hosted systems (e.g. AWS EC2 instances) and systems on a VPN may have a public IP address that is different from the system's private IP address.  If the system is configured with both a public and a private IP address, follow the instructions below.

Get the IP address of the primary route.  This is the private IP address.
```sh
ip route get 1 | sed 's/^.*src \([^ ]*\).*$/\1/;q'
```

Use an IP address service to check the public IP address.
```sh
curl ipinfo.io/ip
```

If the public IP address matches the private IP address then no changes are needed.  Skip ahead to [Running the Blueprint](#running-the-blueprint).
If the public IP address is different from the private IP address, proceed with the changes described below.

Edit `.env` and set `ZMQ_IP` to your _private_ IP address.  For example:

```sh
# Example Only! Your private IP address may be different.
ZMQ_IP=172.31.1.144  
```

Edit `compose.yml`.  In the `kit` service definition, replace the `network_mode: host` directive with the network definition shown below.  Replace `YOUR_PUBLIC_IP_ADDRESS` with your public IP address.
```yaml
networks:
  outside:
    ipv4_address: YOUR_PUBLIC_IP_ADDRESS
```

The start of `compose.yml` will look similar to this:
```yaml
services:
  kit:
    image: "rtdt-kit-app:latest"
    restart: unless-stopped
    build:
      context: .
      dockerfile: kit-app/Dockerfile
      network: host
    privileged: true
    networks:
      outside:
        ipv4_address: 54.218.2.37  # Example Only! Your public IP address may be different.
    ports:
      - "1024:1024/udp"
      - "49100:49100/tcp"
      - "47995-48012:47995-48012/tcp"
      - "49000-49007:49000-49007/tcp"
      - "47995-48012:47995-48012/udp"
      - "49000-49007:49000-49007/udp"
```

At the bottom of `compose.yml`, add a network definition similar to what's shown below.  The subnet definition should include your _public_ IP address.  The easiest way to determine your subnet is to replace the last number in your IP address with `0` and append `/24`, e.g. `54.218.2.37` becomes `54.218.2.0/24`.
```yaml
networks:
  outside:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 54.218.2.0/24  # Example Only!  Note that this is an IP range, not just the public IP address.
```


## Running the Blueprint

*Important*: If you have not logged in to the NGC docker registry (nvcr.io), follow the instructions at https://org.ngc.nvidia.com/setup/api-keys to configure an NGC API key and use it with Docker. 

Run the below docker compose command to run the blueprint.

```sh
cd $HOME/digital_twins_for_fluid_simulation
```

Start the docker containers:

```sh
docker compose up -d
```

Wait for the blueprint to initilaize.  Initialization takes about 10 minutes for the first launch and about 2 minutes for subsequent launches.

When initialization is complete, open `http://PUBLIC_IP_ADDR_OF_THE_MACHINE:5273` in a web browser. For a locally-hosted blueprint, open http://localhost:5273/.  An IP address lookup service like http://ipinfo.io can help find the blueprint host machine's public IP address.


### Blueprint Interactive Functions

Upon launching of the blueprint the display will show the following:

![Blueprint Display](images/blueprint_launch.png)

The blueprint allows for several modifications to the sample vehicle. Once applied, the aerodynamic results of the modification (either single or combined) will be visualized in real-time. The modifications in this example include:

- **Rim Modifications:** Change the type of rims to see how they affect the vehicle's aesthetics and aerodynamics.
- **Mirrors On/Off:** Toggle the side mirrors to observe their impact on airflow and drag.
- **Spoiler On/Off:** Add or remove the rear spoiler to see how it influences downforce and stability.
- **Ride Height:** Adjust the vehicle's ground clearance to see how it affects the airflow underneath the car.
- **Speed of Wind:** Change the wind speed to simulate different driving conditions and observe the aerodynamic effects. 

All quantities displayed are averaged values.The impact of these modifications on the flow are visualized in real-time using the following tools:

- **Curve Trace:** This tool helps you trace the path of airflow around the vehicle, showing how air moves over and under the car.
- **Volume Trace:** This visualization technique shows the movement of air within a specific volume around the vehicle, helping you understand how air interacts with different parts of the car.
- **Volume Render:** This tool provides a detailed 3D visualization of the airflow, allowing you to see the direction of the air as it moves around the vehicle.
- **Slice Planes:** These are defined cross-sectional views that cut through the airflow, providing a detailed look at the air velocity at specific points around the vehicle.

There are also several predefined views you can toggle between to get different perspectives on the vehicle and its aerodynamic performance. 

## Helm Chart deployment
Testing was done using microK8s - you may need to alter the values.yaml of the helm chart based on your K8s deployment.

### Installing Microk8s (pre-req if you don’t have a k8s cluster configured)
1. Install Microk8s on your system.

    https://microk8s.io/#install-microk8s

2. Ensure the relevant add-ons are enabled:

    ```
    microk8s enable dashboard
    ```
    ```
    microk8s enable dns
    ```
    ```
    microk8s enable hostpath-storage
    ```
    ```
    microk8s enable registry:size=100Gi 
    ```
    ```
    microk8s enable gpu
    ```
3. Run a test CUDA container to ensure your cluster is working correctly. 

[Cuda Sample](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/k8s/containers/cuda-sample)

Example below (save as cuda-vector-add-test.yaml):
```
apiVersion: v1
kind: Pod
metadata:
 name: cuda-vector-add-test
 namespace: default
spec:
 restartPolicy: OnFailure
 containers:
 - name: cuda-vector-add
   image: "nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda12.5.0-ubuntu22.04"
   resources:
     limits:
       nvidia.com/gpu: 1
```
4. Run the steps below to test the pod.
```
# Deploy the test pod
microk8s kubectl apply -f cuda-vector-add-test.yaml


# Watch the pod status
microk8s kubectl get pod cuda-vector-add-test -w


# Once the pod is running, check the logs
microk8s kubectl logs cuda-vector-add-test
```
The test is successful if you see something like this:

![Image of working test pod](images/successful_test.png)

If the above doesn’t complete successfully, you have an issue with your K8s cluster. You will need to debug until the above runs successfully.

### Deploying the Helm chart
1. **Ensure you have successfully run the docker-build.sh script to create the docker containers locally.** Next, upload the containers to the microK8s registry.

```
    ##### Save images 
    docker save rtdt-kit-app:latest > rtdt-kit-app.tar 
    docker save rtdt-web-app:latest > rtdt-web-app.tar 
    docker save rtdt-zmq-service:latest > rtdt-zmq-service.tar 
        
    ##### Import to MicroK8s 
    microk8s ctr image import rtdt-kit-app.tar 
    microk8s ctr image import rtdt-web-app.tar 
    microk8s ctr image import rtdt-zmq-service.tar 
```

2. Next, we will run the script to deploy the helm chart
```
    ##### Make the script executable if it isn't already
    chmod +x deploy-k8s.sh

    ##### Deploy the chart
    ./deploy-k8s.sh
```

If using MicroK8s, you can use _microk8s dashboard-proxy_ to track the status of the rtdt pod to see if there are any errors.

![microk8s dashboard](images/microk8s.png)

4. Once deployment is complete, you can access 127.0.0.1 in your browser, and the stream should be available. (It is accessed via port 80, so you don’t need to add a port to the end of the IP)

## Known issues

 - The blueprint supports at most one client connection at a time.
 - Using a remote desktop connection can lead to a degraded experience. Factors like network latency, bandwidth limitations, and the performance of the remote machine can all contribute to issues such as slow response times, lag in mouse and keyboard actions, and poor video or audio quality.

    To address these challenges, the blueprint includes kit-app streaming. This feature allows users to experience applications on a locally-hosted browser, eliminating the need for a remote desktop connection. By running the application locally, users can enjoy smoother performance and a more responsive experience, as the local machine handles the processing and rendering tasks. This approach significantly reduces the impact of network issues and ensures a more reliable and efficient user experience.
 - There is a bug that can occur when importing local images to microk8s. This can lead to an error message similiar to the below:
    ```
    Failed to pull image "rtdt-kit-app:latest": rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/library/rtdt-kit-app:latest": failed to unpack image on snapshotter overlayfs: unexpected media type text/html for sha256:3e725b7e0d5f791ecf63653350b13bb78153b5b9bd30d408eefb57e9a07da4f2: not found
    ```

    If you run into this, please try to re-import the image and verify that the image is imported correctly by running:
    ```
    microk8s ctr image list
    ```

    The label for the imported containers should be `io.cri-containerd.image=managed` if imported correctly.
    See https://github.com/canonical/microk8s/issues/4029#issuecomment-1707974585 for additional details.
 

## Limitations
 
 - Please note that this blueprint is designed to provide an example of integrating the workflow for developers and demonstrate key concepts and patterns. It is not a turn-key application ready for production deployment without customization.
 - The DoMINO-Automotive-Aero NIM may not be suitable for all external aerodynamics use-case and developers should read the NIM details to learn about its own limitations

## Licenses

This blueprint is licensed under the Omniverse License Agreement found [here](/LICENSE.md). 
This project will download and install additional third-party open source software projects. Review the license terms of these open source projects before use.

## Troubleshooting

### Aeronim fails to start

You may encounter the following error message when attempting the `docker compose up -d` step. It indicates that you need to perform a Docker login as described at https://org.ngc.nvidia.com/setup/api-keys.

```
[+] Running 1/1
 ✘ aeronim Error unauthorized: <html>                                                                                                                                                                        0.2s
<head><title>401 Authorization Required</title></head>
<body>
<center><h1>401 Authorization Required</h1></center>
<hr><center>nginx/1.22.1</cen...                0.3s
Error response from daemon: unauthorized: <html>
<head><title>401 Authorization Required</title></head>
<body>
<center><h1>401 Authorization Required</h1></center>
<hr><center>nginx/1.22.1</center>
</body>
</html>
```

### General Debugging

You may need to check logs for troubleshooting. Do the following to do so:

##### Tail logs live
```
docker compose logs kit -f
```

```
docker compoze logs zmq -f
```

##### View the entire log in the terminal
```
docker compose logs kit | less
```

##### Dump the log to a file
```
docker compose logs kit > log.txt
```

##### Restart after zmq issues
You should restart kit after zmq issues:

```
docker compose restart kit
```

#### Ensure required files are present
1. To ensure the required files are present, check that Git LFS properly installed and configured:

    ```
    git lfs version
    ```

    ```
    git lfs status
    ```

    If an error is shown, check that Git LFS is configured correctly.

2. Verify that the files are properly tracked by Git LFS:

    ```
    git lfs ls-files | grep world_rtwt_Main_v1.usda 
    ```

    This should return the world_rtwt_Main_v1.usda file 


3. Ensure the actual file content is downloaded:

    ```
    git lfs pull
    ```

4. Check the file size  

    ```
    ls -lh rtwt-files/Collected_world_rtwt_Main_v1/world_rtwt_Main_v1.usda 
    ```

    If any of the above steps shows an error, re-download all git lfs assests:

    ```
    git lfs fetch --all
    ```
    ```
    git lfs checkout
    ```
