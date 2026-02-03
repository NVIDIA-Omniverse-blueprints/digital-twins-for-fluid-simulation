# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.
import asyncio
import logging
import threading

from omni.kit.async_engine import run_coroutine
from omni.stageupdate import get_stage_update_interface
from carb.settings import get_settings
from omni.usd import get_context
from .controller import Controller


logger = logging.getLogger(__name__)


class Listener:
    """Listener that stage/prim notification events from pxr.Usd."""

    def __init__(self):
        self._init_task: asyncio.Task = None
        self._update_counter = 0

        stage_update_iface = get_stage_update_interface()
        self._stage_subscription = stage_update_iface.create_stage_update_node(
            "omni.rtwt.controller",
            on_attach_fn=self.on_attach,
            on_detach_fn=self.on_detach,
            on_update_fn=self.on_update
        )

        self._dlss_resets_on = True

        if get_context().get_stage():
            # if stage is already attached, enqueue sync
            # else on_attach will handle it.
            self.enqueue_init()

    def __del__(self):
        if self._init_task is not None:
            self._init_task.cancel()
        del self._stage_subscription
        Controller.reset_instance()

    def on_attach(self, stageId, metersPerUnit):
        logger.info("on_attach %s (%s) %s", str(stageId), type(stageId), str(metersPerUnit))
        Controller.reset_instance()
        self.enqueue_init()

    def on_detach(self):
        logger.info("on_detach")
        Controller.reset_instance()
        self.enqueue_init()

    def enqueue_init(self):
        assert threading.current_thread() is threading.main_thread()
        if self._init_task is None or self._init_task.done():
            logger.warning("enqueuing init task")
            self._init_task = run_coroutine(self._init_controller())

    async def _init_controller(self):
        assert threading.current_thread() is threading.main_thread()
        stage = get_context().get_stage()
        if not stage:
            logger.warning("No stage found")
            return

        if Controller.get_instance() is None or Controller.get_instance().stage != stage:
            Controller.reset_instance()

            try:
                controller = Controller()
                await controller.initialize(stage)
                Controller.set_instance(controller)
            except Exception as e:
                logger.error(f"Failed to initialize controller: {e}")
                logger.error("Current stage is not setup for inference data.")

    def on_update(self, _1, _2):
        assert threading.current_thread() is threading.main_thread()
        if self._update_counter % 100 == 0:
            logger.debug("in update")

        self._update_counter += 1
        if controller := Controller.get_instance():
            changed, renderer_reset_needed = controller.update()

            if self._dlss_resets_on:
                get_settings().set_bool('rtx-transient/post/dlss/forceParamReset', False)
            
            if changed:
                if renderer_reset_needed and self._dlss_resets_on:
                    get_settings().set_bool('rtx-transient/post/dlss/forceParamReset', True)
                logger.info("Controller changed and updated")