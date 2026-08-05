# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

from logging import getLogger

import omni.ext

from omni.rtwt.controller.callbacks import CallbackRegistry

from .hooks import comparison_override, dynamic_pressure

logger = getLogger(__name__)

_DYNAMIC_PRESSURE = "auto_aero.dynamic_pressure"
_COMPARISON_OVERRIDE = "auto_aero.comparison_override"


class Extension(omni.ext.IExt):
    """Registers the automotive-aero specialization callbacks into the controller's binding
    engine. The dependency on omni.rtwt.controller guarantees the registry exists first; the
    callbacks are in place long before the first app-state change can trigger the engine."""

    def on_startup(self, _ext_id):
        CallbackRegistry.register(_DYNAMIC_PRESSURE, dynamic_pressure)
        CallbackRegistry.register(_COMPARISON_OVERRIDE, comparison_override)

    def on_shutdown(self):
        CallbackRegistry.unregister(_DYNAMIC_PRESSURE)
        CallbackRegistry.unregister(_COMPARISON_OVERRIDE)
