# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

from carb.settings import get_settings
from carb.tokens import get_tokens_interface
from omni.cae.algorithms.core import get_factory
from omni.cae.data import get_data_delegate_registry
from omni.kit.actions.core import get_action_registry
from omni.kit import commands as kit_commands
from omni.kit.quicklayout import QuickLayout
from omni.kit.viewport.utility import get_active_viewport, disable_selection

from .delegate import InferenceDataDelegate
from . import commands
from .inference import Triton
from .listener import Listener

import asyncio
import os
import omni.ext
import omni.kit.app
import omni.client

from logging import getLogger

logger = getLogger(__name__)


class Extension(omni.ext.IExt):
    def on_startup(self, _ext_id):
        # this initializes the web by registering the API endpoints
        from . import web_api

        self._extId = _ext_id
        self.listener = Listener()
        self._data_delegate = InferenceDataDelegate.get_instance()
        get_data_delegate_registry().register_data_delegate(self._data_delegate)

        # setup algorithms
        factory = get_factory()
        factory.register_create_callback("Triton", ["RtwtTritonAPI"], Triton, self._extId)

        kit_commands.register_all_commands_in_module(commands)

        app = omni.kit.app.get_app()

        # add materials path to the omni.client search path
        # so stage can find the XAC materials included in this extension.
        ext_path = app.get_extension_manager().get_extension_path(self._extId)
        materials_path = os.path.join(ext_path, "data")
        omni.client.add_default_search_path(materials_path)
        self._path = materials_path

        app.delay_app_ready("omni.usd")
        self._init_task = asyncio.ensure_future(self._initialize(app, ext_path))

    def on_shutdown(self):

        if self._init_task:
            self._init_task.cancel()
            self._init_task = None

        # Remove the materials path from the omni.client search path.
        omni.client.remove_default_search_path(self._path)

        del self.listener

        # remove algorithms
        factory = get_factory()
        factory.unregister_all(self._extId)

        kit_commands.unregister_module_commands(commands)

        if self._data_delegate:
            get_data_delegate_registry().deregister_data_delegate(self._data_delegate)
            del self._data_delegate

    async def _initialize(self, app, extensionPath):
        try:
            usd_context = omni.usd.get_context()
            tokens_iface = get_tokens_interface()

            settings = get_settings()

            if usd_file := settings.get("exts/omni.rtwt.controller/usd_file"):
                usd_file = tokens_iface.resolve(usd_file)
                logger.warning("Loading USD file: %s", usd_file)
                await usd_context.open_stage_async(usd_file)
            else:
                logger.error("No USD file specified in settings. Use 'exts/omni.rtwt.controller/usd_file' to set the path.")

            if layout := settings.get("exts/omni.rtwt.controller/layout"):
                layout = tokens_iface.resolve(f"{extensionPath}/layouts/{layout}.json")
                logger.warning("Loading layout: %s", layout)
                await omni.kit.app.get_app().next_update_async()
                QuickLayout.load_file(layout)

            if hide_ui := settings.get("exts/omni.rtwt.controller/hide_ui"):
                logger.warning("Hiding UI as per settings: %s", hide_ui)
                action_registry = get_action_registry()

                action = action_registry.get_action("omni.kit.ui.actions", "toggle_ui")
                action.execute(hide_ui)

                action = action_registry.get_action("omni.kit.viewport.actions", "toggle_camera_visibility")
                action.execute(visible=not hide_ui)

                action = action_registry.get_action("omni.kit.viewport.actions", "toggle_light_visibility")
                action.execute(visible=not hide_ui)

                action = action_registry.get_action("omni.kit.viewport.actions", "toggle_hud_visibility")
                action.execute(visible=not hide_ui)

            else:
                logger.warning("UI will be shown as per settings. Use 'exts/omni.rtwt.controller/hide_ui' to change this.")

            if disable_sel := settings.get_as_bool("exts/omni.rtwt.controller/disable_viewport_selection"):
                logger.warning("Disabling viewport selection as per settings: %s", disable_sel)

                viewport = get_active_viewport()
                assert viewport is not None, "No active viewport found to disable selection."
                self._selection_handle = disable_selection(viewport)
            else:
                logger.warning("Viewport selection will be enabled as per settings. Use 'exts/omni.rtwt.controller/disable_viewport_selection' to change this.")

        except Exception as e:
            logger.error("Error during extension initialization: %s", e)

        logger.warning("Extension initialization complete.")