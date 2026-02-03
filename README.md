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
- NVIDIA RTX GPU(s): 
    - 2x RTX GPUs with at least 40GB of memory each. For example:
        - 2xL40 or L40s
        - 2xA6000
    
    -OR-
    
    - 1x RTX GPU with >80GB of memory. For examples
        - RTX 6000 Pro. 
        - **Note** CUDA_DEVICE_KIT and CUDA_DEVICE_AERONIM should be set to the same value (often `0`), in this configuration.
- For detailed technical requirements, **including recommended driver versions**, for NVIDIA Omniverse, see [this page](https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html).
- 128 GB RAM
- 32 CPU Cores
- 100 GB Storage

**OS requirements**
- Linux - Ubuntu 22.04 or 24.04

**Software Requirements**
- [**Git**](https://git-scm.com/downloads): For version control and repository management.

- [**Git Large File System LFS**](https://git-lfs.com/): For large files that are too large to efficiently store in a Git repository.

- **Python 3**: For scripting and automation.

- [**Docker**](https://docs.docker.com/engine/install/ubuntu/): For containerized development and deployment. **Ensure non-root users have Docker permissions.**

- [**NVIDIA Container Toolkit**](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html): For GPU-accelerated containerized development and deployment. [**Installation**](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#installation) **and** [**Configuration**](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#configuration) **Docker steps are required.**

- **build-essentials**: A package that includes `make` and other essential tools for building applications.  For Ubuntu, install with `sudo apt-get install build-essential`


#### NVIDIA Container Toolkit
The NVIDIA Container Toolkit is a set of tools and libraries that enable GPU-accelerated applications to run in containers. It provides the necessary components and configurations to access NVIDIA GPUs within containerized environments, such as Docker. This toolkit allows developers to leverage the computational power of NVIDIA GPUs for applications in AI, machine learning, data analytics, and high-performance computing, while benefiting from the portability and isolation provided by containers.

[Install NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#configuration)

Ensure you perform [configuration steps](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#configuration) after installing. 

#### NVIDIA GPU Cloud (NGC) Access
Follow the steps to authenticate and generate an API Key to NGC on Docker.  This is needed to check out the NIM.

[Setup NGC API Key](https://docs.nvidia.com/ngc/latest/ngc-catalog-user-guide.html#generating-ngc-api-keys)

Once you have the NGC API Key, you can export it to your environment: 

```bash
export NGC_API_KEY=<ngc-api-key>
```

By default, the environment variable will only be available in the current shell session. Run one of the following commands to make the key available at startup:

**If using bash:**
```sh
echo "export NGC_API_KEY=<ngc-api-key>" >> ~/.bashrc
```

**If using zsh:**
```sh
echo "export NGC_API_KEY=<ngc-api-key>" >> ~/.zshrc
```

Then source or restart your shell.

The NIM performs a runtime check for the NGC API key to ensure it is valid. Therefore, make sure to add the NGC API Key as an environment variable to allow the application to run smoothly.

##### Docker Login for NGC 
To download the necessary containers following the steps here:

[Docker Login NGC](https://docs.nvidia.com/ngc/latest/ngc-catalog-user-guide.html#logging-in-to-the-ngc-container-registry)

After logging in as documented, you should see `Login Succeeded` message.

### Configuration

#### Build the Blueprint
Clone the repository using the following command:

```sh
git clone https://github.com/NVIDIA-Omniverse-blueprints/digital-twins-for-fluid-simulation.git $HOME/digital_twins_for_fluid_simulation
```

Change to the resulting directory:

```sh
cd $HOME/digital_twins_for_fluid_simulation
```

Copy the `.env_template` file to `.env`:

```sh
cp .env_template .env
```

Run the below to build the Docker containers:

```sh
./build-docker.sh
```

#### Open Required Ports

This blueprint uses [Omniverse Kit App Streaming](https://docs.omniverse.nvidia.com/ovas/latest/index.html) and the `@nvidia/omniverse-webrtc-streaming-library` client library to stream the simulation to the client application. The following ports must be open to the client system, i.e. the system running the web browser displaying the wind tunnel:

- Web: `80/tcp` (configurable via `WEB_HOST_PORT`), `1024/udp`
- Kit: `47995-48012/tcp, 47995-48012/udp, 49000-49007/tcp, 49100/tcp, 49000-49007/udp`


#### Configuration for Clouds and VPNs
Cloud-hosted systems (e.g. AWS EC2 instances) and some VPN environments may have a public IP address that is different from the system's private IP address.

This blueprint publishes the required streaming/web ports on the **host** (see [Open Required Ports](#open-required-ports)). The containers communicate with each other on the internal Docker network (`rtwt`) using service DNS names (e.g. `aeronim`), so no special container networking configuration is typically required.

1. Determine the host's private IP address:
```sh
ip route get 1 | sed 's/^.*src \([^ ]*\).*$/\1/;q'
```

2. Determine the host's public IP address (if applicable):
```sh
curl ipinfo.io/ip
```

3. Access the blueprint using the address that is reachable from your client machine:
- Local machine: `http://localhost/`
- Same LAN/VPN: `http://<HOST_PRIVATE_IP>/`
- Public internet: `http://<HOST_PUBLIC_IP>/`

4. If the page loads but streaming does not connect, verify all required TCP/UDP ports are allowed in:
- cloud security groups / firewall rules
- VPN policies


## Running the Blueprint

*Important*: If you have not logged in to the NGC Docker registry (nvcr.io), follow the instructions to [configure an NGC API key and use it with Docker](https://org.ngc.nvidia.com/setup/api-keys). 

Run the below Docker Compose command to run the blueprint:

```sh
cd $HOME/digital_twins_for_fluid_simulation
```

Start the Docker containers:

```sh
docker compose up -d
```

Wait for the blueprint to initialize.  Initialization takes about 10 minutes for the first launch and about 2 minutes for subsequent launches.

When initialization is complete, open `http://PUBLIC_IP_ADDR_OF_THE_MACHINE` in a web browser. For a locally-hosted blueprint, open [localhost](http://localhost/).  An IP address lookup service like [IPinfo](http://ipinfo.io) can help find the blueprint host machine's public IP address.


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


## Known issues

 - The blueprint supports at most one client connection at a time.
 - Using a remote desktop connection can lead to a degraded experience. Factors like network latency, bandwidth limitations, and the performance of the remote machine can all contribute to issues such as slow response times, lag in mouse and keyboard actions, and poor video or audio quality.

    To address these challenges, the blueprint includes Kit application streaming. This feature allows users to experience applications on a locally-hosted browser, eliminating the need for a remote desktop connection. By running the application locally, users can enjoy smoother performance and a more responsive experience, as the local machine handles the processing and rendering tasks. This approach significantly reduces the impact of network issues and ensures a more reliable and efficient user experience.
- Visual artifacts for flow and streamlines may exist depending on `.kit` file renderer and viewport settings. In some configurations flickering and ghosting may occur.
- Renderer outputs can show inconsistent lighting results when using clear coat materials
 
 

## Limitations
 
 - Please note that this blueprint is designed to provide an example of integrating the workflow for developers and demonstrate key concepts and patterns. It is not a turn-key application ready for production deployment without customization.
 - The DoMINO-Automotive-Aero NIM may not be suitable for all external aerodynamics use-case and developers should read the NIM details to learn about its own limitations

## Licenses

This blueprint is licensed under the Omniverse License Agreement found [here](/LICENSE.md). 
This project will download and install additional third-party open source software projects. Review the license terms of these open source projects before use.

## Troubleshooting

### Aeronim fails to start

You may encounter the following error message when attempting the `docker compose up -d` step. It indicates that you need to perform a Docker login as described at https://org.ngc.nvidia.com/setup/api-keys :

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

### Blank White, Grey, or Black Screen
If you experience a blank white screen when attempting to load the web page,
confirm that you have copied `.env_template` to `.env` and all configuration
within `.env.` is correct. Then restart the containers.

If you experience a blank grey or black screen, this usually indicates
that the shaders for the scene are still being compiled. This generally
only occurs the first time you run the blueprint, since shaders are
cached in Docker volumes between runs. Initial runs can take as long
as 30 minutes before the scene appears, depending on the system. Simply
leave the containers and browser running while the shaders are compiling.
It can be helpful to run `docker compose logs -f` to watch the logs for
progress.

### Invalid Runtime Error

If you see the following error when starting the Docker containers, it means 
that the NVIDIA Docker runtime isn't correctly setup:

```
Error response from daemon: unknown or invalid runtime name: nvidia
```

To correct this error, run the following commands to add the `nvidia`
runtime to your Docker installation:

```
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd
```

### General Debugging

You may need to check logs for troubleshooting. Do the following to do so:

##### Tail logs live:
```
docker compose logs kit -f
```

##### View the entire log in the terminal:
```
docker compose logs kit | less
```

##### Dump the log to a file:
```
docker compose logs kit > log.txt
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

4. Check the file size:

    ```
    ls -lh rtwt-files/Collected_world_rtwt_Main_v1/world_rtwt_Main_v1.usda 
    ```

    If any of the above steps shows an error, re-download all git lfs assets:

    ```
    git lfs fetch --all
    ```
    ```
    git lfs checkout
    ```
