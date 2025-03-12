import asyncio
from typing import List
from ..ovapi import OmniverseAPI
import omni.usd
import carb
import carb.events
import omni.kit.app
import carb.settings
import omni.cgns as ocgns
import omni.kit.async_engine
import math
from pxr import Usd, UsdGeom, Gf
from omni.kit.viewport.utility import get_active_viewport
from omni.kit.window.section.common import SectionManager
from omni.kit.window.section import get_instance as get_section_instance
from omni.kit.window.section.common import (
    SETTING_SECTION_ALWAYS_DISPLAY,
    SETTING_SECTION_LIGHT,
    SETTING_SECTION_DIRECTION,
    SETTING_SECTION_ENABLED,
)

'''
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1


  /$$$$$$                                  /$$                           /$$
 /$$__  $$                                | $$                          | $$
| $$  \__/  /$$$$$$  /$$$$$$$   /$$$$$$$ /$$$$$$    /$$$$$$  /$$$$$$$  /$$$$$$   /$$$$$$$
| $$       /$$__  $$| $$__  $$ /$$_____/|_  $$_/   |____  $$| $$__  $$|_  $$_/  /$$_____/
| $$      | $$  \ $$| $$  \ $$|  $$$$$$   | $$      /$$$$$$$| $$  \ $$  | $$   |  $$$$$$
| $$    $$| $$  | $$| $$  | $$ \____  $$  | $$ /$$ /$$__  $$| $$  | $$  | $$ /$$\____  $$
|  $$$$$$/|  $$$$$$/| $$  | $$ /$$$$$$$/  |  $$$$/|  $$$$$$$| $$  | $$  |  $$$$//$$$$$$$/
 \______/  \______/ |__/  |__/|_______/    \___/   \_______/|__/  |__/   \___/ |_______/


!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
'''
app = OmniverseAPI()

# Vehicle-related constants
VEHICLES_PRIM_PATH = "/World/AllVehicles"
VEHICLE_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles"
VEHICLE_VARIANT_NAME = "Variant_Set"
VEHICLE_VARIANT_VALUES = ["ConceptCar"]

# Streamline-related constants 
STREAMLINES_PARENT_PRIM_PATH = "/World/Streamlines"
STREAMLINES_SPHERE_PRIM_PATH = "/World/Streamlines/StreamStart_sphere"
STREAMLINES_CURVES_PRIM_PATH = "/World/Streamlines/StreamLines"
STREAMLINES_POINT_CLOUD_PRIM_PATH = "/World/Streamlines/pointcloud"
STREAMLINES_MIN_RADIUS = 10.0
STREAMLINES_MAX_RADIUS = 30.0

# Smoke probe related constants
SMOKEPROBE_ROOT_PRIM_PATH = "/World/Flow_CFD"
SMOKEPROBE_SIM_PRIM_PATH = "/World/Flow_CFD/CFDResults/flowSimulate"
SMOKEPROBE_PROBES_PARENT_PRIM_PATH = "/World/Flow_CFD/CFDResults/FlowLineProbes"

# Index related constants
INDEX_ROOT_PRIM_PATH = "/World/IndeX"
INDEX_VOLUME_PRIM_PATH = "/World/IndeX/Volume"
INDEX_SLICE_X_PRIM_PATH = "/World/IndeX/Volume_SliceX"
INDEX_SLICE_Y_PRIM_PATH = "/World/IndeX/Volume_SliceY"
INDEX_SLICE_Z_PRIM_PATH = "/World/IndeX/Volume_SliceZ"
SLICE_Y_OFFSET = -45.0

# Default values
DEFAULT_WIND_SPEED = 75.0
DEFAULT_CAMERA_PRIM_PATH="/World/InteractiveCams/demoCam03"

STREAMLINES_BOUNDING_PRIM_PATH = "/World/Streamlines/SliderBounds"
SMOKEPROBE_BOUNDING_PRIM_PATH = "/World/Flow_CFD/CFDResults/SliderBounds"
INDEX_BOUNDING_PRIM_PATH = "/World/IndeX/SliderBounds"

INITIAL_SMOKE_PROBE_PCT_POS = [0.0, -1.0, -1.0]
INITIAL_STREAMLINE_PCT_POS = [-1.0, 0.0, 0.0]
INITIAL_STREAMLINE_PCT_RADIUS = 0.5
INITIAL_SLICE_PCT_POS = 0.0

# Rims
CONCEPT_RIM_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Concept_Car"
CONCEPT_RIM_VARIANT_NAME = "Rims"
CONCEPT_RIM_VARIANT_VALUES = ["Standard", "Aero"]

# Mirrors
CONCEPT_MIRROR_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Concept_Car"
CONCEPT_MIRROR_VARIANT_NAME = "Mirrors"
CONCEPT_MIRROR_VARIANT_VALUES = ["On", "Off"]

# Spoilers
CONCEPT_SPOILER_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Concept_Car"
CONCEPT_SPOILER_VARIANT_NAME = "Spoiler"
CONCEPT_SPOILER_VARIANT_VALUES = ["Off", "On"]

# Ride Height
CONCEPT_RIDE_HEIGHT_VARIANT_PRIM = "/World/AllVehicles/HeroVehicles/Concept_Car/root/Body"
CONCEPT_RIDE_HEIGHT_VARIANT_NAME = "Ride_Height"
CONCEPT_RIDE_HEIGHT_VARIANT_VALUES = ["Standard", "High"]

# Grouped by vehicle

# Rims
RIM_VARIANT_PRIMS = [
    CONCEPT_RIM_VARIANT_PRIM
]

RIM_VARIANT_NAMES = [
    CONCEPT_RIM_VARIANT_NAME
]

RIM_VARIANT_VALUES = [
    CONCEPT_RIM_VARIANT_VALUES
]

# Mirrors
MIRROR_VARIANT_PRIMS = [
    CONCEPT_MIRROR_VARIANT_PRIM
]

MIRROR_VARIANT_NAMES = [
    CONCEPT_MIRROR_VARIANT_NAME
]

MIRROR_VARIANT_VALUES = [
    CONCEPT_MIRROR_VARIANT_VALUES
]

# Spoilers
SPOILER_VARIANT_PRIMS = [
    CONCEPT_SPOILER_VARIANT_PRIM
]

SPOILER_VARIANT_NAMES = [
    CONCEPT_SPOILER_VARIANT_NAME
]

SPOILER_VARIANT_VALUES = [
    CONCEPT_SPOILER_VARIANT_VALUES
]

# Ride Height
RIDE_HEIGHT_VARIANT_PRIMS = [
    CONCEPT_RIDE_HEIGHT_VARIANT_PRIM
]

RIDE_HEIGHT_VARIANT_NAMES = [
    CONCEPT_RIDE_HEIGHT_VARIANT_NAME
]

RIDE_HEIGHT_VARIANT_VALUES = [
    CONCEPT_RIDE_HEIGHT_VARIANT_VALUES
]

DEFAULT_VEHICLE_VARIANT = 500 # Concept Car
DEFAULT_RIM_VARIANT = 0 # Standard
DEFAULT_RIDE_HEIGHT_VARIANT = 0 # Standard
DEFAULT_MIRROR_VARIANT = 0 # On
DEFAULT_SPOILER_VARIANT = 0 # Off

'''
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1


  /$$$$$$  /$$           /$$                 /$$        /$$$$$$   /$$                 /$$
 /$$__  $$| $$          | $$                | $$       /$$__  $$ | $$                | $$
| $$  \__/| $$  /$$$$$$ | $$$$$$$   /$$$$$$ | $$      | $$  \__//$$$$$$    /$$$$$$  /$$$$$$    /$$$$$$
| $$ /$$$$| $$ /$$__  $$| $$__  $$ |____  $$| $$      |  $$$$$$|_  $$_/   |____  $$|_  $$_/   /$$__  $$
| $$|_  $$| $$| $$  \ $$| $$  \ $$  /$$$$$$$| $$       \____  $$ | $$      /$$$$$$$  | $$    | $$$$$$$$
| $$  \ $$| $$| $$  | $$| $$  | $$ /$$__  $$| $$       /$$  \ $$ | $$ /$$ /$$__  $$  | $$ /$$| $$_____/
|  $$$$$$/| $$|  $$$$$$/| $$$$$$$/|  $$$$$$$| $$      |  $$$$$$/ |  $$$$/|  $$$$$$$  |  $$$$/|  $$$$$$$
 \______/ |__/ \______/ |_______/  \_______/|__/       \______/   \___/   \_______/   \___/   \_______/



!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
'''

# Global state
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
    CAR_SELECTION_EVENT = asyncio.Event()
    CAR_SELECTION_HANDLER_SUB = None
    CAR_SELECTION_QUEUE = None

def current_vehicle_idx() -> int:
    return 0
    global GlobalState
    return ((GlobalState.CAR_VARIANT - 100)//100)

def force_concept_variants_to_global_state():
    global GlobalState
    if GlobalState.RIDE_HEIGHT_VARIANT >= len(CONCEPT_RIDE_HEIGHT_VARIANT_VALUES):
        GlobalState.RIDE_HEIGHT_VARIANT = 0
    set_prim_variant(CONCEPT_RIM_VARIANT_PRIM, CONCEPT_RIM_VARIANT_NAME, CONCEPT_RIM_VARIANT_VALUES[GlobalState.RIM_VARIANT])
    set_prim_variant(CONCEPT_MIRROR_VARIANT_PRIM, CONCEPT_MIRROR_VARIANT_NAME, CONCEPT_MIRROR_VARIANT_VALUES[GlobalState.MIRROR_VARIANT])
    set_prim_variant(CONCEPT_SPOILER_VARIANT_PRIM, CONCEPT_SPOILER_VARIANT_NAME, CONCEPT_SPOILER_VARIANT_VALUES[GlobalState.SPOILER_VARIANT])
    set_prim_variant(CONCEPT_RIDE_HEIGHT_VARIANT_PRIM, CONCEPT_RIDE_HEIGHT_VARIANT_NAME, CONCEPT_RIDE_HEIGHT_VARIANT_VALUES[GlobalState.RIDE_HEIGHT_VARIANT])

def force_car_variants_to_global_state(car_idx: int):
    force_concept_variants_to_global_state()

def reset_global_variant_state():
    global GlobalState
    GlobalState.CAR_VARIANT = DEFAULT_VEHICLE_VARIANT
    GlobalState.RIM_VARIANT = DEFAULT_RIM_VARIANT
    GlobalState.MIRROR_VARIANT = DEFAULT_MIRROR_VARIANT
    GlobalState.SPOILER_VARIANT = DEFAULT_SPOILER_VARIANT
    GlobalState.RIDE_HEIGHT_VARIANT = DEFAULT_RIDE_HEIGHT_VARIANT

def get_current_car_inference_id():
    global GlobalState
    return GlobalState.CAR_VARIANT + variants_to_index(rim = GlobalState.RIM_VARIANT, ride_height=GlobalState.RIDE_HEIGHT_VARIANT, mirror=GlobalState.MIRROR_VARIANT, spoilers=GlobalState.SPOILER_VARIANT)

def variants_to_index(rim: int, ride_height: int, mirror: int, spoilers: int) -> int:
    return 1 * mirror + 2 * spoilers + 4 * rim + 8 * ride_height

def get_current_wind_speed() -> int:
    global GlobalState
    return int(GlobalState.WIND_SPEED)


'''
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1

  /$$$$$$   /$$$$$$  /$$   /$$  /$$$$$$
 /$$__  $$ /$$__  $$| $$$ | $$ /$$__  $$
| $$  \__/| $$  \__/| $$$$| $$| $$  \__/
| $$      | $$ /$$$$| $$ $$ $$|  $$$$$$
| $$      | $$|_  $$| $$  $$$$ \____  $$
| $$    $$| $$  \ $$| $$\  $$$ /$$  \ $$
|  $$$$$$/|  $$$$$$/| $$ \  $$|  $$$$$$/
 \______/  \______/ |__/  \__/ \______/


!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
'''

def send_message( message):
    print(f"[UI] Sending message: {message}")   
    INFERENCE_COMPLETE_EVENT= carb.events.type_from_string("inference_complete_signal_kit")
    # Publish event with payload
    bus = omni.kit.app.get_app().get_message_bus_event_stream()
    bus.push(INFERENCE_COMPLETE_EVENT, payload={"message": message})

def get_cgns_ui_extension_instance():
    import ov.cgns_ui.extension
    return ov.cgns_ui.extension.MyExtension.instance

def init_cgns_service():
    global GlobalState
    icgns = ocgns.get_interface()
    service_config = ocgns.ServiceConfig()
    service_config.from_files = False
    GlobalState.ZMQ_CONNECTED = icgns.init_service(True, service_config)
    if not GlobalState.ZMQ_CONNECTED:
        carb.log_error("Could not acquire CGNS backend service")

def update_cgns_service(point_scale: float = 1.0):
    if not GlobalState.ZMQ_CONNECTED:
        init_cgns_service()
    if not GlobalState.ZMQ_CONNECTED:
        return
    config = ocgns.RequestConfig()
    config.id = get_current_car_inference_id()
    config.config = get_current_wind_speed()
    config.multip = point_scale
    icgns = ocgns.get_interface()
    icgns.request_config(config)
    get_cgns_ui_extension_instance()._should_upload_vdb_to_gpu = True
    carb.log_warn(f"Requesting inferencing for config {config.id} and speed {config.config}")
    send_message("inference_start")

'''
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1


 $$$$$$\  $$$$$$$\ $$$$$$\
$$  __$$\ $$  __$$\\_$$  _|
$$ /  $$ |$$ |  $$ | $$ |
$$$$$$$$ |$$$$$$$  | $$ |
$$  __$$ |$$  ____/  $$ |
$$ |  $$ |$$ |       $$ |
$$ |  $$ |$$ |     $$$$$$\
\__|  \__|\__|     \______|


!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
'''

@app.request
def set_interactive_camera(camera_prim_path: str) -> bool:
    # See the action graph under /World/CameraGraphs/CameraController
    switch_cam_msg  = carb.events.type_from_string("switchCamera")
    omni.kit.app.get_app().get_message_bus_event_stream().push(switch_cam_msg, payload={"targetCamera": camera_prim_path})
    return True

@app.request
def reset() -> bool:
    '''
    Reset the application state to defaults
    These defaults should match whatever the defaults in the web application are
    '''
    init_cgns_service()
    reset_global_variant_state()
    select_car_impl(DEFAULT_VEHICLE_VARIANT, reset_rendering_mode=0)
    initialize_interactive_camera_system()
    set_interactive_camera(DEFAULT_CAMERA_PRIM_PATH)
    set_visualization_attribute_state(0) # Velocity
    set_wind_speed(DEFAULT_WIND_SPEED)
    set_gradient_scale(0.0, 150.0)
    set_smokeprobes_pos(INITIAL_SMOKE_PROBE_PCT_POS)
    set_streamlines_pos(INITIAL_STREAMLINE_PCT_POS)
    set_streamlines_radius(INITIAL_STREAMLINE_PCT_RADIUS)
    return True

@app.request
def select_car(cgns_idx: int, reset_rendering_mode: int = -1) -> bool:
    enqueue_async_car_selection_request(cgns_idx=cgns_idx)
    return True

def select_car_impl(cgns_idx: int, reset_rendering_mode: int = -1) -> bool:
    '''
    Set the car state:

    cgns_idx = 100 -> Truck
    cgns_idx = 200 -> SUV
    cgns_idx = 300 -> Electric
    cgns_idx = 400 -> Sedan
    cgns_idx = 500 -> Concept

    Note that this function is much more complicated than just switching out the car variant, it also:
    - Updates all the vehicle part variants to match the current global state
    - Updates the inference request
    - Animates the car down, swaps the car variant, then animates the car back up
    - It tries to time all this using frame delays

    If you need to tweak the timings of the car animation, this is the right place
    '''
    async def async_impl():
        global GlobalState
        GlobalState.CAR_SELECTION_EVENT.clear()
        # If we switch FROafrom  or to the concept car (500), reset the ride height
        # Search the codebase for the corresponding code on the web side: 8762837872
        CONCEPT_CAR_ID = 500
        if GlobalState.CAR_VARIANT == CONCEPT_CAR_ID or cgns_idx == CONCEPT_CAR_ID:
            GlobalState.RIDE_HEIGHT_VARIANT = 0
        GlobalState.CAR_VARIANT = cgns_idx
        current_rendering_mode = GlobalState.RENDERING_MODE if reset_rendering_mode == -1 else reset_rendering_mode
        carb.log_info(f'User selected car: "{cgns_idx}"')
        carb.log_info(f"Beginning animation sequence")
        # Set the car variants for the selected car and update inferencing
        force_car_variants_to_global_state(GlobalState.CAR_VARIANT)
        update_cgns_service()
        # 1. Disable rendering modes
        carb.log_info("1. Disable visualizations")
        set_rendering_mode(-1)
        await wait_for_frames(30)
        # 2. Make the car go down and wait 1 second
        msg = carb.events.type_from_string("carSwap")
        carb.log_info("2. Animate the vehicle platform down")
        omni.kit.app.get_app().get_message_bus_event_stream().push(msg, payload={ })
        await wait_for_frames(240)
        # 3. Swap the variant, wait 1 second
        set_prim_variant(VEHICLE_VARIANT_PRIM, VEHICLE_VARIANT_NAME, VEHICLE_VARIANT_VALUES[current_vehicle_idx()])
        carb.log_info("3. Swap var variant")
        await wait_for_frames(60)
        # 4. Make the car go up, wait 1 second
        carb.log_info("4. Animate the vehicle platform up")
        omni.kit.app.get_app().get_message_bus_event_stream().push(msg, payload={ })
        await wait_for_frames(180)
        # 5. Enable rendering mode again
        carb.log_info("5. Enable visualizations")
        set_rendering_mode(current_rendering_mode)
        await wait_for_frames(10)
        GlobalState.CAR_SELECTION_EVENT.set()
    run_task_and_block(async_impl)
    return True

@app.request
def set_rim_variant(inference_id: int) -> bool:
    '''
    Set the rim state:

    inference_id = 0 -> Default/Standard
    inference_id = 1 -> Aero
    '''
    global GlobalState
    GlobalState.RIM_VARIANT = inference_id
    vehicle_idx = current_vehicle_idx()
    set_prim_variant(RIM_VARIANT_PRIMS[vehicle_idx], RIM_VARIANT_NAMES[vehicle_idx], RIM_VARIANT_VALUES[vehicle_idx][inference_id])
    update_cgns_service()
    return True

@app.request
def set_mirror_variant(inference_id: int) -> bool:
    '''
    Set the mirror state:

    inference_id = 0 -> On
    inference_id = 1 -> Off
    '''
    global GlobalState
    GlobalState.MIRROR_VARIANT = inference_id
    vehicle_idx = current_vehicle_idx()
    set_prim_variant(MIRROR_VARIANT_PRIMS[vehicle_idx], MIRROR_VARIANT_NAMES[vehicle_idx], MIRROR_VARIANT_VALUES[vehicle_idx][inference_id])
    update_cgns_service()
    return True

@app.request
def set_ride_height_variant (inference_id: int) -> bool:
    '''
    Set the ride height state:

    inference_id = 0 -> Standard
    inference_id = 1 -> Low
    inference_id = 2 -> High

    Note that not all cars have all 3 variants
    '''
    global GlobalState
    # HACK:
    # The concept car only has standard and high, and the inferencing backend (and our RIDE_HEIGHT_VARIANT_VALUES[vehicle_idx] array)
    # expects high to be a index 1 rather than 2, but the UI passes a value of 2.
    # Rather than propogate this inconsistency into the UI, we simply specail case it here.
    CONCEPT_CAR_VARIANT_ID = 500
    if GlobalState.CAR_VARIANT == CONCEPT_CAR_VARIANT_ID and inference_id == 2:
        inference_id = 1
    GlobalState.RIDE_HEIGHT_VARIANT = inference_id
    vehicle_idx = current_vehicle_idx()
    set_prim_variant(RIDE_HEIGHT_VARIANT_PRIMS[vehicle_idx], RIDE_HEIGHT_VARIANT_NAMES[vehicle_idx], RIDE_HEIGHT_VARIANT_VALUES[vehicle_idx][inference_id])
    update_cgns_service()
    return True

@app.request
def set_spoiler_variant (inference_id: int) -> bool:
    '''
    Set the spoiler state:

    inference_id = 0 -> Off
    inference_id = 1 -> On
    '''
    global GlobalState
    GlobalState.SPOILER_VARIANT = inference_id
    vehicle_idx = current_vehicle_idx()
    set_prim_variant(SPOILER_VARIANT_PRIMS[vehicle_idx], SPOILER_VARIANT_NAMES[vehicle_idx], SPOILER_VARIANT_VALUES[vehicle_idx][inference_id])
    update_cgns_service()
    return True

@app.request
def set_prim_variant(prim_path: str, variant_set_name: str, variant_value: str) -> bool:
    '''
    Set the prim variant for the prim specified by prim_path
    '''
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        carb.log_error(f"Could not set_prim_variant for {prim_path}, prim not found")
        raise RuntimeError(f"prim path '{prim_path}' not found")
    variant_set = prim.GetVariantSets().GetVariantSet(variant_set_name)
    if variant_set:
        variant_set.SetVariantSelection(variant_value)
    else:
        carb.log_error(
            f"Could not set_prim_variant for '{prim_path}', variant set name '{variant_set_name}' not found"
        )
        raise RuntimeError(
            f"variant set name '{variant_set_name}' for '{prim_path}' not found"
        )
    return True

@app.request
def set_viewport_camera(prim_path: str) -> bool:
    '''
    Set the current viewport camera to the camera specifiec by prim_path
    '''
    stage = omni.usd.get_context().get_stage()
    if not stage.GetPrimAtPath(prim_path):
        carb.log_error(f"Could not set_camera_view to {prim_path}, prim not found")
        raise RuntimeError(f"Camera prim path '{prim_path}' not found")
    viewport = get_active_viewport()
    if not viewport:
        raise RuntimeError("No active Viewport")
    viewport.camera_path = prim_path
    return True

@app.request
def set_rendering_mode(mode: int) -> bool:
    '''
    Set the exclusive rendering mode:
    mode = 0 -> Render Flow smoke probes
    mode = 1 -> Render Warp stream lines
    mode = 2 -> Render IndeX Volume data
    mode = 3 -> Render IndeX Slice data
    '''
    global GlobalState
    # Do nothing if the user requested the same rendering mode
    # if mode == RENDERING_MODE:
    #     return True
    GlobalState.RENDERING_MODE = mode
    # smoke probes
    if mode == 0:
        disable_streamline_mode()
        disable_index_mode()
        disable_slice_mode()

        # NOTE: Hard toggle the smoke probe mode by first disabling it
        async def toggle_smoke_probe():
            disable_smokeprobe_mode()
            await wait_for_frames(5)
            enable_smokeprobe_mode()

        run_task_and_block(toggle_smoke_probe)
    # stream lines
    elif mode == 1:
        disable_index_mode()
        disable_smokeprobe_mode()
        disable_slice_mode()
        enable_streamline_mode()
    # index
    elif mode == 2:
        disable_streamline_mode()
        disable_smokeprobe_mode()
        disable_slice_mode()
        enable_index_mode()
    # section mode (still index)
    elif mode == 3:
        disable_streamline_mode()
        disable_smokeprobe_mode()
        disable_index_mode()
        enable_slice_mode()
    # disable
    else:
        disable_streamline_mode()
        disable_slice_mode()
        disable_index_mode()
        disable_smokeprobe_mode()
    return True

@app.request
def set_visualization_attribute_state(attribute: int) -> bool:
    '''
    Set the attribute to render, currently only supports Velocity and Pressure
    attribute = 0 -> Velocity
    attribute = 1 -> Pressure
    '''
    global GlobalState
    GlobalState.VELOCITY_OR_PRESSURE = attribute
    is_pressure = attribute == 1
    if is_pressure:
        # IndeX
        set_prim_rel(INDEX_VOLUME_PRIM_PATH,  "material:binding", f"{INDEX_VOLUME_PRIM_PATH}/MaterialPressure_Preset01")
        set_prim_rel(INDEX_SLICE_X_PRIM_PATH, "material:binding", f"{INDEX_ROOT_PRIM_PATH}/SliceMaterial_Pressure")
        set_prim_rel(INDEX_SLICE_Y_PRIM_PATH, "material:binding", f"{INDEX_ROOT_PRIM_PATH}/SliceMaterial_Pressure")
        set_prim_rel(INDEX_SLICE_Z_PRIM_PATH, "material:binding", f"{INDEX_ROOT_PRIM_PATH}/SliceMaterial_Pressure")

        # Flow
        ## Disable Velocity
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen", "layer", 0)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender", "layer", 0)
        set_prim_attribute("/World/Flow_CFD/CFDResults/VDB/flowEmitterNanoVdb_velocity", "enabled", False)
        ## Enable Pressure
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen_pressure", "layer", 2)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender_pressure", "layer", 2)
        set_prim_attribute("/World/Flow_CFD/CFDResults/VDB/flowEmitterNanoVdb_pressure", "enabled", True)
    else:
        # IndeX
        set_prim_rel(INDEX_VOLUME_PRIM_PATH,  "material:binding", f"{INDEX_VOLUME_PRIM_PATH}/MaterialVelocity_Preset01")
        set_prim_rel(INDEX_SLICE_X_PRIM_PATH, "material:binding", f"{INDEX_ROOT_PRIM_PATH}/SliceMaterial_Velocity")
        set_prim_rel(INDEX_SLICE_Y_PRIM_PATH, "material:binding", f"{INDEX_ROOT_PRIM_PATH}/SliceMaterial_Velocity")
        set_prim_rel(INDEX_SLICE_Z_PRIM_PATH, "material:binding", f"{INDEX_ROOT_PRIM_PATH}/SliceMaterial_Velocity")

        # Flow
        ## Enable Velocity
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen", "layer", 2)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender", "layer", 2)
        set_prim_attribute("/World/Flow_CFD/CFDResults/VDB/flowEmitterNanoVdb_velocity", "enabled", True)
        ## Disable Pressure
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen_pressure", "layer", 0)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender_pressure", "layer", 0)
        set_prim_attribute("/World/Flow_CFD/CFDResults/VDB/flowEmitterNanoVdb_pressure", "enabled", False)
    return True

@app.request
def set_streamlines_pos(pct: List[float]) -> bool:
    '''
    Set the position of the streamline sphere:

    pct = [x,y,z] where each component is a % value
    x -> [-1, 1]
    y -> [-1, 1]
    z -> [-1, 1]

    and the % value determines where to position the prim within the bounds of the prim at STREAMLINES_BOUNDING_PRIM_PATH
    '''
    pos = calculate_local_pos_in_bounds([STREAMLINES_BOUNDING_PRIM_PATH], pct)
    set_prim_attribute(STREAMLINES_SPHERE_PRIM_PATH, "xformOp:translate", pos)
    return True

@app.request
def set_streamlines_radius(pct: float) -> bool:
    '''
    Set the radius of the streamline sphere as a % [0.0, 1.0]
    As the radius changes, update the number of streamlines that originate from the sphere.
    '''
    # Calculate radius
    radius = STREAMLINES_MIN_RADIUS + pct * (STREAMLINES_MAX_RADIUS - STREAMLINES_MIN_RADIUS)
    set_prim_attribute(STREAMLINES_SPHERE_PRIM_PATH, "radius", radius)
    # Calculate the number of stream lines that should originate from the sphere
    # based on the radius.
    k = 25
    reference_radius = STREAMLINES_MIN_RADIUS
    total_point_count = k * (radius / reference_radius) ** 2
    grid_x = math.floor(math.sqrt(total_point_count))
    grid_y = grid_x
    get_cgns_ui_extension_instance()._gridX = grid_x
    get_cgns_ui_extension_instance()._gridY = grid_y
    return True

@app.request
def set_smokeprobes_pos(pct: List[float]) -> bool:
    '''
    Set the position of the smoke probe emitters:

    pct = [x,y,z] where each component is a % value
    x -> [-1, 1]
    y -> [-1, 1]
    z -> [-1, 1]

    and the % value determines where to position the prim within the bounds of the prim at SMOKEPROBE_BOUNDING_PRIM_PATH
    '''
    pos = calculate_local_pos_in_bounds([SMOKEPROBE_BOUNDING_PRIM_PATH], pct)
    set_prim_attribute(SMOKEPROBE_PROBES_PARENT_PRIM_PATH, "xformOp:translate", pos)
    return True

@app.request
def set_wind_speed(speed: float, point_scale: float = 1.0) -> bool:
    """Updates the wind speed and triggers an inference request update."""
    global GlobalState
    GlobalState.WIND_SPEED = speed
    update_cgns_service(point_scale=point_scale)
    return True

@app.request
def set_slice_state(state: str) -> bool:
    '''
    Set the state of the IndeX Slice rendering visualization
    This manages the state of both the IndeX Slice Volume prims AND the section tool state
    '''
    global GlobalState
    section_manager = SectionManager()
    section_manager.get_section_widget_prim(True)
    settings = carb.settings.get_settings()
    settings.set(SETTING_SECTION_ENABLED, state != "clear")
    if state == "X" or state == "x":
        GlobalState.SLICE_AXIS_SELECTED = "x"
        settings.set(SETTING_SECTION_DIRECTION, 1)
        section_manager.align_widget("x")
        set_prim_visibility(INDEX_SLICE_X_PRIM_PATH, True)
        set_prim_visibility(INDEX_SLICE_Y_PRIM_PATH, False)
        set_prim_visibility(INDEX_SLICE_Z_PRIM_PATH, False)
    elif state == "Y" or state == "y":
        GlobalState.SLICE_AXIS_SELECTED = "y"
        settings.set(SETTING_SECTION_DIRECTION, 1)
        section_manager.align_widget("z")
        set_prim_visibility(INDEX_SLICE_X_PRIM_PATH, False)
        set_prim_visibility(INDEX_SLICE_Z_PRIM_PATH, True)
        set_prim_visibility(INDEX_SLICE_Y_PRIM_PATH, False)
    elif state == "Z" or state == "z":
        GlobalState.SLICE_AXIS_SELECTED = "z"
        settings.set(SETTING_SECTION_DIRECTION, 0)
        section_manager.align_widget("y")
        set_prim_visibility(INDEX_SLICE_X_PRIM_PATH, False)
        set_prim_visibility(INDEX_SLICE_Y_PRIM_PATH, True)
        set_prim_visibility(INDEX_SLICE_Z_PRIM_PATH, False)
    elif state == "clear":
        set_prim_visibility(INDEX_SLICE_X_PRIM_PATH, False)
        set_prim_visibility(INDEX_SLICE_Y_PRIM_PATH, False)
        set_prim_visibility(INDEX_SLICE_Z_PRIM_PATH, False)
    set_slice_pos(INITIAL_SLICE_PCT_POS)
    return True

@app.request
def set_slice_pos(pct: float) -> bool:
    """
    Set the position of the current selected slice axis along the oriented axis at the specified pct

    This positions both the IndeX Slice plane prim AND the section tool widget
    """
    global GlobalState
    section_manager = SectionManager()
    section_manager.get_section_widget_prim(True)
    bounding_prims = [INDEX_BOUNDING_PRIM_PATH]
    if GlobalState.SLICE_AXIS_SELECTED == "x":
        section_pos = calculate_world_pos_in_bounds(bounding_prims, [pct, 0.0, 0.0])
        slice_pos = calculate_local_pos_in_bounds(bounding_prims, [0.0, -(pct + 0.5), -0.5])
        section_manager.set_widget_position(section_pos)
        set_prim_attribute(INDEX_SLICE_X_PRIM_PATH, "xformOp:translate", slice_pos)
    elif GlobalState.SLICE_AXIS_SELECTED == "y":
        section_pos = calculate_world_pos_in_bounds(bounding_prims, [0.0, 0.0, pct])
        slice_pos = calculate_local_pos_in_bounds(bounding_prims, [0.0, 0.5, pct])
        section_manager.set_widget_position(section_pos)
        set_prim_attribute(INDEX_SLICE_Z_PRIM_PATH, "xformOp:translate", slice_pos)
    elif GlobalState.SLICE_AXIS_SELECTED == "z":
        section_pos = calculate_world_pos_in_bounds(bounding_prims, [0.0, pct, 0.0])
        slice_pos = calculate_local_pos_in_bounds(bounding_prims, [pct, 0.0, -0.5])
        section_manager.set_widget_position(section_pos)
        set_prim_attribute(INDEX_SLICE_Y_PRIM_PATH, "xformOp:translate", slice_pos)
    return True

@app.request
def set_gradient_scale(min_val: float, max_val: float) -> bool:
    """
    Update the color domains across all visualizations whenever the gradient scale changes
    """
    global GlobalState
    is_pressure = GlobalState.VELOCITY_OR_PRESSURE == 1
    carb.log_info(f"set_gradient_scale(min_val={min_val}, max_val={max_val})")
    if is_pressure:
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender/rayMarch", "colormapXMin", min_val)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender/rayMarch", "colormapXMax", max_val)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen/shadow", "colormapXMin", min_val)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen/shadow", "colormapXMax", max_val)
        set_prim_attribute("/World/IndeX/Volume/MaterialPressure_Preset01/Colormap", "domain", Gf.Vec2f([min_val, max_val]))
    else:
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender/rayMarch", "colormapXMin", min_val)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowRender/rayMarch", "colormapXMax", max_val)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen/shadow", "colormapXMin", min_val)
        set_prim_attribute("/World/Flow_CFD/CFDResults/flowOffscreen/shadow", "colormapXMax", max_val)
        set_prim_attribute("/World/IndeX/Volume/MaterialVelocity_Preset01/Colormap", "domain", Gf.Vec2f([min_val, max_val]))
    return True

@app.signal
def inference_complete(**kwargs):
        print(f"Inference Complete: {kwargs}")

        message = kwargs.get("message")

        if message is not None:
            return message

        return 'error'

'''
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1


 /$$   /$$ /$$$$$$$$ /$$$$$$ /$$        /$$$$$$
| $$  | $$|__  $$__/|_  $$_/| $$       /$$__  $$
| $$  | $$   | $$     | $$  | $$      | $$  \__/
| $$  | $$   | $$     | $$  | $$      |  $$$$$$
| $$  | $$   | $$     | $$  | $$       \____  $$
| $$  | $$   | $$     | $$  | $$       /$$  \ $$
|  $$$$$$/   | $$    /$$$$$$| $$$$$$$$|  $$$$$$/
 \______/    |__/   |______/|________/ \______/


!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1
'''



def run_task_and_block(fn):
    omni.kit.async_engine.run_coroutine(fn())

def initialize_interactive_camera_system():
    # See the action graph under /World/CameraGraphs/SystemStartup
    start_msg  = carb.events.type_from_string("startConfig")
    omni.kit.app.get_app().get_message_bus_event_stream().push(start_msg, payload={})

def initialize_aysnc_car_selction_handler():
    global GlobalState
    update_stream = omni.kit.app.get_app().get_update_event_stream()
    GlobalState.CAR_SELECTION_HANDLER_SUB = update_stream.create_subscription_to_pop(async_car_selection_handler, name="omni.rtwt.api.async_car_handler")
    GlobalState.CAR_SELECTION_EVENT.set()

def deinitialize_aysnc_car_selction_handler():
    global GlobalState
    if GlobalState.CAR_SELECTION_HANDLER_SUB is not None:
        GlobalState.CAR_SELECTION_HANDLER_SUB.unsubscribe()

def enqueue_async_car_selection_request(cgns_idx: int):
    global GlobalState
    GlobalState.CAR_SELECTION_QUEUE = cgns_idx
    return

def async_car_selection_handler(_event):
    global GlobalState
    if not GlobalState.CAR_SELECTION_EVENT.is_set():
        return
    if GlobalState.CAR_SELECTION_QUEUE is not None:
        cgns_idx = GlobalState.CAR_SELECTION_QUEUE
        GlobalState.CAR_SELECTION_QUEUE = None
        select_car_impl(cgns_idx=cgns_idx)
    return

def deinitialize() -> bool:
    deinitialize_aysnc_car_selction_handler()

def initialize() -> bool:
    """
    Called by the kit app on initial load once
    """

    async def async_init():
        carb.log_info("car_controller initializing")
        global GlobalState
        # HACK:
        # Need to toggle the section tool window at least once
        # to make sure set_slice_state works
        # While it's open, set any relevant settings
        # Wait a few frames before closing it
        initialize_aysnc_car_selction_handler()
        settings = carb.settings.get_settings()
        get_section_instance().show_window(None, True)
        settings.set(SETTING_SECTION_ALWAYS_DISPLAY, False)
        settings.set(SETTING_SECTION_ENABLED, False)
        settings.set(SETTING_SECTION_LIGHT, False)
        await wait_for_frames(10)
        get_section_instance().show_window(None, False)

        # Start the zmq client and set the app state
        # Flipped true for the new data, false for the old data
        flipped = True
        sdf_range = [-10.0, 0.0] if flipped else [0.0, 10.0]
        settings = carb.settings.get_settings()
        settings.set("exts/omni.cgns/distance_ranges", sdf_range)
        initialize_streamline_mode()
        reset()
        await wait_for_frames(1000)

    run_task_and_block(async_init)
    return True

def initialize_streamline_mode():
    """
    One time initialization just for the streamlines
    """
    ext = get_cgns_ui_extension_instance()
    ext.generateStreamStartPrim("sphere", True)
    '''
    From Rob:
    ---
    radius = 0.6
    segment length = 0.1
    segment count = 500
    curve count = radius * 4
    '''
    ext._crvWidth = 0.6
    ext._crvResolution = 0.1
    ext._crvSegments = 500
    # Make sure the streamlines prim as an xform op on it
    # so we can set the translate on it
    stage = omni.usd.get_context().get_stage()
    try:
        prim = stage.GetPrimAtPath(STREAMLINES_SPHERE_PRIM_PATH)
        prim = UsdGeom.Xformable(prim)
        prim.AddTranslateOp().Set((0, 0, 0))
        prim.AddRotateXYZOp().Set((0, 0, 0))
        prim.AddScaleOp().Set((1, 1, 1))
    except:
        pass

    try:
        prim = stage.GetPrimAtPath(STREAMLINES_PARENT_PRIM_PATH)
        prim = UsdGeom.Xformable(prim)
        prim.AddTranslateOp().Set((0, 0, 0))
        prim.AddRotateXYZOp().Set((0, 0, 0))
        prim.AddScaleOp().Set((1, 1, 1))
    except:
        pass

async def wait_for_frames(n: int):
    carb.log_info(f"Waiting for {n} frames...")
    for i in range(0, n):
        await omni.kit.app.get_app().next_update_async()
    return
def enable_streamline_mode():
    carb.log_info("Enabling streamline mode")
    get_cgns_ui_extension_instance()._toggle_objects_changed_listener(True)
    # set_streamlines_pos(INITIAL_STREAMLINE_PCT_POS)

    # Show the stream line prims
    try:
        set_prim_active(STREAMLINES_CURVES_PRIM_PATH, True)
        set_prim_visibility(STREAMLINES_CURVES_PRIM_PATH, True)
        set_prim_visibility(STREAMLINES_PARENT_PRIM_PATH, True)
        set_prim_visibility(STREAMLINES_SPHERE_PRIM_PATH, True)
        # set_prim_visibility(STREAMLINES_CURVES_PRIM_PATH, True)
    except:
        pass

    try:
        # Never show the point cloud
        set_prim_visibility(STREAMLINES_POINT_CLOUD_PRIM_PATH, False)
    except:
        pass


def disable_streamline_mode():
    carb.log_info("Disabling streamline mode")
    # get_cgns_ui_extension_instance()._toggle_objects_changed_listener(False)
    # Hide stream line prims

    try:
        set_prim_visibility(STREAMLINES_POINT_CLOUD_PRIM_PATH, False)
    except:
        pass

    try:
        # set_prim_visibility(STREAMLINES_CURVES_PRIM_PATH, False)
        set_prim_active(STREAMLINES_CURVES_PRIM_PATH, False)
        set_prim_visibility(STREAMLINES_CURVES_PRIM_PATH, False)
    except:
        pass

    try:
        set_prim_visibility(STREAMLINES_PARENT_PRIM_PATH, False)
    except:
        pass


def enable_smokeprobe_mode():
    carb.log_info("Enabling smokeprobe mode")
    set_prim_attribute(SMOKEPROBE_SIM_PRIM_PATH, "forceClear", False)
    set_prim_attribute(SMOKEPROBE_SIM_PRIM_PATH, "forceSimulate", True)
    set_prim_visibility(SMOKEPROBE_ROOT_PRIM_PATH, True)
    # set_smokeprobes_pos(INITIAL_SMOKE_PROBE_PCT_POS)


def disable_smokeprobe_mode():
    carb.log_info("Disabling smokeprobe mode")
    set_prim_attribute(SMOKEPROBE_SIM_PRIM_PATH, "forceClear", True)
    set_prim_attribute(SMOKEPROBE_SIM_PRIM_PATH, "forceSimulate", False)
    set_prim_visibility(SMOKEPROBE_ROOT_PRIM_PATH, False)


def enable_index_mode():
    carb.log_info("Enabling IndeX volume mode")
    set_prim_visibility(INDEX_ROOT_PRIM_PATH, True)
    set_prim_visibility(INDEX_VOLUME_PRIM_PATH, True)


def disable_index_mode():
    carb.log_info("Disabling IndeX volume mode")
    set_prim_visibility(INDEX_ROOT_PRIM_PATH, False)
    set_prim_visibility(INDEX_VOLUME_PRIM_PATH, False)


def enable_slice_mode():
    carb.log_info("Enabling IndeX slice mode")
    set_prim_visibility(INDEX_ROOT_PRIM_PATH, True)
    set_slice_state(state="x")


def disable_slice_mode():
    carb.log_info("Disabling IndeX slice mode")
    set_prim_visibility(INDEX_ROOT_PRIM_PATH, False)
    set_slice_state(state="clear")

def set_prim_active(prim_path: str, active: bool):
    stage = omni.usd.get_context().get_stage()
    if not stage:
        carb.log_warn(f"Cannot set active state for prim '{prim_path}': Stage is None")
        return
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise Exception(f"Could not find prim at path '{prim_path}")
    prim.SetActive(active)
    return


def set_prim_visibility(prim_path: str, visible: bool):
    value = "inherited" if visible else "invisible"
    set_prim_attribute(prim_path, "visibility", value)


def set_prim_attribute(prim_path: str, attribute: str, value: any):
    stage = omni.usd.get_context().get_stage()
    if not stage:
        carb.log_warn(f"Cannot set attribute '{attribute}' for prim '{prim_path}': Stage is None")
        return
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise Exception(f"Could not find prim at path '{prim_path}")
    attribute = prim.GetAttribute(attribute)
    if not attribute:
        raise Exception(f"Could not find attribute '{attribute}' for prim '{prim_path}")
    attribute.Set(value)
    return

def set_prim_rel(prim_path: str, rel: str, value: any):
    stage = omni.usd.get_context().get_stage()
    if not stage:
        carb.log_warn(f"Cannot set relationship '{rel}' for prim '{prim_path}': Stage is None")
        return
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise Exception(f"Could not find prim at path '{prim_path}")
    relationship = prim.GetRelationship(rel)
    if not relationship:
        raise Exception(f"Could not find relationship '{rel}' for prim '{prim_path}")
    relationship.SetTargets([value])
    return


def calculate_pos_in_bounds(prim_paths: List[str], pct: List[float]):
    """
    Calculate a position in the bounding box surrounding the prims specified by `prim_paths`
    pct is a list of 3 percentage values from -1.0 to 1.0 corresponding to the pct position in
    the bounds, for each axis
    """
    return (calculate_world_pos_in_bounds(prim_paths, pct), calculate_local_pos_in_bounds(prim_paths, pct))

def calculate_local_pos_in_bounds(prim_paths: List[str], pct: List[float]):
    """
    Calculate a position in the bounding box surrounding the prims specified by `prim_paths`
    pct is a list of 3 percentage values from -1.0 to 1.0 corresponding to the pct position in
    the bounds, for each axis
    """
    local_bounds = get_local_bounds(prim_paths=prim_paths)
    local_pos = local_bounds.GetMidpoint()
    for i, p in enumerate(pct):
        local_pos[i] += 0.5 * p * local_bounds.GetSize()[i]
    return local_pos

def calculate_world_pos_in_bounds(prim_paths: List[str], pct: List[float]):
    """
    Calculate a position in the bounding box surrounding the prims specified by `prim_paths`
    pct is a list of 3 percentage values from -1.0 to 1.0 corresponding to the pct position in
    the bounds, for each axis
    """
    world_bounds = get_world_bounds(prim_paths=prim_paths)
    world_pos = world_bounds.GetMidpoint()
    for i, p in enumerate(pct):
        world_pos[i] += 0.5 * p * world_bounds.GetSize()[i]
    return world_pos


def get_local_bounds(prim_paths: list):
    with SectionManager()._get_section_edit_context():
        all_bound = Gf.Range3d()
        if isinstance(prim_paths, list) and len(prim_paths) > 0:
            for path in prim_paths:
                prim = SectionManager()._stage.GetPrimAtPath(path)
                # Cannot use location here since it could be invalid (for example: walls in sampleHouse)
                # xform = UsdGeom.Xformable(prim)
                # matrix = xform.GetLocalTransformation()
                # location = matrix.ExtractTranslation()
                bound = (
                    SectionManager()
                    ._bboxcache.ComputeLocalBound(prim)
                    .ComputeAlignedRange()
                )
                if bound.IsEmpty():
                    for child in Usd.PrimRange(prim):
                        if child.IsA(UsdGeom.Boundable):
                            sub_bound = (
                                SectionManager()
                                ._bboxcache.ComputeLocalBound(child)
                                .ComputeAlignedRange()
                            )
                            bound.UnionWith(sub_bound)
                all_bound.UnionWith(bound)
        return all_bound

def get_world_bounds(prim_paths: list):
    with SectionManager()._get_section_edit_context():
        all_bound = Gf.Range3d()
        if isinstance(prim_paths, list) and len(prim_paths) > 0:
            for path in prim_paths:
                prim = SectionManager()._stage.GetPrimAtPath(path)
                # Cannot use location here since it could be invalid (for example: walls in sampleHouse)
                # xform = UsdGeom.Xformable(prim)
                # matrix = xform.GetLocalTransformation()
                # location = matrix.ExtractTranslation()
                bound = (
                    SectionManager()
                    ._bboxcache.ComputeWorldBound(prim)
                    .ComputeAlignedRange()
                )
                if bound.IsEmpty():
                    for child in Usd.PrimRange(prim):
                        if child.IsA(UsdGeom.Boundable):
                            sub_bound = (
                                SectionManager()
                                ._bboxcache.ComputeWorldBound(child)
                                .ComputeAlignedRange()
                            )
                            bound.UnionWith(sub_bound)
                all_bound.UnionWith(bound)
        return all_bound
