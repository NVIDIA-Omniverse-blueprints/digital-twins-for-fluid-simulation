# Developer Scripts

This directory contains scripts for local development and testing of the Real-Time Digital Twin blueprint.

## Prerequisites

- Node.js 20.x LTS (recommended to match containerized behavior)
- NVIDIA GPU with appropriate drivers
- (Optional) Docker for running the Aero NIM container

## Scripts
These scripts can be run with or without the Aero NIM inference container. See [run-aeronim-container.sh](#run-aeronim-containersh) and [Running Without the NIM Container](#running-without-the-nim-container) for details.


### build.sh

Builds all required Kit components, USD schemas, and the web application locally.

```sh
./build.sh
```

**Note:** This script assumes `npm` is installed (preferably Node.js 20.x LTS).

### run-kit.sh

Runs the Kit application as an interactive editor. Useful for development and debugging.

```sh
./run-kit.sh
```

The editor can optionally connect to the Aero NIM container if it's running.

> ⚠️ **Caution:** Exercise care when editing the USD scene in the editor. Any saved changes will modify the USD files that the blueprint depends on and may cause issues in the full experience.

### run-webapp.sh

Runs the headless Kit application in the background and starts the web frontend on port 5273.

```sh
./run-webapp.sh
```

Access the web app at `http://localhost:5273`

### run-aeronim-container.sh

**(Optional)** Starts the Aero NIM inference container for a full local experience.

```sh
./run-aeronim-container.sh
```

**Important:** Before running this script, you must first build the Docker containers using the top-level build script:

```sh
cd ..
./build-docker.sh
```

## Running Without the NIM Container

If the Aero NIM container is not running:
- The USD stage will load and display correctly
- The web interface will function
- **Inference results will not be available** (no fluid simulation output).
> **Note:** Error messages are expected in the console when the inference service is not reachable.

## Typical Workflow

1. Build everything:
   ```sh
   ./build.sh
   ```

2. (Optional) Start the NIM container in a separate terminal:
   ```sh
   ./run-aeronim-container.sh
   ```

3. Run the editor for development:
   ```sh
   ./run-kit.sh
   ```

   Or run the full web application:
   ```sh
   ./run-webapp.sh
   ```