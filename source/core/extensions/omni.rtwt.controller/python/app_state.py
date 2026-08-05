# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

from logging import getLogger

from omni.cae.viz.execution_context import ExecutionContext
from omni.cae.viz.operator import operator
from pxr import Usd

from . import control_registry
from .binding_executor import BindingExecutor
from .binding_graph import BindingGraph

logger = getLogger(__name__)


@operator()
class AppStateOperator:
    """Apply the web-application state prim to the live scene via the binding engine.

    Triggered whenever a prim carrying the workflow's configured app-state API schemas is
    dirtied (typically by a web-API request). It reads the current control values and drives the
    **declarative binding engine**: the workflow manifest (plus optional stage-authored
    RtwtControlBindingAPI prims) maps each knob to its effect — variant / attribute / colormap /
    material / transform / playback / viewport. Changing what the surrogate controls is therefore a
    manifest + schema edit, never a change to this operator. The engine carries zero workflow
    vocabulary; specialization-specific physics lives behind named callbacks supplied by a hooks
    extension.
    """

    prim_type: str = "Prim"
    # Populated in Extension.on_startup from exts."omni.rtwt.controller".app_state_api_schemas.
    # Left empty here so core hardcodes no specialization schema vocabulary; the operator is only
    # registered when a workflow supplies its schema names (an empty api_schemas set would
    # subset-match every untyped prim).
    api_schemas: set[str] = set()
    optional_api_schemas: set[str] = set()

    async def exec(self, prim: Usd.Prim, device: str, context: ExecutionContext):
        """Read the app-state prim and apply every manifest/stage binding to the live scene."""
        registry = control_registry.get_workflow_registry()
        if registry is None:
            logger.warning("AppStateOperator: no workflow manifest loaded; nothing to apply")
            return

        expected_path = registry.manifest.app_state_prim
        if str(prim.GetPath()) != expected_path:
            logger.warning(
                "AppStateOperator: ignoring app-state API prim '%s'; workflow '%s' declares '%s'",
                prim.GetPath(),
                registry.manifest.id,
                expected_path,
            )
            return

        stage = prim.GetStage()
        control_state = _read_control_state(prim, registry)
        graph = BindingGraph.build(registry, stage)
        BindingExecutor(stage, control_state, graph.bindings(), app_state_prim=prim).apply()


def _read_control_state(prim: Usd.Prim, registry) -> dict:
    """Map each manifest control id to its current value on the app-state prim.

    The value authored on the manifest's ``app_state_prim`` (or the schema fallback) is the single
    source of truth for a control's runtime value — there is no separate manifest default.
    Bindings refer to manifest control ids, which need not equal schema short keys; the registry
    performs that mapping explicitly.
    """
    state: dict = {}
    for control_id, full in registry.id_to_full().items():
        attr = prim.GetAttribute(full)
        if attr:
            state[control_id] = attr.Get()
    return state
