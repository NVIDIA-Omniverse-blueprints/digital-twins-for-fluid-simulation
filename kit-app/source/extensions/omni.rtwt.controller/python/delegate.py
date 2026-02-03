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

import numpy as np
from omni.cae.data.delegates import DataDelegateBase
from pxr import Usd
from typing import Any

logger = getLogger(__name__)


class InferenceDataDelegate(DataDelegateBase):
    PRIM_PATH = "/World/Inference/ResultData"
    FIELD_NAME_ATTR = "omni:rtwt:fieldName"
    KEY_ATTR = "omni:rtwt:key"
    TAG_ATTR = "omni:rtwt:tag"

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__("omni.rtwt.controller")
        self._data = {}

    def get_field_array(self, prim: Usd.Prim, time: Usd.TimeCode) -> np.ndarray:
        name = prim.GetAttribute(self.FIELD_NAME_ATTR).Get(time)
        key = prim.GetAttribute(self.KEY_ATTR).Get(time)
        tag = prim.GetAttribute(self.TAG_ATTR).Get(time)

        if key not in self._data:
            logger.error(f"No data found for key \"{key}\"")
            return None

        data_tag, data = self._data[key]
        if data_tag != tag:
            logger.error(f"Tag mismatch: {tag} != {data_tag}")
            return None

        array = getattr(data, name, None)
        if array is None:
            logger.error(f"No field named {name} found in data with tag {data_tag}")
            return None

        logger.warning(f"Fetching field array for {name}: {array.shape} min={array.min(axis=0)} max={array.max(axis=0)}")
        return array

    def can_provide(self, prim: Usd.Prim) -> bool:
        return prim and prim.HasAttribute(self.FIELD_NAME_ATTR) and prim.HasAttribute(self.TAG_ATTR) and prim.HasAttribute(self.KEY_ATTR)   

    def set_data(self, key: str, data_tag: str, data: Any):
        logger.warning("setting data (%s, %s)", key, data_tag)
        self._data[key] = (data_tag, data)
