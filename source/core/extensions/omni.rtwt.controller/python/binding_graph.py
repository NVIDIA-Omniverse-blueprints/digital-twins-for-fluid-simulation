# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""BindingGraph — the union of manifest bindings and stage-authored USD bindings.

The engine reads bindings from two sources, both producing the same :class:`BindingSpec` shape:

* the **manifest** ``[controls.<id>].bindings`` (the primary, plain-TOML path), and
* stage-authored multi-apply ``RtwtControlBindingAPI`` instances (the advanced, USD-native path),
  read via the same usdrt ``GetPrimsWithAppliedAPIName`` walk ``utils.apply_slider_transforms``
  uses, with instance properties named ``omni:rtwt:binding:<instance>:<prop>``.

A control's binding lives in exactly one place. A binding declared in BOTH the manifest and the
stage (same knobs + kind) is a double-declaration: the validator reports it; here the USD
duplicate is dropped (manifest wins) so the engine never applies an effect twice.
"""

from __future__ import annotations

from logging import getLogger

from omni.cae.core import usd_utils

from . import utils
from .manifest import BindingSpec

logger = getLogger(__name__)

_BINDING_API = "RtwtControlBindingAPI"
_NS = "omni:rtwt:binding"


class BindingGraph:
    def __init__(self, bindings: list):
        self._bindings = list(bindings)

    def bindings(self) -> list:
        return list(self._bindings)

    @classmethod
    def build(cls, registry, stage) -> "BindingGraph":
        """Collect manifest bindings (from every control) plus stage-authored USD bindings."""
        manifest_bindings: list = []
        for ctrl in registry.controls():
            manifest_bindings.extend(ctrl.spec.bindings)

        seen = {_dedupe_key(b) for b in manifest_bindings}
        merged = list(manifest_bindings)
        if stage is not None:
            for ub in _read_usd_bindings(stage):
                if _dedupe_key(ub) in seen:
                    logger.error(
                        "binding double-declared in manifest AND stage (knobs=%s kind=%s); "
                        "dropping the USD duplicate (a binding must live in exactly one place)",
                        ub.knobs, ub.kind,
                    )
                    continue
                seen.add(_dedupe_key(ub))
                merged.append(ub)
        return cls(merged)


def _dedupe_key(b: BindingSpec):
    return (frozenset(b.knobs), b.kind)


def _read_usd_bindings(stage) -> list:
    bindings: list = []
    for path in utils.get_rt_stage(stage).GetPrimsWithAppliedAPIName(_BINDING_API):
        prim = stage.GetPrimAtPath(str(path))
        if not prim or not prim.IsValid():
            continue
        for inst in usd_utils.get_instances(prim, _BINDING_API):
            bindings.append(_binding_from_instance(prim, inst))
    return bindings


def _binding_from_instance(prim, inst: str) -> BindingSpec:
    def attr(prop):
        return usd_utils.get_attribute(prim, f"{_NS}:{inst}:{prop}", quiet=True)

    knobs = attr("knobs") or []
    targets_rel = prim.GetRelationship(f"{_NS}:{inst}:targets")
    targets = targets_rel.GetForwardedTargets() if targets_rel else []
    return BindingSpec(
        kind=str(attr("type") or ""),
        knobs=tuple(str(k) for k in knobs),
        targets=tuple(str(t) for t in targets),
        variant_set=str(attr("variantSet") or ""),
        selection_expr=str(attr("selectionExpr") or ""),
        attribute=str(attr("attribute") or ""),
        material_on=str(attr("materialOn") or ""),
        material_off=str(attr("materialOff") or ""),
        callback=str(attr("callback") or ""),
        # The schema's visibleWhen gates the binding (engine treats it as when_expr).
        when_expr=str(attr("visibleWhen") or ""),
    )
