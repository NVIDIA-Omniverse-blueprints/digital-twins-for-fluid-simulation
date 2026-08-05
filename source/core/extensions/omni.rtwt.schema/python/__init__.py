# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import os.path
from logging import getLogger

from pxr import Plug

logger = getLogger(__name__)

pluginsRoot = os.path.abspath(os.path.join(os.path.dirname(__file__), "schemas"))
if not os.path.isdir(pluginsRoot):
    raise RuntimeError(f"Failed to find USD schemas directory '{pluginsRoot}'")

pluginDirs = [d for d in os.listdir(pluginsRoot) if os.path.isdir(os.path.join(pluginsRoot, d))]
if not pluginDirs:
    raise RuntimeError(f"Failed to find any USD plugin directories in '{pluginsRoot}'")

for pluginDir in pluginDirs:
    schemaPath = os.path.join(pluginsRoot, pluginDir, "resources")
    if os.path.isdir(schemaPath):
        logger.info("loading USD plugin from '%s'", schemaPath)
        if not Plug.Registry().RegisterPlugins(schemaPath):
            logger.error("Failed to load USD plugin from '%s'", schemaPath)
