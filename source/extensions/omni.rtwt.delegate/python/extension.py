# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import omni.ext
from omni.cae.data import get_data_delegate_registry
from .predicted import PredictedFieldDelegate

from logging import getLogger
logger = getLogger(__name__)

class Extension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._registry = get_data_delegate_registry()

        self._delegate = PredictedFieldDelegate(ext_id)
        self._registry.register_data_delegate(self._delegate, 1)

    def on_shutdown(self):
        self._registry.deregister_data_delegate(self._delegate)
        del self._delegate
