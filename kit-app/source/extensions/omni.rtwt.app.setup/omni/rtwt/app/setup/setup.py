# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import asyncio
from pathlib import Path

import carb.settings
import carb.tokens
import omni.ext
import omni.kit.app
import omni.kit.imgui as _imgui
import omni.kit.menu.utils
import omni.kit.viewport
import omni.ui as ui
import omni.usd
from omni.kit.mainwindow import get_main_window
from omni.kit.menu.utils import MenuLayout
from omni.kit.quicklayout import QuickLayout
from omni.kit.viewport.utility import get_viewport_from_window_name
from omni.kit.window.title import get_main_window_title

OUR_NAME = "omni.rtwt.app.setup"
SETTING_ROOT = f"/exts/${OUR_NAME}/"
SETTING_MENU_VISIBLE = SETTING_ROOT + "menu_visible"
SETTING_VIEWPORT_SPLASH = SETTING_ROOT + "viewport_splash"

COMMAND_MACRO_SETTING = "/exts/omni.kit.command_macro.core/"
COMMAND_MACRO_FILE_SETTING = COMMAND_MACRO_SETTING + "macro_file"

async def _load_layout(layout_file: str):
    """this private methods just help loading layout, you can use it in the Layout Menu"""
    await omni.kit.app.get_app().next_update_async()  # type: ignore
    QuickLayout.load_file(layout_file)

    # Set viewport to FILL
    viewport_api = get_viewport_from_window_name("Viewport")
    if viewport_api and hasattr(viewport_api, "fill_frame"):
        viewport_api.fill_frame = True


# This extension is mostly loading the Layout updating menu
class SetupExtension(omni.ext.IExt):
    # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # this extension is located on filesystem.
    def on_startup(self, _ext_id: str):
        self._assets_loaded = False

        asyncio.ensure_future(self._loading())

        # get the settings
        self._settings = carb.settings.get_settings()

        # get auto load stage name
        self._stage_url = self._settings.get_as_string("/app/auto_load_usd")

         # check if setup have benchmark macro file to activate - ignore setup auto_load_usd name, in order to run proper benchmark.
        benchmark_macro_file_name = self._settings.get(COMMAND_MACRO_FILE_SETTING)
        if benchmark_macro_file_name:
            self._stage_url = None

        # if no benchmark is activated (not applicable on production - provided macro file name will always be None) - load provided by setup stage.
        if self._stage_url:
            self._stage_url = carb.tokens.get_tokens_interface().resolve(self._stage_url)
            print(f"Loading {self._stage_url}")
            asyncio.ensure_future(self.__open_stage(self._stage_url))

        self._await_layout = asyncio.ensure_future(self._delayed_layout())
        # set up the menu and their layout
        self._setup_menu()

        # set up the Application Title
        window_title = get_main_window_title()
        if window_title and hasattr(window_title, "set_app_version"):
            window_title.set_app_version(self._settings.get_as_string("/app/titleVersion"))

        self._stage_sub = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(self._on_stage, name="Omni Kit Starter Setup")
        )

    async def _delayed_layout(self):
        # few frame delay to allow automatic Layout of window that want their own positions
        for _i in range(4):
            await omni.kit.app.get_app().next_update_async()  # type: ignore

        settings = carb.settings.get_settings()
        # setup the Layout for your app
        token = "${" + OUR_NAME + "}/layouts"
        layouts_path = carb.tokens.get_tokens_interface().resolve(token)
        layout_name = settings.get("/app/layout/name")
        layout_file = Path(layouts_path).joinpath(f"{layout_name}.json")

        # TODO: Some window will be float if not set visible here
        if layout_name == "staging":
            ui.Workspace.show_window("Preferences")

        asyncio.ensure_future(_load_layout(f"{layout_file}"))

        # using imgui directly to adjust some color and Variable
        imgui = _imgui.acquire_imgui()

        # DockSplitterSize is the variable that drive the size of the Dock Split connection
        imgui.push_style_var_float(_imgui.StyleVar.DockSplitterSize, 2)

    def _on_stage(self, stage_event):
        if self._stage_url:
            if stage_event.type == int(omni.usd.StageEventType.ASSETS_LOADED):
                self._assets_loaded = True
        # in case we are loading without specific stage - wait for default stage to be opened
        else:
            if stage_event.type == int(omni.usd.StageEventType.OPENED):
                self._assets_loaded = True

    async def _loading(self):
        pass

    def _setup_menu(self):
        # Menubar
        main_menu_bar = get_main_window().get_main_menu_bar()
        settings = carb.settings.get_settings()
        main_menu_bar.visible = settings.get_as_bool(SETTING_MENU_VISIBLE)

        self._menu_layout = [
            MenuLayout.Menu("File", remove=True),
            MenuLayout.Menu("Create", remove=True),
            MenuLayout.Menu("Tools", remove=True),
            MenuLayout.Menu("Help", remove=True),
            MenuLayout.Menu(
                "Window",
                [
                    MenuLayout.SubMenu("Browsers", remove=True),
                    MenuLayout.SubMenu("Viewport", remove=True),
                    MenuLayout.SubMenu("Animation", remove=True),
                    MenuLayout.SubMenu("Layout", remove=True),
                    MenuLayout.SubMenu("Visual Scripting", remove=True),
                    MenuLayout.Item("Content", remove=True),
                    MenuLayout.Item("Extensions", remove=True),
                ],
            ),
        ]
        omni.kit.menu.utils.add_layout(self._menu_layout)  # type: ignore

    async def __open_stage(self, url):
        # 10 frame delay to allow Layout
        for i in range(5):
            await omni.kit.app.get_app().next_update_async()  # type: ignore

        usd_context = omni.usd.get_context()
        usd_context.open_stage(url)  # type: ignore

    def on_shutdown(self):
        omni.kit.menu.utils.remove_layout(self._menu_layout)  # type: ignore
        self._menu_layout = None
        self._messaging.on_shutdown()
        self._messaging = None
