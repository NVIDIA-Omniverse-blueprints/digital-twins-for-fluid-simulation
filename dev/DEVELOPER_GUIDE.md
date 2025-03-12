# Real-time Computer-aided Engineering Digital Twins Developer Guide

## Purpose of this Guide

This guide is intended to serve as a quick, getting-started reference for developers working with the Real-time Computer-aided Engineering Digital Twins blueprint. It is **not** an exhaustive guide on adapting the blueprint for all possible use cases.

The blueprint is designed to provide an example of integrating the workflow for developers and demonstrate key concepts and patterns. It is **not** a turn-key application ready for production deployment without customization.

Developers are expected to use this guide as a starting point and extend the blueprint according to their specific requirements, potentially making significant architectural or implementation changes as needed for their particular use cases.

## Table of Contents
1. [Introduction](#introduction)
2. [Technical Architecture](#technical-architecture)
   - [Communication Protocols](#communication-protocols)
3. [Code Structure & Key Components](#code-structure--key-components)
   - [Web Frontend (web-app/)](#web-frontend-web-app)
   - [Kit Application (kit-app/)](#kit-application-kit-app)
   - [Service Network (service_network/)](#service-network-service_network)
   - [Vehicle Data (rtwt-files/)](#vehicle-data-rtwt-files)
4. [Development Workflow](#development-workflow)
   - [Local Development Workflow](#local-development-workflow)
5. [Customizing the Application](#customizing-the-application)
   - [Adding a New Vehicle](#adding-a-new-vehicle)
     - [Vehicle Variants System](#vehicle-variants-system)
     - [STL File Naming Convention](#stl-file-naming-convention)
     - [USD File Changes](#usd-file-changes)
     - [Web App Changes](#web-app-changes)
   - [Changing the Surrogate Model](#changing-the-surrogate-model)

## Introduction

This developer guide provides technical information for developers who want to extend or modify the Real-time Computer-aided Engineering Digital Twins application. It assumes you have already read the README.md file and have a basic understanding of the project's purpose and setup requirements.

## Technical Architecture

The application follows a microservices architecture with several components that communicate through well-defined interfaces:

```
┌─────────────────┐      WebRTC      ┌─────────────────┐
│                 │◄───────────────► │                 │
│   Web Frontend  │                  │  Kit Application│
│    (React.js)   │      API         │  (Omniverse Kit)│
│                 │◄───────────────► │                 │
└─────────────────┘                  └────────┬────────┘
                                              ▲
                                              │
                                              │ ZeroMQ
                                              ▼
                                     ┌─────────────────┐
                                     │ Service Network │
                                     │    (ZeroMQ)     │
                                     └────────┬────────┘
                                              ▲
                                              │
                                              │ Triton API
                                              ▼
                                     ┌─────────────────┐
                                     │    Aero NIM     │
                                     │(Surrogate Model)│
                                     └─────────────────┘
```

### Communication Protocols

1. **Web Frontend to Kit Application**:
   - **WebRTC**: Used for streaming the 3D visualization from the Kit application to the web browser.
   - **API**: Implemented using the `OmniverseAPI` class, which provides a request-response mechanism over WebRTC data channels.

2. **Kit Application to Service Network**:
   - **ZeroMQ**: Used for high-performance, asynchronous messaging between the Kit application and the service network.

3. **Service Network to Aero NIM**:
   - **Triton Inference Server API**: Used for sending inference requests to the Aero NIM and receiving results.

## Code Structure & Key Components

### Web Frontend (web-app/)

```
web-app/
├── public/                # Static assets
├── src/
│   ├── components/        # Reusable UI components
│   ├── Menus/             # Application menu components
│   ├── OmniverseApi.ts    # Client-side API for communicating with Kit
│   ├── OmniverseStream.tsx # WebRTC streaming component
│   └── App.tsx            # Main application component
├──  package.json           # Dependencies and scripts
└── Dockerfile             # Docker build definition
```

### Kit Application (kit-app/)

```
kit-app/
├── app/                   # Application output
├── source/
│   ├── apps/              # Kit application definitions
│   │   ├── omni.rtwt.app.kit            # Main application
│   │   ├── omni.rtwt.app.webrtc.kit     # WebRTC-enabled application
│   │   └── omni.rtwt.editor.kit         # Dev Editor application
│   └── extensions/        # Custom Kit extensions
│       ├── omni.rtwt.api/               # API extension
│       │   └── omni/rtwt/api/
│       │       ├── api/                 # API implementation
│       │       │   └── rtwt.py          # Main API implementation
│       │       └── ovapi.py             # API framework
│       ├── omni.rtwt.app.setup/         # Application setup
│       ├── omni.cgns/                   # CFD data handling
│       ├── ov.cgns/                     # CGNS file format support
│       └── ov.cgns_ui/                  # UI for CGNS visualization
└── Dockerfile             # Docker build definition
```

### Service Network (service_network/)

```
service_network/
├── src_py/
│   └── inference_service/
│       ├── service.py         # Base service implementation
│       ├── service_zmq.py     # ZeroMQ service implementation
│       └── file_inference.py  # File-based inference (for testing)
├── main.py                # Service entry point
└── Dockerfile             # Docker build definition
```

### Vehicle Data (rtwt-files/)

```
rtwt-files/
├── demo_data_all/
│   └── low_res/
│       └── detailed_car_XXX/  # Vehicle model directories
│           └── aero_suv_low.stl  # Vehicle STL file
└── Collected_world_rtwt_Main_v1/  # USD scene data
```

## Development Workflow

### Local Development Workflow

For faster development iterations, you can use the scripts in the `dev` folder to build and run the application locally without rebuilding the Docker containers:

1. **Build the Application Locally**:
   ```bash
   cd dev
   ./build.sh
   ```
   This script builds the kit application and installs web app dependencies.

2. **Start Inference Components**:
   ```bash
   docker compose -f compose-inference.yml up -d
   ```
   This starts only the inference components needed for the application.

3. **Run the Kit Application and Web App**:
   You can run both applications in separate terminals:

   Terminal 1 - Run the Kit Application:
   ```bash
   ./run-kit.sh
   ```
   This runs the kit application directly on your machine, allowing for faster debugging and iteration. It will run in editor mode, allowing for easier debugging with additional UI components.

   Terminal 2 - Run the Web App:
   ```bash
   ./run-webapp.sh
   ```
   This starts the web app in development mode.

4. **Access the Application**:
   The debug web app will run on port 5173:
   ```
   http://localhost:5173/?server=127.0.0.1&width=1920&height=1080&fps=60
   ```

5. **Make Changes and Iterate**:
   You can now make changes to the kit application code and simply restart the appropriate application without having to rebuild Docker containers, significantly speeding up the development cycle.


## Customizing the Application

### Adding a New Vehicle

To add a new vehicle to the application, you need to understand the vehicle variant system and STL file naming convention.

#### Vehicle Variants System

The application uses a variant system to manage different vehicle models and their customization options. The variant system is implemented in `kit-app/source/extensions/omni.rtwt.api/omni/rtwt/api/api/rtwt.py`.

1. **Global State Management**:
   The application maintains a global state for vehicle variants in the `GlobalState` class:

   ```python
   class GlobalState:
       ZMQ_CONNECTED = False
       SLICE_AXIS_SELECTED = "X"
       RENDERING_MODE = 0
       VOLUME_GRADIENT_PRESET = 1 # 1 or 2
       VELOCITY_OR_PRESSURE = 0 # 0 for velocity, 1 for pressure
       CAR_VARIANT = DEFAULT_VEHICLE_VARIANT
       RIM_VARIANT = DEFAULT_RIM_VARIANT
       RIDE_HEIGHT_VARIANT = DEFAULT_RIDE_HEIGHT_VARIANT
       MIRROR_VARIANT = DEFAULT_MIRROR_VARIANT
       SPOILER_VARIANT = DEFAULT_SPOILER_VARIANT
       WIND_SPEED = 25.0
       # ...
   ```

2. **Vehicle Variant Constants**:
   The application defines constants for vehicle variants:

   ```python
   # Vehicle-related constants
   VEHICLES_PRIM_PATH = "/World/AllVehicles"
   VEHICLE_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles"
   VEHICLE_VARIANT_NAME = "Variant_Set"
   VEHICLE_VARIANT_VALUES = ["ConceptCar"]  # Add your new vehicle here
   ```

3. **Vehicle Customization Variants**:
   Each vehicle can have multiple customization options. Here are some of the current options for the Concept Car:

   ```python
   # Rims
   CONCEPT_RIM_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Concept_Car"
   CONCEPT_RIM_VARIANT_NAME = "Rims"
   CONCEPT_RIM_VARIANT_VALUES = ["Standard", "Aero"]

   # Mirrors
   CONCEPT_MIRROR_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Concept_Car"
   CONCEPT_MIRROR_VARIANT_NAME = "Mirrors"
   CONCEPT_MIRROR_VARIANT_VALUES = ["On", "Off"]
   #... additional variants
   ```

4. **API Methods for Variant Control**:
   The application provides API methods to control vehicle variants:

   ```python
   @app.request
   def set_rim_variant(inference_id: int) -> bool:
       # Implementation...

   @app.request
   def set_mirror_variant(inference_id: int) -> bool:
       # Implementation...

   @app.request
   def set_ride_height_variant(inference_id: int) -> bool:
       # Implementation...

   @app.request
   def set_spoiler_variant(inference_id: int) -> bool:
       # Implementation...
   ```

5. **Adding a New Vehicle Variant**:
   To add a new vehicle variant, you need to:

   - Define new constants for your vehicle's customization options:
     ```python
     # Your Vehicle Rims
     YOUR_VEHICLE_RIM_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Your_Vehicle"
     YOUR_VEHICLE_RIM_VARIANT_NAME = "Rims"
     YOUR_VEHICLE_RIM_VARIANT_VALUES = ["Standard", "Aero"]
     
     # Your Vehicle Mirrors
     YOUR_VEHICLE_MIRROR_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Your_Vehicle"
     YOUR_VEHICLE_MIRROR_VARIANT_NAME = "Mirrors"
     YOUR_VEHICLE_MIRROR_VARIANT_VALUES = ["On", "Off"]
     
     # ... other customization options
     ```

   - Add a function to apply your vehicle's variants:
     ```python
     def force_your_vehicle_variants_to_global_state():
         global GlobalState
         set_prim_variant(YOUR_VEHICLE_RIM_VARIANT_PRIM, YOUR_VEHICLE_RIM_VARIANT_NAME, 
                         YOUR_VEHICLE_RIM_VARIANT_VALUES[GlobalState.RIM_VARIANT])
         set_prim_variant(YOUR_VEHICLE_MIRROR_VARIANT_PRIM, YOUR_VEHICLE_MIRROR_VARIANT_NAME, 
                         YOUR_VEHICLE_MIRROR_VARIANT_VALUES[GlobalState.MIRROR_VARIANT])
         # ... other customization options
     ```

   - Update the `force_car_variants_to_global_state` function to include your vehicle:
     ```python
     def force_car_variants_to_global_state(car_idx: int):
         if car_idx == 500:  # Concept Car
             force_concept_variants_to_global_state()
         elif car_idx == 100:  # Your Vehicle
             force_your_vehicle_variants_to_global_state()
     ```

#### STL File Naming Convention

The application uses a specific naming convention for STL files to identify different vehicle models and their variants.

1. **STL ID Ranges and Vehicle Family Base IDs**:
   The application organizes vehicle models into ID ranges, with each vehicle family having a base ID (100, 200, 300, etc.):

   ```python
   stl_ids = (
       list(range(500, 516))    # Fifth vehicle family (base ID: 500)
   )
   ```
   Note: Currently only the ID range starting with 500 is used in the blueprint (Concept Car).

   Each range represents a family of vehicle models with different variants. The structure works as follows:
   - Base ID (e.g., 100, 200, 300): Represents the vehicle family
   - Offset from Base ID: Determined by the variant_to_index mapping

2. **Vehicle ID Calculation**:
   The final vehicle ID is calculated by adding the base ID (e.g., 100) to the variant index:

   ```python
   # Example: For the fifth vehicle family (base ID: 500)
   # with rim=1, ride_height=0, mirror=1, spoilers=0
   variant_index = variants_to_index(1, 0, 1, 0)  # Returns 5
   vehicle_id = 500 + variant_index  # Results in 505
   ```

   This means:
   - Vehicle ID 500: Fifth vehicle family with default variants (all 0)
   - Vehicle ID 505: Fifth vehicle family with rim=1, ride_height=0, mirror=1, spoilers=0
   - And so on...


3. **STL File Path Format**:
   The blueprint currently uses a specific format for STL file paths:

   ```python
   stl_path_format = "detailed_car_%d/aero_suv_low.stl"
   ```

   Where `%d` is replaced with the calculated vehicle ID (base ID + variant index).

4. **Directory Structure**:
   The STL files are organized in the `rtwt-files/demo_data_all/low_res/` directory:

   ```
   rtwt-files/
   └── demo_data_all/
       └── low_res/
           ├── detailed_car_500/  # Fifth vehicle family, default variants
           │   └── aero_suv_low.stl
           ├── detailed_car_501/  # Fifth vehicle family, mirror=1
           │   └── aero_suv_low.stl
           └── ...
   ```

5. **Adding a New Vehicle Family**:
   To add a new vehicle family, you need to:

   - Choose a base ID for your vehicle family (e.g., 100)
   - Create directories for all variants of your vehicle:
     ```
     rtwt-files/demo_data_all/low_res/detailed_car_100/aero_suv_low.stl  # Default variants
     rtwt-files/demo_data_all/low_res/detailed_car_101/aero_suv_low.stl  # mirror=1
     rtwt-files/demo_data_all/low_res/detailed_car_108/aero_suv_low.stl  # ride_height=1
     # ... and so on for all possible variants
     ```
   - Update the `stl_ids` list to include your vehicle family's ID range:
     ```python
     stl_ids = (
         list(range(500, 516)) +
         list(range(100, 124))  # Add your new vehicle family (base ID: 100)
     )
     ```

#### USD File Changes

When adding a new vehicle, you need to update the USD scene file to include your vehicle model and its variants:

1. **Add Vehicle Geometry to USD**:
   - Open the USD scene file (`rtwt-files/Collected_world_rtwt_Main_v1/world_rtwt_Main_v1.usda`) in Omniverse Kit.
   - Add your vehicle geometry under the `/World/AllVehicles/HeroVehicles` prim.
   - Create a new USD file for your vehicle (e.g., `your_vehicle.usda`) and add it as a reference under `/World/AllVehicles/HeroVehicles`.
   - Import or create the geometry for your vehicle with all its variant parts (different rims, mirrors, spoilers, etc.).
   - Use the Concept Car USD file as a reference for structure and variant setup.

2. **Set Up Variant Sets**:
   - Create variant sets for your vehicle's customization options:
     - Rims variant set with options like "Standard" and "Aero"
     - Mirrors variant set with options like "On" and "Off"
     - Spoiler variant set with options like "Off" and "On"
     - Ride Height variant set with options like "Standard", "Lowered", and "Lifted"
   - For each variant set, configure the visibility or replacement of the appropriate geometry.

3. **Add to Main Vehicle Variant Set**:
   - Add your vehicle to the main vehicle variant set at `/World/AllVehicles/HeroVehicles`.
   - In the "Variant_Set" variant set, create a new variant option with your vehicle's name.
   - Configure this variant to show your vehicle and hide other vehicles when selected.

4. **Update ActionGraphs**:
   - Locate the ActionGraphs in the USD file that control cameras and animations.
   - Update the vehicle selection ActionGraph to include your new vehicle.
   - Ensure all ActionGraph connections are properly set up for your new vehicle.
   - If your vehicle has unique animation requirements, create new ActionGraph nodes as needed.

5. **Test USD Variants and ActionGraphs**:
   - Test switching between variants in the USD editor to ensure they work correctly.
   - Verify that all combinations of variants display correctly.
   - Test the ActionGraphs to ensure proper behavior and animations.

#### Web App Changes

To integrate your new vehicle into the web app UI, the changes you need to make include:

1. **Create Vehicle Thumbnail**:
   - Create a thumbnail image for your vehicle.
   - Add it to `web-app/src/img/`.
   - Recommended size should match existing vehicle thumbnail.

2. **Update Vehicle Selection UI**:
   - Open `web-app/src/Menus/Vehicles/VehicleMenu.tsx`.
   - Import your vehicle's thumbnail image:
     ```tsx
     import yourVehicleImg from '../../img/YourVehicle.png';
     ```
   - Add your vehicle to the VehicleMenu component:
     ```tsx
     // Add a new vehicle button with thumbnail image and click handler
     // Follow the pattern of existing vehicle entries in the menu
     ```
   - Note: Ensure your vehicle's ID matches its base ID from the STL ID ranges.

3. **Update Vehicle Variants Menu**:
   - Open `web-app/src/Menus/Vehicles/VariantsMenu.tsx`.
   - The VariantsMenu component handles all vehicle customization options in one unified interface:
     - Rims selection (with visual thumbnails)
     - Mirrors toggle (on/off switch)
     - Spoilers toggle (on/off switch)
     - Ride height selection (lowered/standard/lifted radio buttons)
   - If your vehicle has different customization options, update the VariantsMenu component:
     ```tsx
     interface VariantsMenuProps {
       selectedRim: string;
       setSelectedRim: (value: string) => void;
       mirrorsOn: boolean;
       setMirrorsOn: (value: boolean) => void;
       spoilersOn: boolean;
       setSpoilersOn: (value: boolean) => void;
       rideHeight: string;
       setRideHeight: (value: string) => void;
       selectedModel: string | null;
     }
     ```
   - Add any vehicle-specific logic for enabling/disabling options:
     ```tsx
     // Example: Disable certain ride heights for specific models
     const isLiftedDisabled = selectedModel === 'Your Vehicle';
     const isLoweredDisabled = selectedModel === 'Your Vehicle';
     ```

4. **Update API Integration**:
   - The VariantsMenu integrates with the Omniverse API using these methods:
     - `set_rim_variant` (0 for Standard, 1 for Aero)
     - `set_mirror_variant` (0 for On, 1 for Off)
     - `set_spoiler_variant` (0 for Off, 1 for On)
     - `set_ride_height_variant` (0 for Standard, 1 for Lowered, 2 for Lifted)
   - Ensure your vehicle responds correctly to these API calls.
   - If your vehicle needs additional API methods, add them to both the API and the VariantsMenu component.

5. **Test the Integration**:
   - Test the complete flow from selecting your vehicle to customizing it.
   - Verify that all UI controls in the VariantsMenu work correctly with your new vehicle.
   - Check that the vehicle appears correctly in the 3D view.
   - Test that all variant combinations work as expected.
   - Make additional changes to components and menus as needed based on testing results.

### Changing the Surrogate Model

The application uses the Aero NIM (DoMINO-Automotive-Aero NIM) for aerodynamic simulation. To change the surrogate model:

1. **Prepare Your Surrogate Model**:
   - Create a containerized version of your surrogate model.
   - Ensure it exposes the same API as the Aero NIM:
     - HTTP endpoint for model metadata
     - Input format: STL files
     - Output format: Velocity, pressure, and SDF fields
   - Ideally, deploy your model using Triton for easiest integration: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/performance_tuning.html

2. **Update the Docker Compose File**:
   - Open `compose.yml`.
   - Replace the `aeronim` service with your surrogate model details:
     ```yaml
     aeronim:
       image: "your-surrogate-model-image:version"
       runtime: nvidia
       environment:
         CUDA_VISIBLE_DEVICES: "1"
         NGC_API_KEY: "${NGC_API_KEY}"
       network_mode: host
       ipc: host
       ports: 
         - "8000:8000"
     ```

3. **Update the Service Network**:
   - If your surrogate model has a different API, update the `service_network/src_py/inference_service/service.py` file to handle the new API.
   - **Important**: Your model's output data format MUST match the Aero NIM format:
     ```python
     field_names = ["coordinates", "velocity", "pressure", "sdf"]
     ```
   - The data structure, dimensions, and field names must be identical to ensure compatibility with the visualization pipeline.

4. **Test Your Integration**:
   - Build and run the application with your surrogate model.
   - Verify that the visualization works correctly with your model's output.
   - Check all visualization modes (streamlines, volume rendering, etc.) to ensure they interpret your model's data correctly.