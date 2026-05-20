# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

__all__ = ["PredictedFieldDelegate"]

from logging import getLogger

import numpy as np
from omni.cae.data import cache
from omni.cae.data.delegates import DataDelegateBase
from pxr import Usd
from omni.cae.delegate.npz.npz import NPZDataDelegate
logger = getLogger(__name__)

_API_SCHEMA = "RtwtFieldArrayAPI"
_TAG_ATTR = "omni:rtwt:field_array:tag"
_USE_PLACEHOLDER_ATTR = "omni:rtwt:field_array:usePlaceholder"


class PredictedFieldDelegate(DataDelegateBase):

    def __init__(self, extId: str):
        super().__init__(extId)
        self._npz_delegate = NPZDataDelegate(extId)

    @staticmethod
    def set_tag(prim: Usd.Prim, tag: str) -> str:
        """Set the tag on the prim and return the old tag."""
        old_tag = prim.GetAttribute(_TAG_ATTR).Get()
        prim.GetAttribute(_TAG_ATTR).Set(tag)
        return old_tag

    def get_field_array(self, prim: Usd.Prim, time: Usd.TimeCode) -> np.ndarray:
        placeholder = prim.GetAttribute(_USE_PLACEHOLDER_ATTR).Get(time)
        if placeholder:
            logger.warning("Using placeholder data for %s at time %s", prim.GetPath(), time)
            return self._npz_delegate.get_field_array(prim, time)

        tag = prim.GetAttribute(_TAG_ATTR).Get(time)
        if not tag:
            logger.error("No tag set on %s, inference may not have run yet", prim.GetPath())
            return None
        array = cache.get(tag)
        if array is None:
            logger.error("No cached data for tag '%s' on %s", tag, prim.GetPath())
            return None
        return array

    def can_provide(self, prim: Usd.Prim) -> bool:
        return (
            prim and prim.IsValid()
            and _API_SCHEMA in prim.GetAppliedSchemas()
            and bool(prim.GetAttribute(_TAG_ATTR).Get())
        )
