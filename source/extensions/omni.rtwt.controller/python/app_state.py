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

import omni.timeline
from omni.cae.viz.execution_context import ExecutionContext
from omni.cae.viz.operator import operator
from omni.cae.schema import viz as cae_viz
from omni.cae.data import usd_utils
from omni.kit.viewport.utility import get_active_viewport
from pxr import Gf, Sdf, Usd, UsdShade

from . import utils

logger = getLogger(__name__)


@operator()
class AppStateOperator:
    """Translate the web-application state prim into live scene changes.

    Triggered whenever a prim carrying both RtwtInferenceAppStateAPI and
    RtwtVizAppStateAPI is dirtied (typically by a web-API request).  A single
    execution fan-outs the new state to every affected part of the scene:

    - Car variant sets (Spoiler / Rims / Mirrors) on CarHero and CarCFD.
    - CAE visualization mode and slice-direction variant sets.
    - Inference velocity attribute on the Inference prim.
    - Colormap domains and material shader domains derived from the velocity.
    - Streamlines material binding (AnimatedStreaks vs ScalarColor).
    - Slider-driven transforms on all RtwtTransformAPI prims.
    - Viewport resolution scale (2X for Streamlines, 1X otherwise).
    - Timeline playback (play when animated streaks are active or explicitly
      requested, stop otherwise).
    """

    prim_type: str = "Prim"
    api_schemas: set[str] = {"RtwtInferenceAppStateAPI", "RtwtVizAppStateAPI"}
    optional_api_schemas: set[str] = set()

    async def exec(self, prim: Usd.Prim, device: str, context: ExecutionContext):
        """Apply the current app-state prim values to the live scene.

        Reads all state attributes from *prim*, then issues the corresponding
        USD edits and Kit API calls.  Most writes are batched inside a single
        Sdf.ChangeBlock to minimize change-processing overhead; the material
        binding and operator-enable toggle must happen outside the block because
        they rely on Kit callbacks that fire after the block closes.
        """

        spoiler = prim.GetAttribute("omni:rtwt:app_state:spoiler").Get() or "On"
        rims = prim.GetAttribute("omni:rtwt:app_state:rims").Get() or "Standard"
        mirrors = prim.GetAttribute("omni:rtwt:app_state:mirrors").Get() or "On"
        velocity = float(prim.GetAttribute("omni:rtwt:app_state:velocity").Get() or 25.0)
        slider_value = int(prim.GetAttribute("omni:rtwt:app_state:sliderValue").Get() or 0)
        slice_direction = prim.GetAttribute("omni:rtwt:app_state:sliceDirection").Get() or "X"
        viz_field = prim.GetAttribute("omni:rtwt:app_state:vizField").Get() or "VelocityMagnitude"
        viz_mode = prim.GetAttribute("omni:rtwt:app_state:vizMode").Get() or "Streamlines"
        animated_streaks = bool(prim.GetAttribute("omni:rtwt:app_state:animatedStreaks").Get() or False)
        play_animation = bool(prim.GetAttribute("omni:rtwt:app_state:playAnimation").Get() or False)

        logger.info(
            "AppStateOperator: spoiler=%s rims=%s mirrors=%s velocity=%s "
            "sliderValue=%s sliceDirection=%s vizField=%s vizMode=%s animatedStreaks=%s",
            spoiler, rims, mirrors, velocity, slider_value, slice_direction, viz_field, viz_mode, animated_streaks,
        )

        resolution_scale = 2.0 if viz_mode == "Streamlines" else 1.0

        stage = prim.GetStage()

        with Sdf.ChangeBlock():
            # Propagate car configuration variants.
            for car_path in ("/World/CarHero", "/World/CarCFD"):
                if not (car_prim := stage.GetPrimAtPath(car_path)):
                    continue
                vsets = car_prim.GetVariantSets()
                for set_name, value in (("Spoiler", spoiler), ("Rims", rims), ("Mirrors", mirrors)):
                    if vsets.HasVariantSet(set_name):
                        vsets.GetVariantSet(set_name).SetVariantSelection(value)
                    else:
                        logger.warning("Variant set '%s' not found on %s", set_name, car_path)

            # Set Mode and SliceDirection variant sets on the CAE anchor prim.
            # For Slice and Volume modes, compose the Mode variant name from vizMode + vizField.
            mode_variant = f"{viz_mode}_{viz_field}" if viz_mode in ("Slice", "Volume") else viz_mode
            if cae_prim := stage.GetPrimAtPath("/World/CAE"):
                vsets = cae_prim.GetVariantSets()
                if vsets.HasVariantSet("Mode"):
                    vsets.GetVariantSet("Mode").SetVariantSelection(mode_variant)
                    logger.info("Set CAE Mode variant to '%s'", mode_variant)
                else:
                    logger.warning("Mode variant set not found on /World/CAE")
                if vsets.HasVariantSet("SliceDirection"):
                    vsets.GetVariantSet("SliceDirection").SetVariantSelection(slice_direction)
                    logger.info("Set CAE SliceDirection variant to '%s'", slice_direction)
                else:
                    logger.warning("SliceDirection variant set not found on /World/CAE")

            # Forward velocity to the Inference prim.
            if inference_prim := stage.GetPrimAtPath("/World/Inference"):
                if attr := inference_prim.GetAttribute("omni:rtwt:inference:velocity"):
                    attr.Set(velocity)

            # Update colormap domains based on the current velocity (m/s).
            # Velocity range: 0.1 → 1.5× speed (matches the McLaren convention).
            # Pressure range: ±dynamic pressure q = ½ρv² (air density 1.225 kg/m³).
            vel_max = 1.5 * velocity
            air_density = 1.225
            dynamic_pressure = 0.5 * air_density * velocity ** 2

            if vel_colormap := stage.GetPrimAtPath("/World/Colormaps/VelocityColormap"):
                vel_colormap.CreateAttribute("domain", Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(0.1, vel_max)
                )

            if pres_colormap := stage.GetPrimAtPath("/World/Colormaps/PressureColormap"):
                pres_colormap.CreateAttribute("domain", Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(-dynamic_pressure, dynamic_pressure)
                )

            # Update streamlines material shader domain to match velocity range.
            for mat_name in ("AnimatedStreaks", "ScalarColor"):
                if shader := stage.GetPrimAtPath(f"/World/CAE/Streamlines/Materials/{mat_name}/Shader"):
                    shader.CreateAttribute("inputs:domain", Sdf.ValueTypeNames.Float2).Set(
                        Gf.Vec2f(0.0, vel_max)
                    )

            # Update slice shader domains to match the current velocity/pressure ranges.
            if vel_slice_shader := stage.GetPrimAtPath(
                "/World/CAE/PlanarSlice_VelocityMagnitude/Materials/SliceTexture/Shader"
            ):
                vel_slice_shader.CreateAttribute("inputs:domain", Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(0.0, vel_max)
                )

            if pres_slice_shader := stage.GetPrimAtPath(
                "/World/CAE/PlanarSlice_Pressure/Materials/SliceTexture/Shader"
            ):
                pres_slice_shader.CreateAttribute("inputs:domain", Sdf.ValueTypeNames.Float2).Set(
                    Gf.Vec2f(-dynamic_pressure, dynamic_pressure)
                )

        # Switch Streamlines material.
        if streamlines_prim := stage.GetPrimAtPath("/World/CAE/Streamlines"):
            mat_name = "AnimatedStreaks" if animated_streaks else "ScalarColor"
            mat_path = streamlines_prim.GetPath().AppendPath(f"Materials/{mat_name}")
            if mat_prim := stage.GetPrimAtPath(mat_path):
                binding_api = UsdShade.MaterialBindingAPI(streamlines_prim)
                if binding_api.GetDirectBinding().GetMaterialPath() != mat_path:
                    UsdShade.MaterialBindingAPI.Apply(streamlines_prim).Bind(
                        UsdShade.Material(mat_prim),
                        UsdShade.Tokens.weakerThanDescendants,
                    )
                    # Toggle the enabled flag off then on to force the operator
                    # to re-execute after a material change.  This works around
                    # a Kit bug where changing a material binding alone does not
                    # reliably trigger operator re-execution.
                    op_api = cae_viz.OperatorAPI(streamlines_prim)
                    op_api.CreateEnabledAttr().Set(False)
                    op_api.CreateEnabledAttr().Set(True)
            else:
                logger.warning("Streamlines material not found: %s", mat_path)

        # Apply slider-driven transforms via the ROI bounding box.
        roi_prim = usd_utils.get_target_prim(prim, "omni:rtwt:app_state:roi")
        utils.apply_slider_transforms(stage, roi_prim, slider_value)

        # Set viewport resolution scale and control timeline playback.
        if viewport := get_active_viewport():
            viewport.set_texture_resolution_scale(resolution_scale)
            logger.info("Set viewport resolution scale to %s", resolution_scale)

        should_play = (animated_streaks and viz_mode == "Streamlines") or play_animation
        timeline = omni.timeline.get_timeline_interface()
        if should_play:
            timeline.play()
        else:
            timeline.stop()
