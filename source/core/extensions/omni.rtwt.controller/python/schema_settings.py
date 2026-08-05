# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Carb-configurable schema names for the use-case-agnostic controller.

The controller introspects a workflow's USD AppState schema(s) to discover its knobs. The
schema *names* are specialization vocabulary, so core never hardcodes them: a workflow supplies
them via the carb setting

    exts."omni.rtwt.controller".app_state_api_schemas = ["YourWorkflowAppStateAPI"]

Core's default is empty, so deleting the specialization leaves a buildable, launchable core that
simply has no app-state knobs.
"""

import os

from carb.settings import get_settings
from carb.tokens import get_tokens_interface

_CONTROLLER_EXT = "omni.rtwt.controller"


def app_state_api_schemas() -> list[str]:
    """Return the applied AppState API-schema names the controller introspects for knobs.

    Empty when no workflow is configured (core-only). Order is preserved as authored.
    """
    value = get_settings().get(f"/exts/{_CONTROLLER_EXT}/app_state_api_schemas")
    return [str(name) for name in value] if value else []


def workflow_manifest_path() -> str | None:
    """Resolve the configured workflow-manifest path (carb ``${...}`` tokens expanded).

    Returns None when unset (core-only / no workflow). Normalized lexically so that tokens
    like ``${app}/../rtwt/workflow/workflow.toml`` resolve against the intended sibling
    directory rather than following symlinks first.
    """
    raw = get_settings().get_as_string(f"/exts/{_CONTROLLER_EXT}/workflow_manifest")
    if not raw:
        return None
    return os.path.normpath(get_tokens_interface().resolve(raw))
