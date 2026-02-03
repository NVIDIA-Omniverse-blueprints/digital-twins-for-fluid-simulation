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
from omni.kit.app import get_app
from pxr import Usd
from carb.events import type_from_string
from omni.kit import commands
from omni.cae.data import usd_utils
from pxr import UsdGeom, Sdf
from .commands import CreateTriton
logger = getLogger(__name__)


class Car:
    CAR_VARIANT_PRIM_PATH = "/World/AllVehicles/HeroVehicles"
    CAR_VARIANT_NAME = "Variant_Set"

    def __init__(self, car: int):
        self._car: int = car
        self._rim: int = 0
        self._mirror: int = 0
        self._spoiler: int = 0
        self._ride_height: int = 0

    @property
    def car(self) -> str:
        return self.__class__.__name__
    
    @property
    def rim(self) -> str:
        return self.RIM_VARIANT_VALUES[self._rim]
    
    @property
    def mirror(self) -> str:
        return self.MIRROR_VARIANT_VALUES[self._mirror]

    @property
    def spoiler(self) -> str:
        return self.SPOILER_VARIANT_VALUES[self._spoiler]

    @property
    def ride_height(self) -> str:
        return self.RIDE_HEIGHT_VARIANT_VALUES[self._ride_height]

    @rim.setter
    def rim(self, value: str):
        if value in self.RIM_VARIANT_VALUES:
            self._rim = self.RIM_VARIANT_VALUES.index(value)
        else:
            raise ValueError(f"Invalid rim variant: {value}")

    @mirror.setter
    def mirror(self, value: str):
        if value in self.MIRROR_VARIANT_VALUES:
            self._mirror = self.MIRROR_VARIANT_VALUES.index(value)
        else:
            raise ValueError(f"Invalid mirror variant: {value}")

    @spoiler.setter
    def spoiler(self, value: str):
        if value in self.SPOILER_VARIANT_VALUES:
            self._spoiler = self.SPOILER_VARIANT_VALUES.index(value)
        else:
            raise ValueError(f"Invalid spoiler variant: {value}")

    @ride_height.setter
    def ride_height(self, value: str):
        if value in self.RIDE_HEIGHT_VARIANT_VALUES:
            self._ride_height = self.RIDE_HEIGHT_VARIANT_VALUES.index(value)
        else:
            raise ValueError(f"Invalid ride height variant: {value}")

    @property
    def inference_id(self) -> int:
        return self._car + self._mirror + 2 * self._spoiler + 4 * self._rim + 8 * self._ride_height

    def sync(self, stage: Usd.Stage):
        """
        Update the Prim based on the state
        """
        logger.warning(f"Stage updating to reflect state: model_id: {self.inference_id}: "
                       f"rim: {self.RIM_VARIANT_VALUES[self._rim]}, "
                       f"mirror: {self.MIRROR_VARIANT_VALUES[self._mirror]}, "
                       f"spoiler: {self.SPOILER_VARIANT_VALUES[self._spoiler]}, "
                       f"ride-height: {self.RIDE_HEIGHT_VARIANT_VALUES[self._ride_height]}")

        # first activate the car:
        car_var_prim = stage.GetPrimAtPath(self.CAR_VARIANT_PRIM_PATH)
        if not car_var_prim:
            logger.error(f"Prim {self.CAR_VARIANT_PRIM_PATH} not found. Stage may not reflect state.")
            return

        logger.info(f"Setting car variant to {self.__class__.__name__}")
        car_var_prim.GetVariantSet(self.CAR_VARIANT_NAME).SetVariantSelection(self.__class__.__name__)

        prim = stage.GetPrimAtPath(self.PRIM_PATH)
        if not prim:
            logger.error(f"Prim {self.PRIM_PATH} not found. Stage may not reflect state.")
            return

        logger.info(f"Setting rim variant to {self.RIM_VARIANT_VALUES[self._rim]}")
        variant_set = prim.GetVariantSet(self.RIM_VARIANT_NAME)
        variant_set.SetVariantSelection(self.RIM_VARIANT_VALUES[self._rim])

        logger.info(f"Setting mirror variant to {self.MIRROR_VARIANT_VALUES[self._mirror]}")
        variant_set = prim.GetVariantSet(self.MIRROR_VARIANT_NAME)
        variant_set.SetVariantSelection(self.MIRROR_VARIANT_VALUES[self._mirror])

        logger.info(f"Setting spoiler variant to {self.SPOILER_VARIANT_VALUES[self._spoiler]}")
        variant_set = prim.GetVariantSet(self.SPOILER_VARIANT_NAME)
        variant_set.SetVariantSelection(self.SPOILER_VARIANT_VALUES[self._spoiler])

        logger.info(f"Setting ride height variant to {self.RIDE_HEIGHT_VARIANT_VALUES[self._ride_height]}")
        variant_set = prim.GetVariantSet(self.RIDE_HEIGHT_VARIANT_NAME)
        variant_set.SetVariantSelection(self.RIDE_HEIGHT_VARIANT_VALUES[self._ride_height])


class ConceptCar(Car):
    PRIM_PATH = "/World/AllVehicles/HeroVehicles/Concept_Car"
    RIM_VARIANT_NAME = "Rims"
    RIM_VARIANT_VALUES = ["Standard", "Aero"]

    MIRROR_VARIANT_NAME = "Mirrors"
    MIRROR_VARIANT_VALUES = ["On", "Off"]

    SPOILER_VARIANT_NAME = "Spoiler"
    SPOILER_VARIANT_VALUES = ["Off", "On"]

    RIDE_HEIGHT_VARIANT_NAME = "Ride_Height"
    RIDE_HEIGHT_VARIANT_VALUES = ["Standard", "High"]

    def __init__(self):
        super().__init__(500)


class Controller:
    instance: "Controller" = None
    _ns = "omni:rtwt:service"

    SMOKEPROBE_PROBES_PARENT_PRIM_PATH = "/World/Flow_CFD/CFDResults/FlowLineProbes"
    SMOKEPROBE_BOUNDING_PRIM_PATH = "/World/Flow_CFD/CFDResults/SliderBounds"

    @classmethod
    def get_instance(cls) -> "Controller":
        return cls.instance

    @classmethod
    def set_instance(cls, instance: "Controller"):
        cls.instance = instance

    @classmethod
    def reset_instance(cls):
        cls.instance = None

    def __init__(self):
        self._stage: Usd.Stage = None
        self._triton_path = "/World/Inference"
        self._vis_path = "/World/CAE"
        self._web_service_path = "/World/Control"
        self._control_prim: Usd.Prim = None
        self._needs_init = False

    async def initialize(self, stage: Usd.Stage):
        assert self._stage is None
        self._stage: Usd.Stage = stage
        # # this will raise exception if stage is not supported;
        # # which means the controller won't be setup for this stage -- exactly what we want.
        # self.reset_state()

        commands.execute("CreateRTWTService", prim_path=self._web_service_path)
        commands.execute("CreateTriton", prim_path=self._triton_path)
        commands.execute("CreateRTWTVisualization", prim_path=self._vis_path,
                         dataset_path=f'{self._triton_path}/{CreateTriton.RESULT_PRIM_NAME}',
                         stl_path=f'{self._triton_path}/{CreateTriton.INPUT_PRIM_NAME}')

        self._control_prim = stage.GetPrimAtPath(Sdf.Path(self._web_service_path))
        assert self._control_prim, f"Control prim {self._web_service_path} not found after creation"
        self._needs_init = True

        self._camera_change_tracker = usd_utils.ChangeTracker(stage)
        self._camera_change_tracker.TrackAttribute(f"{self._ns}:camera")

        self._car_change_tracker = usd_utils.ChangeTracker(stage)
        self._car_change_tracker.TrackAttribute(f"{self._ns}:carModel")
        self._car_change_tracker.TrackAttribute(f"{self._ns}:rim")
        self._car_change_tracker.TrackAttribute(f"{self._ns}:mirror")
        self._car_change_tracker.TrackAttribute(f"{self._ns}:spoiler")
        self._car_change_tracker.TrackAttribute(f"{self._ns}:rideHeight")

        self._rendering_tracker = usd_utils.ChangeTracker(stage)
        self._rendering_tracker.TrackAttribute(f"{self._ns}:renderingMode")
        self._rendering_tracker.TrackAttribute(f"{self._ns}:attribute")
        self._rendering_tracker.TrackAttribute(f"{self._ns}:windSpeed")
        self._rendering_tracker.TrackAttribute(f"{self._ns}:pressureGradientScale")
        self._rendering_tracker.TrackAttribute(f"{self._ns}:velocityMagnitudeGradientScale")
        self._rendering_tracker.TrackAttribute(f"{self._ns}:showInputStl")

        self._streamline_tracker = usd_utils.ChangeTracker(stage)
        self._streamline_tracker.TrackAttribute(f"{self._ns}:streamlineRadiusFactor")
        self._streamline_tracker.TrackAttribute(f"{self._ns}:streamlineSeedPosition")
        self._streamline_tracker.TrackAttribute(f"{self._ns}:streamlineRadiusRange")

        self._slice_tracker = usd_utils.ChangeTracker(stage)
        self._slice_tracker.TrackAttribute(f"{self._ns}:sliceMode")
        self._slice_tracker.TrackAttribute(f"{self._ns}:slicePosition")

        self._flow_tracker = usd_utils.ChangeTracker(stage)
        self._flow_tracker.TrackAttribute(f"{self._ns}:smokeProbePosition")
        logger.warning("Controller initialized")

    def reset_state(self):
        pass

    @property
    def stage(self) -> Usd.Stage:
        return self._stage

    @property
    def control_prim(self) -> Usd.Prim:
        if not self._control_prim:
            logger.error("Control prim not initialized")
        return self._control_prim

    def update(self) -> tuple[bool, bool]:
        if not self.control_prim:
            logger.error("No control prim")
            return False, False    # no relevant changes

        try:
            changed = False
            renderer_reset_needed = False
            if self._camera_change_tracker.PrimChanged(self._control_prim) or self._needs_init:
                self.update_camera()
                self._camera_change_tracker.ClearChanges()
                changed = True

            if self._car_change_tracker.PrimChanged(self._control_prim) or self._needs_init:
                self.update_car()
                self._car_change_tracker.ClearChanges()
                changed = True
                renderer_reset_needed = True

            if self._rendering_tracker.PrimChanged(self._control_prim) or self._needs_init:
                self.update_rendering()
                self._rendering_tracker.ClearChanges()
                changed = True
                renderer_reset_needed = True

            if self._streamline_tracker.PrimChanged(self._control_prim) or self._needs_init:
                self.update_streamlines()
                self._streamline_tracker.ClearChanges()
                changed = True

            if self._slice_tracker.PrimChanged(self._control_prim) or self._needs_init:
                self.update_slice()
                self._slice_tracker.ClearChanges()
                changed = True

            if self._flow_tracker.PrimChanged(self._control_prim) or self._needs_init:
                self.update_flow()
                self._flow_tracker.ClearChanges()
                changed = True

        except Exception as e:
            logger.error(f"Error in update: {e}")
            raise e

        self._needs_init = False
        return changed, renderer_reset_needed

    def update_camera(self):
        camera = usd_utils.get_attribute(self._control_prim, f"{self._ns}:camera", quiet=True)
        if not camera:
            logger.warning("No camera found")
            return
        logger.warning(f"update_camera to {camera}")
        switch_cam_msg = type_from_string("switchCamera")
        get_app().get_message_bus_event_stream().push(switch_cam_msg, payload={"targetCamera": str(camera)})

    def update_car(self):
        logger.warning("update_car")
        car_model = usd_utils.get_attribute(self._control_prim, f"{self._ns}:carModel")
        if car_model == "Concept":
            car = ConceptCar()
        else:
            raise RuntimeError(f"Unknown car model {car_model}")

        car.rim = usd_utils.get_attribute(self._control_prim, f"{self._ns}:rim")
        car.mirror = usd_utils.get_attribute(self._control_prim, f"{self._ns}:mirror")
        car.spoiler = usd_utils.get_attribute(self._control_prim, f"{self._ns}:spoiler")
        car.ride_height = usd_utils.get_attribute(self._control_prim, f"{self._ns}:rideHeight")
        car.sync(self._stage)

        # since car changed, update the inference
        if triton := self._stage.GetPrimAtPath(self._triton_path):
            logger.warning(f"Setting inference modelId to {car.inference_id}")
            triton.GetAttribute("omni:rtwt:triton:modelId").Set(car.inference_id)

    def update_rendering(self):
        rendering_mode = usd_utils.get_attribute(self._control_prim, f"{self._ns}:renderingMode")
        attribute = usd_utils.get_attribute(self._control_prim, f"{self._ns}:attribute")
        logger.warning("update_rendering to %s for attribute %s", rendering_mode, attribute)

        streamlines_scope = UsdGeom.Scope(self._stage.GetPrimAtPath(f"{self._vis_path}/Streamlines"))
        flow_scope = UsdGeom.Scope(self._stage.GetPrimAtPath(f"{self._vis_path}/Flow"))
        volumes_scope = UsdGeom.Scope(self._stage.GetPrimAtPath(f"{self._vis_path}/Volumes"))
        slices_scope = UsdGeom.Scope(self._stage.GetPrimAtPath(f"{self._vis_path}/Slices"))

        if rendering_mode == "Volume":
            streamlines_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            flow_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            volumes_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
            slices_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)

            # update which volume to show:
            pressure_volume = UsdGeom.Imageable(volumes_scope.GetPrim().GetChild("Pressure"))
            velocity_volume = UsdGeom.Imageable(volumes_scope.GetPrim().GetChild("VelocityMagnitude"))
            pressure_volume.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if attribute == "Pressure" else UsdGeom.Tokens.invisible)
            velocity_volume.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if attribute == "VelocityMagnitude" else UsdGeom.Tokens.invisible)

        elif rendering_mode == "Slice":
            streamlines_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            flow_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            volumes_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            slices_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)

            # update which slice to show
            pressure_slice = UsdGeom.Imageable(slices_scope.GetPrim().GetChild("Pressure"))
            velocity_slice = UsdGeom.Imageable(slices_scope.GetPrim().GetChild("VelocityMagnitude"))
            pressure_slice.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if attribute == "Pressure" else UsdGeom.Tokens.invisible)
            velocity_slice.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if attribute == "VelocityMagnitude" else UsdGeom.Tokens.invisible)

        elif rendering_mode == "Smoke":
            streamlines_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            flow_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
            volumes_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            slices_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        elif rendering_mode == "Streamlines":
            streamlines_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
            flow_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            volumes_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            slices_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        else:
            logger.warning(f"Unknown rendering mode {rendering_mode}")
            streamlines_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            flow_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            volumes_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            slices_scope.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        stl_prim = UsdGeom.Mesh(self._stage.GetPrimAtPath(f"{self._vis_path}/InputMesh"))
        if usd_utils.get_attribute(self._control_prim, f"{self._ns}:showInputStl"):
            logger.warning("Showing input STL")
            stl_prim.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
        else:
            logger.warning("Hiding input STL")
            stl_prim.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        wind_speed = usd_utils.get_attribute(self._control_prim, f"{self._ns}:windSpeed")
        logger.warning(f"update_streamline to wind speed {wind_speed}")
        if triton := self._stage.GetPrimAtPath(self._triton_path):
            logger.warning(f"Setting inference wind speed to {wind_speed}")
            triton.GetAttribute("omni:rtwt:triton:streamVelocity").Set(wind_speed)

        if attribute == "Pressure":
            gradient = usd_utils.get_attribute(self._control_prim, f"{self._ns}:pressureGradientScale")
        elif attribute == "VelocityMagnitude":
            gradient = usd_utils.get_attribute(self._control_prim, f"{self._ns}:velocityMagnitudeGradientScale")

        # update color maps for IndeX
        colormap_paths = [
            f"{self._vis_path}/Volumes/{attribute}/Material/Colormap",
            f"{self._vis_path}/Slices/{attribute}/Material/Colormap",
        ]
        for colormap_path in colormap_paths:
            if v_color := self._stage.GetPrimAtPath(colormap_path):
                v_color.GetAttribute("domain").Set(gradient)
                v_color.GetAttribute("domainBoundaryMode").Set("clampToEdge")
            else:
                logger.error(f"{colormap_path} colormap not found!")
                
        # update range for Flow
        flow_suffix = "_pressure" if attribute == "Pressure" else ""
        flow_paths = [
            f"/World/Flow_CFD/CFDResults/flowRender{flow_suffix}/rayMarch",
            f"/World/Flow_CFD/CFDResults/flowOffscreen{flow_suffix}/shadow",
        ]
        for flow_path in flow_paths:
            if v_flow := self._stage.GetPrimAtPath(flow_path):
                v_flow.GetAttribute("colormapXMin").Set(gradient[0])
                v_flow.GetAttribute("colormapXMax").Set(gradient[1])
            else:
                logger.error(f"{flow_path} flow path not found!")

        # update Flow colors
        # TODO: implement Flow coloring updates; for now, we'll use default coloring
        if probe_prim := self._stage.GetPrimAtPath(self.SMOKEPROBE_PROBES_PARENT_PRIM_PATH):
            UsdGeom.Imageable(probe_prim).GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if rendering_mode == "Smoke" else UsdGeom.Tokens.invisible)
        else:
            logger.error(f"{self.SMOKEPROBE_PROBES_PARENT_PRIM_PATH} smoke probe path not found!")

        if ds_emitter_vm := self._stage.GetPrimAtPath(f"{self._vis_path}/Flow/VelocityMagnitude"):
            ds_emitter_vm.GetAttribute("enabled").Set(rendering_mode == "Smoke" and attribute == "VelocityMagnitude")
        else:
            logger.error(f"{self._vis_path}/Flow/VelocityMagnitude not found!")

        if ds_emitter_pressure := self._stage.GetPrimAtPath(f"{self._vis_path}/Flow/Pressure"):
            ds_emitter_pressure.GetAttribute("enabled").Set(rendering_mode == "Smoke" and attribute == "Pressure")
        else:
            logger.error(f"{self._vis_path}/Flow/Pressure not found!")

        if flow_sim := self._stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowSimulate"):
            flow_sim.GetAttribute("forceClear").Set(rendering_mode != "Smoke")
            flow_sim.GetAttribute("forceDisableEmitters").Set(rendering_mode != "Smoke")
            flow_sim.GetAttribute("forceSimulate").Set(rendering_mode == "Smoke")
        else:
            logger.error("/World/Flow_CFD/CFDResults/flowSimulate not found!")

        if flow_render := self._stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowRender"):
            flow_render.GetAttribute("layer").Set(2 if attribute == "VelocityMagnitude" else 0)
        else:
            logger.error("/World/Flow_CFD/CFDResults/flowRender not found!")
        if flow_render_pressure := self._stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowRender_pressure"):
            flow_render_pressure.GetAttribute("layer").Set(2 if attribute == "Pressure" else 0)
        else:
            logger.error("/World/Flow_CFD/CFDResults/flowRender_pressure not found!")
        if flow_offscreen := self._stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowOffscreen"):
            flow_offscreen.GetAttribute("layer").Set(2 if attribute == "VelocityMagnitude" else 0)
        else:
            logger.error("/World/Flow_CFD/CFDResults/flowOffscreen not found!")
        if flow_offscreen_pressure := self._stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowOffscreen_pressure"):
            flow_offscreen_pressure.GetAttribute("layer").Set(2 if attribute == "Pressure" else 0)
        else:
            logger.error("/World/Flow_CFD/CFDResults/flowOffscreen_pressure not found!")

    def update_streamlines(self):
        streamlines_scope = self._stage.GetPrimAtPath(f"{self._vis_path}/Streamlines")
        seeds_prim = streamlines_scope.GetChild("Seeds")

        # set seeds
        radiusRange = list(usd_utils.get_attribute(self._control_prim, f"{self._ns}:streamlineRadiusRange"))
        radiusFactor = usd_utils.get_attribute(self._control_prim, f"{self._ns}:streamlineRadiusFactor")
        radius = float(radiusFactor * (radiusRange[1] - radiusRange[0]) + radiusRange[0])
        
        logger.warning(f"update_streamline to radius {radius}")
        xformAPI = UsdGeom.XformCommonAPI(seeds_prim)
        xformAPI.SetScale((radius, radius, radius))

        exts = usd_utils.get_attribute(self._control_prim, f"{self._ns}:extent")
        normalized_pos = usd_utils.get_attribute(self._control_prim, f"{self._ns}:streamlineSeedPosition")
        # clamp to (-1, 1)
        normalized_pos = [max(-1, min(1, p)) for p in normalized_pos]
        x = exts[0][0] + (exts[1][0] - exts[0][0]) * (normalized_pos[0] + 1) / 2
        y = exts[0][1] + (exts[1][1] - exts[0][1]) * (normalized_pos[1] + 1) / 2
        z = exts[0][2] + (exts[1][2] - exts[0][2]) * (normalized_pos[2] + 1) / 2
        logger.warning(f"update_streamline to position {x}, {y}, {z}")
        xformAPI.SetTranslate((x, y, z))

    def update_slice(self):
        index_scope = self._stage.GetPrimAtPath(f"{self._vis_path}/Slices")
        v_slice_xform = UsdGeom.XformCommonAPI(index_scope.GetPrimAtPath("VelocityMagnitude/Plane"))
        p_slice_xform = UsdGeom.XformCommonAPI(index_scope.GetPrimAtPath("Pressure/Plane"))

        # Update the slice position based on the control parameters
        exts = usd_utils.get_attribute(self._control_prim, f"{self._ns}:extent")
        normalized_pos = usd_utils.get_attribute(self._control_prim, f"{self._ns}:slicePosition")
        # clamp to (-1, 1)
        normalized_pos = max(-1, min(1, normalized_pos))
        mode = usd_utils.get_attribute(self._control_prim, f"{self._ns}:sliceMode")
        if mode == "X":
            axis = 1
            rotation = (0, 0, 90)
            normalized_pos = -normalized_pos   # invert X axis to match UI
        elif mode == "Z":
            rotation = (0, 0, 0)
            axis = 0
        elif mode == "Y":
            rotation = (0, 90, 0)
            axis = 2
        else:
            logger.warning(f"Unknown slice mode {mode}")
            return
        
        slice_position = exts[0][axis] + (exts[1][axis] - exts[0][axis]) * (normalized_pos + 1) / 2
        slice_pos_vec = [0] * 3
        slice_pos_vec[axis] = slice_position

        v_slice_xform.SetRotate(rotation)
        v_slice_xform.SetTranslate(slice_pos_vec)
        p_slice_xform.SetRotate(rotation)
        p_slice_xform.SetTranslate(slice_pos_vec)

        logger.warning(f"update_slice to {slice_pos_vec} and rotation {rotation}")

    def update_flow(self):

        normalized_pos = usd_utils.get_attribute(self._control_prim, f"{self._ns}:smokeProbePosition")
        # Since Flow probes are not placed under the same xform as the data, we rely on SMOKEPROBE_BOUNDING_PRIM_PATH
        if bds_prim := self._stage.GetPrimAtPath(self.SMOKEPROBE_BOUNDING_PRIM_PATH):
            exts_range3d = usd_utils.get_bounds(bds_prim, Usd.TimeCode.EarliestTime())
            exts = [exts_range3d.GetMin(), exts_range3d.GetMax()]
        else:
            logger.error(f"{self.SMOKEPROBE_BOUNDING_PRIM_PATH} bounding prim path not found!")
            return

        pos = [exts[0][i] + (exts[1][i] - exts[0][i]) * (normalized_pos[i] + 1) / 2 for i in range(3)]
        if smoke_probe := self._stage.GetPrimAtPath(self.SMOKEPROBE_PROBES_PARENT_PRIM_PATH):
            logger.warning(f"update_flow to position {pos}")
            xformAPI = UsdGeom.XformCommonAPI(smoke_probe)
            xformAPI.SetTranslate(pos)
        else:
            logger.error(f"{self.SMOKEPROBE_PROBES_PARENT_PRIM_PATH} smoke probe path not found!")


def get_controller() -> Controller:
    """
    Get the global controller instance. This will raise an exception if the controller
    has not been initialized. Use `initialize` to set it up.
    """
    controller = Controller.get_instance()
    if controller is None:
        raise RuntimeError("Controller not initialized")
    return controller
