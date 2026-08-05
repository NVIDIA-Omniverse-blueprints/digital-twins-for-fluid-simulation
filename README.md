<h2><img align="center" src=images/NVIDIA_image.png> Omniverse Blueprint for Real-time Computer-aided Engineering Digital Twins

## Overview

The Omniverse Blueprint for Real-time Computer-aided Engineering Digital Twins offers a reference workflow for building real-time digital twins for external aerodynamic Computational Fluid Dynamics (CFD) workflows combining CUDA-X accelerated solvers, PhysicsNeMo for physics AI, and Omniverse for high quality rendering. 

This blueprint offers a comprehensive reference workflow for building real-time digital twins, specifically tailored for external aerodynamic CFD simulations. This workflow leverages CUDA-X accelerated solvers for high-performance computing, PhysicsNeMo for advanced simulation AI, and Omniverse for high-quality, real-time rendering. 

The digital twin tool is available to test either through build.nvidia.com or by deploying it yourself using this set of instructions. The build.nvidia.com version is deployed as a live, interactive blueprint on build.nvidia.com, where you can work through a pre-built environment, selecting different configurations and seeing the outputs from a real-time inference against a pre-trained machine learning (ML) model through Omniverse. If you want to deploy this blueprint locally and/or customize it for your own needs you can follow these set of instructions. The installation and management of the blueprint software and hardware infrastructure are intended for on-premises deployment.

The self-hosted blueprint ships in two Docker Compose profiles: a **standard** live-inference configuration for multi-GPU workstations, and a **lite** single-GPU configuration that serves pre-baked inference results on hardware as small as a 16 GB VRAM RTX 5080. Jump to [Deployment modes](#deployment-modes) for details; [Running the Blueprint](#running-the-blueprint) shows the invocation for each.

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

Requirements vary significantly by deployment mode; the [Running the Blueprint](#running-the-blueprint) section compares them side-by-side.

**Hardware**

- NVIDIA RTX GPU(s):
    - **Lite profile** (single-GPU, cached inference; see [Deployment modes](#deployment-modes)):
        - 1× RTX GPU with ≥ 16 GB VRAM (e.g. **RTX 5080**, RTX 4080, RTX A4500). No AeroNIM container, no second GPU.
    - **Standard profile** (live AeroNIM inference):
        - 2× RTX GPUs with at least 40 GB of memory each. For example:
            - 2× L40 or L40s
            - 2× A6000

        -OR-

        - 1× RTX GPU with > 80 GB of memory. For example:
            - RTX 6000 Pro.
            - **Note:** `CUDA_DEVICE_KIT` and `CUDA_DEVICE_AERONIM` should be set to the same value (often `0`) in this configuration.
- For detailed technical requirements, **including recommended driver versions**, for NVIDIA Omniverse, see [this page](https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html).
- **Standard profile:** 128 GB RAM, 32 CPU cores, 100 GB storage (driven by AeroNIM's model loading and Triton memory footprint).
- **Lite profile:** 16 GB RAM and 8 CPU cores are sufficient; ≥ 5 GB free storage for the baked cache plus the kit image.

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

> **Note:** NGC access is only required for the **standard** profile, which builds and runs the AeroNIM-based inference service. If you only intend to use the **lite** profile (pre-baked inference), you can skip this section.

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
Clone the repository and its submodules using the following command:

```sh
git clone --recurse-submodules https://github.com/NVIDIA-Omniverse-blueprints/digital-twins-for-fluid-simulation.git
```

Change to the resulting directory:

```sh
cd digital-twins-for-fluid-simulation
```

This repository uses the `kit-cae` submodule. If you cloned without `--recurse-submodules`, or if `kit-cae/` is missing or empty, initialize the submodules before building:

```sh
git submodule update --init --recursive
```

The submodule pins the tested Kit-CAE 3 revision from its `main` branch, and the build pulls
Kit-CAE with its associated dependencies.

Copy the `.env_template` file to `.env`:

```sh
cp .env_template .env
```

Review `.env` and decide which profile to run (see [Deployment modes](#deployment-modes)). The template defaults to `COMPOSE_PROFILES=standard`; set it to `lite` to run the offline, single-GPU stack.

The Docker images are built on first `docker compose up -d`. An explicit
`docker compose build` respects whichever profile is active in `.env`: `standard` builds Kit, web,
and AeroNIM, while `lite` builds Kit and web.

#### Open Required Ports

This blueprint uses Kit WebRTC streaming and the `@nvidia/omniverse-webrtc-streaming-library` client library to stream the simulation to the client application. The following ports must be open to the client system, i.e. the system running the web browser displaying the wind tunnel:

- Web/proxy: `80/tcp` (configurable via `RTWT_HTTP_HOST_PORT`) and optionally `443/tcp` (configurable via `RTWT_HTTPS_HOST_PORT`). The Trame service is also published directly on `WEB_HOST_PORT` for local development.
- Kit signaling fallback: `49100/tcp` if the browser connects to Kit directly instead of through the launch proxy.
- Kit media/transport: `1024/udp, 47995-48012/tcp, 47995-48012/udp, 49000-49007/tcp, 49000-49007/udp`

The standard profile also publishes Triton on `8080/tcp` for readiness checks and split-host
deployments. RTDT does not add authentication to that API; restrict it to the local host or a trusted
private network with host firewall or cloud security-group rules, and never expose it to the public
internet.


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

#### Brev Launchables

For a Brev launchable, use Docker Compose mode and point the launchable at this repo's `compose.yml`. Set `COMPOSE_PROFILES=lite` for the single-GPU offline experience, or `COMPOSE_PROFILES=standard` plus `NGC_API_KEY` for the full AeroNIM-backed stack.

Configure Brev networking as follows:

- Add a Secure Link for `RTWT_HTTP_HOST_PORT` (`80` by default). This serves the Trame UI through the launch proxy and proxies Kit's `/sign_in` signaling endpoint.
- Open the Brev Secure Link hostname, not `https://<instance-public-ip>/`. The NVIDIA WebRTC client treats IPv4 signaling hosts as plain `ws://`, which browsers block from an HTTPS page.
- Expose the Kit WebRTC media/transport ports directly: `1024/udp`, `47995-48012/tcp`, `47995-48012/udp`, `49000-49007/tcp`, and `49000-49007/udp`.
- `49100/tcp` does not need a public link when using the launch proxy, but it can be exposed for direct non-proxied debugging.

When the UI is opened through an HTTPS Secure Link, the browser client automatically uses that HTTPS host for signaling and the instance public IP for WebRTC media. If public-IP discovery is blocked in the container, set `RTWT_PUBLIC_IP` or `RTWT_MEDIA_SERVER` to the Brev instance public IP.


## Running the Blueprint

The blueprint has two deployment profiles. The same `docker compose up -d` command starts whichever one is active in `.env`.

| | **Lite profile** | **Standard profile** |
|---|---|---|
| **GPU** | 1× RTX ≥ 16 GB VRAM | 2× RTX ≥ 40 GB each, or 1× ≥ 80 GB |
| **NGC account** | Not required | Required for AeroNIM build/runtime |
| **Inference** | Pre-baked cache in `source/specializations/auto-aero/data/cache/` (shipped via Git LFS) | Live DoMINO inference via AeroNIM |
| **Controls** | Velocity + Spoiler | Velocity + Spoiler + Rims + Mirrors |

The lite profile lets the blueprint run on a single GPU (RTX 5080 or better) without NGC access. The standard profile is required to drive live inference, for example to swap in a different car model, retrain, or exercise the full parameter space. See [Deployment modes](#deployment-modes) below for cache regeneration and UI details.

### Select your profile in `.env`

Set `COMPOSE_PROFILES` at the top of `.env`:

```sh
# Full live-inference stack (kit + aeronim + web)
COMPOSE_PROFILES=standard

# or

# Offline stack (kit-lite + web), served from source/specializations/auto-aero/data/cache/
COMPOSE_PROFILES=lite
```

### Start the containers

*Standard profile only:* If you have not logged in to the NGC Docker registry (nvcr.io), do so first; see [configure an NGC API key and use it with Docker](https://org.ngc.nvidia.com/setup/api-keys). **The lite profile does not need this step.**

```sh
cd digital-twins-for-fluid-simulation
docker compose up -d
```

### First launch and subsequent launches

**The first launch in either profile takes up to ~5 minutes while the Kit app compiles shaders.** This is a one-time cost; subsequent launches reuse the cached shaders from the `ov-cache` Docker volume.

The standard profile additionally builds the custom AeroNIM image from the NGC base image if it is not already on the host, which can add another 10+ minutes depending on network speed. The lite profile has no such step.

Once shaders and images are cached locally, subsequent launches are roughly **30–60 seconds for lite** and **1–2 minutes for standard** (the latter includes AeroNIM's Triton model warm-up).

### Open the UI

When initialization is complete, open `http://PUBLIC_IP_ADDR_OF_THE_MACHINE` in a web browser. For a locally-hosted blueprint, open [localhost](http://localhost/). An IP address lookup service like [IPinfo](http://ipinfo.io) can help find the blueprint host machine's public IP address.

### Deployment modes

**Lite profile.** Skips the 39 GB AeroNIM container entirely and serves four velocities × two spoiler states (eight combinations) from a shipped cache in `source/specializations/auto-aero/data/cache/`. Rim and mirror toggles are greyed out in the UI; the frontend queries Kit on connect to learn which option values have a matching cache entry and restricts itself accordingly. The rest of the experience (streaming, camera controls, Flow / Streamlines / Volume / Slice visualization, colormaps) behaves identically to the standard profile. Every interaction hits the on-disk cache (and then the in-memory cache on repeat), so response is effectively instant: no Triton round-trip, no GPU inference run.

**Standard profile: CACHE panel.** In the standard profile the right-hand UI exposes a **CACHE** panel that walks the full combination space once, caches the results in memory for the remainder of the session, and then serves every subsequent interaction from that cache. It's a one-time warm-up that trades startup time for smoother interactive response across the full parameter space. The panel is hidden in lite (the disk cache is the single source of truth there).

**Regenerating the lite cache.** Cache entries are SHA256-keyed `.npz` files with a sibling `.json` sidecar recording the originating `RtwtInferenceAppStateAPI` values. The key covers AppState values and requested outputs, but not the underlying model payload or domain. Always bake into a new empty staging directory so an old entry cannot be mistaken for a valid hit after a model, geometry, or domain change:

1. Create an empty staging directory. Build the host app, start only AeroNIM, and launch the editor
   with an absolute staging path (the Compose data mount is read-only and can also have
   UID-mismatch issues):

   ```bash
   ./repo.sh build -r
   docker compose --profile standard up -d aeronim
   ./repo.sh launch -n omni.rtwt.editor.kit -- \
     --/exts/omni.rtwt.inference/triton_http_url=localhost:8080 \
     --/exts/omni.rtwt.inference/offline_mode=true \
     --/exts/omni.rtwt.inference/generate_if_missing=true \
     --/exts/omni.rtwt.inference/offline_cache_dir=/absolute/path/to/empty/staging-cache
   ```

2. In the editor, drive `/World/AppState` through every tuple you intend to ship. Because staging
   started empty, each tuple must miss, call Triton, and write a new `.npz`/`.json` pair.
3. Check that every hashed sidecar has a payload, every payload has a sidecar, and no two keys claim
   the same tuple. Review the printed tuples against the intended set:

   ```bash
   RTDT_STAGING_CACHE=/absolute/path/to/empty/staging-cache python - <<'PY'
   import json, os, re
   from pathlib import Path

   root = Path(os.environ["RTDT_STAGING_CACHE"])
   hashed = re.compile(r"[0-9a-f]{16}")
   json_keys = {p.stem for p in root.glob("*.json") if hashed.fullmatch(p.stem)}
   npz_keys = {p.stem for p in root.glob("*.npz") if hashed.fullmatch(p.stem)}
   if json_keys != npz_keys:
       raise SystemExit(f"unpaired cache files: json_only={sorted(json_keys - npz_keys)}, npz_only={sorted(npz_keys - json_keys)}")
   tuples = {}
   for key in sorted(json_keys):
       state = json.loads((root / f"{key}.json").read_text()).get("app_state")
       if not isinstance(state, dict):
           raise SystemExit(f"{key}.json has no app_state object")
       signature = json.dumps(state, sort_keys=True)
       if signature in tuples:
           raise SystemExit(f"duplicate tuple: {tuples[signature]} and {key}")
       tuples[signature] = key
       print(key, signature)
   print(f"validated {len(tuples)} unique cache tuples")
   PY
   ```

4. Validate every staged tuple in lite mode, plus an unsupported tuple to confirm it is rejected
   without leaving stale results. Replace the tracked 16-hex-character tuple pairs as one curated
   set rather than merging new files into old ones. Preserve or deliberately regenerate the named
   comparison files (`mock_ground_truth.*` and `diff.*`).
5. Commit the approved `.npz` files (LFS-tracked) and `.json` sidecars (plain text, diffable), then
   stop the temporary AeroNIM service with `docker compose --profile standard down`.

Do not leave obsolete `.npz`/`.json` pairs when the schema, model, domain, outputs, or supported tuple set changes. The
`get_available_options` scan aggregates every `app_state` key and value in every sidecar; it does
not filter stale entries against the current schema or manifest, so leftover sidecars can
incorrectly widen the options offered by the lite UI.

### Kubernetes deployment (Helm)

For cluster-native deployments (managed Kubernetes, on-prem clusters, etc.) a Helm chart ships under [`deploy/helm`](deploy/helm/). It mirrors the Docker Compose profiles (`lite` and `standard`) while keeping this workstation-focused Compose workflow intact for local development. See [`deploy/README.md`](deploy/README.md) for local cluster smoke testing, registry-based install commands, validation levels, and troubleshooting notes.


### Blueprint Interactive Functions

Upon launching of the blueprint the display will show the following:

![Blueprint Display](images/blueprint_launch.png)

The blueprint allows several modifications to the sample vehicle; applying any of them re-runs inference and the aerodynamic results are visualized in real-time. The available controls are:

- **Velocity:** Wind speed in m/s (25 / 50 / 75 / 100). Drag the slider to compare drag and flow regimes.
- **Spoiler On/Off:** Add or remove the rear spoiler to see its impact on the wake and downforce.
- **Mirrors On/Off:** Toggle the side mirrors to observe their effect on airflow and drag. *(Standard profile only; greyed out in the lite profile.)*
- **Rims:** Switch between Standard and Aero rims. *(Standard profile only; greyed out in the lite profile.)*

All quantities displayed are time-averaged. The flow field is visualized in real time using four techniques selectable from the **VISUALIZATION TECHNIQUES** panel:

- **Flow:** Continuous flow traces streaming across the scene, the default "look at the wake" view.
- **Streamlines:** Discrete streamlines seeded from a user-positioned plane. Toggle **Animated Streaks** to watch them evolve along the flow.
- **Volume:** IndeX volume-renders the selected field (velocity magnitude or pressure) through the simulation domain.
- **Slice:** Cross-sectional slice through the domain along the chosen axis (X / Y / Z), showing the selected field's magnitude at that plane.

When a mode exposes additional controls (field selector, slice direction, plane position, animation toggle) they appear under **VISUALIZATION ADJUSTMENT**.

A set of predefined camera views (left panel) lets you switch perspective, plus an **ORBIT** button for continuous rotation.

### Comparison view

Besides the live **Explore** view, the UI includes a **Comparison** view for a single pre-baked configuration. It shows three result sets — the surrogate prediction, a reference (mock ground-truth), and their signed difference — so you can see where the surrogate and the reference disagree. Switching between them is instant: the comparison results are served from the shipped cache, with no live inference, so the Comparison view works in both profiles.

The `RTWT_UI_PANELS` setting in `.env` selects which panels appear:

- `both` (default) — the live Explore panel and the Comparison panel
- `explore` — the Explore panel only
- `compare` — the Comparison panel only


## Known issues

 - The blueprint supports at most one client connection at a time.
 - Using a remote desktop connection can lead to a degraded experience. Factors like network latency, bandwidth limitations, and the performance of the remote machine can all contribute to issues such as slow response times, lag in mouse and keyboard actions, and poor video or audio quality.

    To address these challenges, the blueprint includes Kit application streaming. This feature allows users to experience applications on a locally-hosted browser, eliminating the need for a remote desktop connection. By running the application locally, users can enjoy smoother performance and a more responsive experience, as the local machine handles the processing and rendering tasks. This approach significantly reduces the impact of network issues and ensures a more reliable and efficient user experience.
- Visual artifacts for flow and streamlines may exist depending on `.kit` file renderer and viewport settings. In some configurations flickering and ghosting may occur.
- Renderer outputs can show inconsistent lighting results when using clear coat materials
 
 

## Limitations

- Please note that this blueprint is designed to provide an example of integrating the workflow for developers and demonstrate key concepts and patterns. It is not a turn-key application ready for production deployment without customization.
- The DoMINO-Automotive-Aero NIM (used by the standard profile) may not be suitable for all external aerodynamics use-cases; developers should read the NIM details to learn about its own limitations.
- **Lite profile** only serves the 8 combinations captured in `source/specializations/auto-aero/data/cache/` (4 velocities × spoiler on/off, with mirrors fixed at On and rims fixed at Standard). Rims and mirrors controls are disabled in the UI for values without a cache entry. Any state outside the cached set produces a logged cache-miss error; there is no AeroNIM fallback. If you need the full control surface, run the standard profile.

## Licenses

This blueprint is licensed under the Omniverse License Agreement found [here](LICENSE.md).
This project will download and install additional third-party open source software projects. Review the license terms of these open source projects before use.

## Troubleshooting

### AeroNIM fails to start (standard profile only)

You may encounter the following error message when running `docker compose up -d` with the standard profile active (`COMPOSE_PROFILES=standard` in `.env`). It indicates that you need to perform a Docker login as described at https://org.ngc.nvidia.com/setup/api-keys :

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
cached in the `ov-cache` Docker volume between runs. First-launch shader
compilation typically takes up to ~5 minutes in either profile, but can
be longer on older or lower-spec hardware. Simply leave the containers
and browser running while the shaders are compiling. It can be helpful
to run `docker compose logs -f kit` to watch the logs for progress.

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
1. Verify that the required submodule is checked out:

    ```
    git submodule status --recursive
    ```

    This should show `kit-cae` with the pinned Kit-CAE 3.0 commit hash. A leading `-` means the
    submodule is not initialized; a leading `+` means its working tree is not at the revision
    recorded by this repository. If `kit-cae/` is missing or empty, initialize the submodules:

    ```
    git submodule update --init --recursive
    ```

2. To ensure the required files are present, check that Git LFS properly installed and configured:

    ```
    git lfs version
    ```

    ```
    git lfs status
    ```

    If an error is shown, check that Git LFS is configured correctly.

3. Verify that a representative binary asset is properly tracked by Git LFS:

    ```
    git lfs ls-files | grep source/specializations/auto-aero/data/low_res/detailed_car_500/aero_suv_low.ply
    ```

    This should return the PLY path. `Main.usda` is a normal text file and is not LFS-tracked.

4. Ensure the actual file content is downloaded:

    ```
    git lfs pull
    ```

5. Check that the pulled files are real content, not small LFS pointer stubs:

    ```
    ls -lh source/specializations/auto-aero/data/low_res/detailed_car_500/aero_suv_low.ply source/specializations/auto-aero/data/cache/190801d8395215a6.npz
    ```

    Each file should be its full size (the representative PLY is about 6 MB and the cache entry is
    tens of MB). If either is only a few hundred bytes, Git LFS did not pull the content. With the
    **lite** profile also check `source/specializations/auto-aero/data/cache/` contains the
    pre-baked `.npz` files plus their `.json` sidecars.

    If any of the above steps shows an error, re-download all git lfs assets:

    ```
    git lfs fetch --all
    ```
    ```
    git lfs checkout
    ```
