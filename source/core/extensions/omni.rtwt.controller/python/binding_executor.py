# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""BindingExecutor — the generic USD-Controller binding engine.

Given the current control state (knob short-key -> value) and a set of bindings (from
``BindingGraph``), this applies each binding's effect via a per-kind handler, observing the
``Sdf.ChangeBlock`` discipline:

* **inside** the block (pure USD authoring): ``Variant`` (incl. composed ``selection_expr``),
  ``Attribute``, ``ColormapDomain`` / ``Callback`` (the specialization adapter returns pure
  attribute writes), ``Relationship``, ``Visibility``.
* **outside** the block (these fire Kit callbacks that must run after the block closes):
  ``Material`` (+ the Kit re-enable workaround), ``Transform``, ``Playback``, ``ViewportScale``.

The engine carries zero workflow vocabulary; aero-specific physics lives behind named callbacks
(``callbacks.CallbackRegistry``) supplied by a specialization.
"""

from __future__ import annotations

from logging import getLogger

import omni.timeline
from omni.cae.core import usd_utils
from omni.cae.schema import viz as cae_viz
from omni.kit.viewport.utility import get_active_viewport
from pxr import Gf, Sdf, UsdGeom, UsdShade

from . import expr, utils
from .binding_contract import SUPPORTED_BINDING_KINDS
from .callbacks import CallbackRegistry

logger = getLogger(__name__)

# Which change-block phase each binding kind runs in. Kinds firing Kit callbacks must run after
# the block closes.
_INSIDE = {"Variant", "Attribute", "ColormapDomain", "Callback", "Relationship", "Visibility"}
_OUTSIDE = {"Material", "Transform", "Playback", "ViewportScale"}


class BindingExecutor:
    def __init__(self, stage, control_state: dict, bindings: list, app_state_prim=None, callbacks=CallbackRegistry):
        self.stage = stage
        self.state = control_state
        self.bindings = bindings
        self.app_state_prim = app_state_prim
        self.callbacks = callbacks

    def apply(self) -> None:
        inside = [b for b in self.bindings if b.kind in _INSIDE]
        outside = [b for b in self.bindings if b.kind in _OUTSIDE]
        unknown = [b for b in self.bindings if b.kind not in SUPPORTED_BINDING_KINDS]
        for b in unknown:
            logger.warning("BindingExecutor: unknown binding kind '%s' (knobs=%s)", b.kind, b.knobs)

        with Sdf.ChangeBlock():
            for b in inside:
                self._dispatch(b)
        # Outside the change block: these rely on Kit callbacks that fire after it closes.
        for b in outside:
            self._dispatch(b)

    def _dispatch(self, b) -> None:
        handler = _HANDLERS.get(b.kind)
        if handler is None:
            return
        try:
            handler(self, b)
        except Exception as exc:  # noqa: BLE001 - one bad binding must not abort the rest
            logger.error("BindingExecutor: binding kind '%s' (knobs=%s) failed: %s", b.kind, b.knobs, exc)

    # -- helpers ------------------------------------------------------------
    def _knob_value(self, b):
        return self.state.get(b.knobs[0]) if b.knobs else None

    def _gated(self, b) -> bool:
        return expr.eval_when(b.when_expr, self.state)


# ---------------------------------------------------------------------------
# Per-kind handlers (inside the change block)
# ---------------------------------------------------------------------------
def _handle_variant(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    if b.selection_expr:
        value = expr.eval_selection(b.selection_expr, ex.state)
    else:
        value = str(ex._knob_value(b))
    for target in b.targets:
        prim = ex.stage.GetPrimAtPath(target)
        if not prim or not prim.IsValid():
            logger.warning("Variant target %s not found", target)
            continue
        vsets = prim.GetVariantSets()
        if vsets.HasVariantSet(b.variant_set):
            vsets.GetVariantSet(b.variant_set).SetVariantSelection(value)
        else:
            logger.warning("Variant set '%s' not found on %s", b.variant_set, target)


def _handle_attribute(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    value = ex._knob_value(b)
    for target in b.targets:
        prim = ex.stage.GetPrimAtPath(target)
        if not prim or not prim.IsValid():
            logger.warning("Attribute target %s not found", target)
            continue
        attr = prim.GetAttribute(b.attribute)
        if attr:
            attr.Set(value)
        else:
            logger.warning("Attribute '%s' not found on %s", b.attribute, target)


def _handle_callback(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    fn = ex.callbacks.get(b.callback)
    if fn is None:
        logger.error("callback '%s' is not registered (ensure the specialization hooks extension is enabled)", b.callback)
        return
    for write in fn(ex.state):
        try:
            prim_path, attr_name, value = write
        except (TypeError, ValueError):
            logger.error("callback '%s' returned a malformed write: %r", b.callback, write)
            continue
        _apply_write(ex.stage, prim_path, attr_name, value)


def _handle_relationship(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    value = ex._knob_value(b)
    if value is None:
        return
    for target in b.targets:
        prim = ex.stage.GetPrimAtPath(target)
        if prim and prim.IsValid():
            prim.CreateRelationship(b.attribute).SetTargets([Sdf.Path(str(value))])


def _handle_visibility(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    visible = bool(ex._knob_value(b))
    for target in b.targets:
        prim = ex.stage.GetPrimAtPath(target)
        if prim and prim.IsValid():
            imageable = UsdGeom.Imageable(prim)
            if visible:
                imageable.MakeVisible()
            else:
                imageable.MakeInvisible()


# ---------------------------------------------------------------------------
# Per-kind handlers (outside the change block — fire Kit callbacks)
# ---------------------------------------------------------------------------
def _handle_material(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    on = bool(ex._knob_value(b))
    sub = b.material_on if on else b.material_off
    if not sub:
        return
    for target in b.targets:
        prim = ex.stage.GetPrimAtPath(target)
        if not prim or not prim.IsValid():
            logger.warning("Material target %s not found", target)
            continue
        mat_path = prim.GetPath().AppendPath(sub)
        mat_prim = ex.stage.GetPrimAtPath(mat_path)
        if not mat_prim or not mat_prim.IsValid():
            logger.warning("Material not found: %s", mat_path)
            continue
        binding_api = UsdShade.MaterialBindingAPI(prim)
        if binding_api.GetDirectBinding().GetMaterialPath() != mat_path:
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(
                UsdShade.Material(mat_prim),
                UsdShade.Tokens.weakerThanDescendants,
            )
            # A material-binding change alone does not re-trigger the operator, so toggle
            # enabled off then on to force it to re-execute.
            op_api = cae_viz.OperatorAPI(prim)
            op_api.CreateEnabledAttr().Set(False)
            op_api.CreateEnabledAttr().Set(True)


def _handle_transform(ex: BindingExecutor, b) -> None:
    if not ex._gated(b):
        return
    if ex.app_state_prim is None:
        return
    roi_rel = b.params.get("roi_rel", "omni:rtwt:app_state:roi")
    slider_value = int(ex._knob_value(b) or 0)
    roi_prim = usd_utils.get_target_prim(ex.app_state_prim, roi_rel)
    utils.apply_slider_transforms(ex.stage, roi_prim, slider_value)


def _handle_playback(ex: BindingExecutor, b) -> None:
    should_play = ex._gated(b)
    timeline = omni.timeline.get_timeline_interface()
    if should_play:
        timeline.play()
    else:
        timeline.stop()


def _handle_viewport_scale(ex: BindingExecutor, b) -> None:
    scale = b.params.get("on", 2.0) if ex._gated(b) else b.params.get("off", 1.0)
    viewport = get_active_viewport()
    if viewport:
        viewport.set_texture_resolution_scale(float(scale))


_HANDLERS = {
    "Variant": _handle_variant,
    "Attribute": _handle_attribute,
    "ColormapDomain": _handle_callback,
    "Callback": _handle_callback,
    "Relationship": _handle_relationship,
    "Visibility": _handle_visibility,
    "Material": _handle_material,
    "Transform": _handle_transform,
    "Playback": _handle_playback,
    "ViewportScale": _handle_viewport_scale,
}


def _apply_write(stage, prim_path: str, attr_name: str, value) -> None:
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        logger.warning("callback write target prim not found: %s", prim_path)
        return
    type_name = _infer_value_type(value)
    if type_name is None:
        attr = prim.GetAttribute(attr_name)
        if attr:
            attr.Set(value)
    else:
        prim.CreateAttribute(attr_name, type_name).Set(value)


def _infer_value_type(value):
    if isinstance(value, Gf.Vec2f):
        return Sdf.ValueTypeNames.Float2
    if isinstance(value, Gf.Vec3f):
        return Sdf.ValueTypeNames.Float3
    if isinstance(value, bool):
        return Sdf.ValueTypeNames.Bool
    if isinstance(value, float):
        return Sdf.ValueTypeNames.Float
    if isinstance(value, int):
        return Sdf.ValueTypeNames.Int
    if isinstance(value, str):
        return Sdf.ValueTypeNames.Token
    return None
