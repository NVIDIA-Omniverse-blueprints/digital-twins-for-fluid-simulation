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
from omni.kit.commands import register_all_commands_in_module, unregister_module_commands
from omni.cae.viz import Controller, register_module_operators, unregister_module_operators

from . import inference
from . import results


class Extension(omni.ext.IExt):
    def on_startup(self, ext_id):
        Controller.add_schema_regex(r"^Rtwt")
        register_all_commands_in_module(results)
        register_module_operators(inference)

    def on_shutdown(self):
        unregister_module_operators(inference)
        unregister_module_commands(results)
        Controller.remove_schema_regex(r"^Rtwt")
