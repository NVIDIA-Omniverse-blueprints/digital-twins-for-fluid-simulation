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

from omni.cae.data import usd_utils
from pxr import Usd, UsdGeom, UsdUtils
from usdrt import Usd as UsdRt

logger = getLogger(__name__)


def get_rt_stage(stage: Usd.Stage):
    """Return the UsdRt stage corresponding to the given USD stage."""
    cache = UsdUtils.StageCache.Get()
    stage_id = cache.GetId(stage)
    return UsdRt.Stage.Attach(stage_id.ToLongInt())


def apply_slider_transforms(stage: Usd.Stage, roi_prim: Usd.Prim, slider_value: int):
    """Apply slider-driven translations to all prims with RtwtTransformAPI.

    slider_value is in [-100, 100] and is mapped linearly to each axis of the
    ROI bounding box.  Each RtwtTransformAPI instance declares which axis ("x",
    "y", or "z") it controls and whether the direction should be flipped.
    """
    bounds = usd_utils.get_bounds(roi_prim)
    x_value = bounds.GetMin()[0] + (slider_value + 100) / 200 * (bounds.GetMax()[0] - bounds.GetMin()[0])
    y_value = bounds.GetMin()[1] + (slider_value + 100) / 200 * (bounds.GetMax()[1] - bounds.GetMin()[1])
    z_value = bounds.GetMin()[2] + (slider_value + 100) / 200 * (bounds.GetMax()[2] - bounds.GetMin()[2])
    logger.info("Mapped slider %d to: (%s, %s, %s)", slider_value, x_value, y_value, z_value)

    for path in get_rt_stage(stage).GetPrimsWithAppliedAPIName("RtwtTransformAPI"):
        xformed_prim = stage.GetPrimAtPath(str(path))
        if not xformed_prim:
            continue
        instance_names = usd_utils.get_instances(xformed_prim, "RtwtTransformAPI")
        for name in instance_names:
            name = name.lower()
            if name not in ("x", "y", "z"):
                logger.info("Unknown RtwtTransformAPI instance '%s' on %s, skipping", name, path)
                continue

            flip = usd_utils.get_attribute(xformed_prim, f"omni:rtwt:transform:{name}:flipDirection")
            xform_api = UsdGeom.Xformable(xformed_prim)
            cur_value = xform_api.GetTranslateOp().Get() if xform_api.GetTranslateOp() else [0.0, 0.0, 0.0]

            mapped = {"x": x_value, "y": y_value, "z": z_value}[name]
            axis_idx = {"x": 0, "y": 1, "z": 2}[name]
            cur_value[axis_idx] = mapped if not flip else -mapped

            UsdGeom.XformCommonAPI(xformed_prim).SetTranslate(cur_value)
            logger.info("Set translation of %s to %s", path, cur_value)
