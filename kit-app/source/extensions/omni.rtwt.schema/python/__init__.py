# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

import os.path
from logging import getLogger

from pxr import Plug

logger = getLogger(__name__)

pluginsRoot = os.path.abspath(os.path.join(os.path.dirname(__file__), "schemas"))
if not os.path.isdir(pluginsRoot):
    logger.error("Failed to find USD schemas directory '%s'", pluginsRoot)
    raise RuntimeError(f"Failed to find USD schemas directory '{pluginsRoot}'")

# list all the plugin directories
pluginDirs = [d for d in os.listdir(pluginsRoot) if os.path.isdir(os.path.join(pluginsRoot, d))]
if not pluginDirs:
    logger.error("Failed to find any USD plugin directories in '%s'", pluginsRoot)
    raise RuntimeError(f"Failed to find any USD plugin directories in '{pluginsRoot}'")

# register all the plugin directories
for pluginDir in pluginDirs:
    pluginPath = os.path.join(pluginsRoot, pluginDir)
    schemaPath = os.path.join(pluginPath, "resources")
    if os.path.isdir(schemaPath):
        # register the plugin
        # this will also register the schemas in the resources directory
        # and the plugin directory itself
        logger.info("loading USD plugin from '%s'", schemaPath)
        result = Plug.Registry().RegisterPlugins(schemaPath)
        if not result:
            logger.error("Failed to load USD plugin from '%s'", schemaPath)
