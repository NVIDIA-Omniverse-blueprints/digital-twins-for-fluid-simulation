# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import omni
from .ovapi import ALL_OMNIVERSE_API_OBJECTS
from .api.rtwt import initialize, deinitialize
import asyncio
import omni.kit.async_engine
import omni.kit.app
import carb

class WaitForRtx:
    """
    Helper class to wait for RTX to load
    """

    def __init__(self):
        self._wait = asyncio.Event()
        self._sub = (
            omni.usd.get_context()
            .get_rendering_event_stream()
            .create_subscription_to_push_by_type(int(omni.usd.StageRenderingEventType.NEW_FRAME), self._set_ready)
        )

    async def wait(self):
        await self._wait.wait()

    def _set_ready(self, _):
        self._wait.set()
        self._sub.unsubscribe()
        self._sub = None


class WaitForStageLoad:
    """
    Helper class to wait for Stage to load
    """

    def __init__(self):
        self._wait = asyncio.Event()
        self._sub = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_push_by_type(int(omni.usd.StageEventType.ASSETS_LOADED), self._set_ready)
        )

    async def wait(self):
        await self._wait.wait()

    def _set_ready(self, _):
        self._wait.set()
        self._sub.unsubscribe()
        self._sub = None


async def wait_for_rtx_and_stage_then_init():
    try:
        await WaitForRtx().wait()
        await WaitForStageLoad().wait()
        
        # Additional check to ensure stage is available
        stage = omni.usd.get_context().get_stage()
        if not stage:
            carb.log_warn("Stage is not available after waiting for stage load events. Waiting for additional frames...")
            # Wait for a few more frames to ensure stage is loaded
            for _ in range(10):
                await omni.kit.app.get_app().next_update_async()
                stage = omni.usd.get_context().get_stage()
                if stage:
                    carb.log_info("Stage is now available after waiting for additional frames")
                    break
        
        if stage:
            initialize()
        else:
            carb.log_error("Failed to initialize RTWT API: Stage is not available")
    except Exception as e:
        carb.log_error(f"Error during RTWT API initialization: {str(e)}")


class ApiExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str):
        try:
            omni.kit.async_engine.run_coroutine(wait_for_rtx_and_stage_then_init())
        except Exception as e:
            carb.log_error(f"Failed to start RTWT API extension: {str(e)}")

    def on_shutdown(self):
        for api in ALL_OMNIVERSE_API_OBJECTS:
            api.cleanup()
        deinitialize()
