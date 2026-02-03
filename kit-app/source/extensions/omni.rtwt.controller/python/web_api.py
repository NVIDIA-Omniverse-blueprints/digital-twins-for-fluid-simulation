# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.
from logging import getLogger
from . import ovapi
from .controller import get_controller
from enum import Enum
from pxr import Usd, Gf

logger = getLogger(__name__)
ns = "omni:rtwt:service"

app = ovapi.OmniverseAPI()

@app.request
def reset() -> bool:
    logger.warning("Resetting controller state")
    prim = get_control_prim()    
    prim.GetAttribute(f"{ns}:carModel").Set("Concept")
    prim.GetAttribute(f"{ns}:rim").Set("Standard")
    prim.GetAttribute(f"{ns}:mirror").Set("On")
    prim.GetAttribute(f"{ns}:spoiler").Set("Off")
    prim.GetAttribute(f"{ns}:rideHeight").Set("Standard")
    prim.GetAttribute(f"{ns}:camera").Set("/World/InteractiveCams/demoCam03")
    prim.GetAttribute(f"{ns}:windSpeed").Set(75)
    prim.GetAttribute(f"{ns}:renderingMode").Set("Smoke")
    pos = [0.0,-1.0,-1.0]
    prim.GetAttribute(f"{ns}:smokeProbePosition").Set(Gf.Vec3f(*pos))
    return True


class CarModels(Enum):
    Truck = 100
    SUV = 200
    Electric = 300
    Sedan = 400
    Concept = 500


class RenderingModes(Enum):
    Smoke = 0
    Streamlines = 1
    Volume = 2
    Slice = 3


def get_control_prim() -> Usd.Prim:
    controller = get_controller()
    if controller:
        if prim := controller.control_prim:
            return prim
        raise RuntimeError("Control prim not initialized")
    raise RuntimeError("Controller not initialized")


@app.request
def select_car(cgns_idx: int, reset_rendering_mode: int = -1) -> bool:
    logger.error(f"Selecting car with CGNS index: {cgns_idx}, reset rendering mode: {reset_rendering_mode}")
    prim = get_control_prim()    
    prim.GetAttribute(f"{ns}:carModel").Set(CarModels(cgns_idx).name)
    if reset_rendering_mode >= 0:
        prim.GetAttribute(f"{ns}:renderingMode").Set(RenderingModes(reset_rendering_mode).name)
        return True
    return False


@app.request
def set_interactive_camera(camera_prim_path: str) -> bool:
    logger.warning(f"Setting interactive camera to {camera_prim_path}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:camera").Set(camera_prim_path)
    return True


@app.request
def set_rim_variant(inference_id: int) -> bool:
    logger.error(f"Setting rim variant to {inference_id}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:rim").Set("Standard" if inference_id == 0 else "Aero")
    return True


@app.request
def set_mirror_variant(inference_id: int) -> bool:
    logger.warning(f"Setting mirror variant to {inference_id}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:mirror").Set("On" if inference_id == 0 else "Off")
    return True


@app.request
def set_spoiler_variant(inference_id: int) -> bool:
    logger.warning(f"Setting spoiler variant to {inference_id}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:spoiler").Set("Off" if inference_id == 0 else "On")
    return True


@app.request
def set_ride_height_variant(inference_id: int) -> bool:
    logger.warning(f"Setting ride height variant to {inference_id}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:rideHeight").Set("Standard" if inference_id == 0 else "High")
    return True


@app.request
def set_wind_speed(speed: float, point_scale: float = 1.0) -> bool:
    logger.warning(f"Setting wind speed to {speed}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:windSpeed").Set(speed)
    return True


@app.request
def set_rendering_mode(mode: int) -> bool:
    logger.warning(f"Setting rendering mode to {mode}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:renderingMode").Set(RenderingModes(mode).name)
    return True


@app.request
def set_visualization_attribute_state(attribute: int) -> bool:
    '''
    Set the attribute to render, currently only supports Velocity and Pressure
    attribute = 0 -> VelocityMagnitude
    attribute = 1 -> Pressure
    '''
    logger.warning(f"Setting visualization attribute state to {attribute}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:attribute").Set("VelocityMagnitude" if attribute == 0 else "Pressure")
    return True


@app.request
def set_streamlines_pos(pct: list[float]) -> bool:
    '''
    Set the position of the streamline sphere:

    pct = [x,y,z] where each component is a % value
    x -> [-1, 1]
    y -> [-1, 1]
    z -> [-1, 1]

    and the % value determines where to position the prim within the bounds of the prim at STREAMLINES_BOUNDING_PRIM_PATH
    '''
    logger.warning(f"Setting streamline seed position to {pct}")
    pos = [max(-1.0, min(1.0, v)) for v in pct]
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:streamlineSeedPosition").Set(Gf.Vec3f(*pos))
    return True


@app.request
def set_streamlines_radius(pct: float) -> bool:
    '''
    Set the radius of the streamline sphere as a % [0.0, 1.0]
    As the radius changes, update the number of streamlines that originate from the sphere.
    '''
    logger.warning(f"Setting streamline radius to {pct}")
    radius = max(0.0, min(1.0, pct))
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:streamlineRadiusFactor").Set(radius)
    return True


@app.request
def set_smokeprobes_pos(pct: list[float]) -> bool:
    '''
    Set the position of the smoke probe emitters:

    pct = [x,y,z] where each component is a % value
    x -> [-1, 1]
    y -> [-1, 1]
    z -> [-1, 1]

    and the % value determines where to position the prim within the bounds of the prim at SMOKEPROBE_BOUNDING_PRIM_PATH
    '''
    logger.warning(f"Setting smoke probe position to {pct}")
    pos = [max(-1.0, min(1.0, v)) for v in pct]
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:smokeProbePosition").Set(Gf.Vec3f(*pos))
    return True


@app.request
def set_slice_state(state: str) -> bool:
    '''
    Set the state of the IndeX Slice rendering visualization
    This manages the state of both the IndeX Slice Volume prims AND the section tool state
    '''
    logger.warning(f"Setting slice state to {state}")
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:sliceMode").Set(state.upper())
    return True


@app.request
def set_slice_pos(pct: float) -> bool:
    """
    Set the position of the current selected slice axis along the oriented axis at the specified pct

    This positions both the IndeX Slice plane prim AND the section tool widget
    """
    logger.warning(f"Setting slice position to {pct}")
    pos = max(-1.0, min(1.0, pct))
    prim = get_control_prim()
    prim.GetAttribute(f"{ns}:slicePosition").Set(pos)
    return True


@app.request
def set_gradient_scale(min_val: float, max_val: float) -> bool:
    """
    Update the color domains across all visualizations whenever the gradient scale changes
    """
    logger.warning(f"Setting gradient scale to [{min_val}, {max_val}]")
    prim = get_control_prim()

    attr = prim.GetAttribute(f"{ns}:attribute").Get()
    if attr == "Pressure":
        prim.GetAttribute(f"{ns}:pressureGradientScale").Set(Gf.Vec2f(min_val, max_val))
    else:
        prim.GetAttribute(f"{ns}:velocityMagnitudeGradientScale").Set(Gf.Vec2f(min_val, max_val))
    return True


@app.signal
def inference_complete(message: str):
    logger.warning("Received 'inference_complete_signal' with message: %s", message)
    return message
