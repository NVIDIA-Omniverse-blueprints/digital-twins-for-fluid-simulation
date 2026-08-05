# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Workflow-manifest loader for the use-case-agnostic controller.

A *workflow manifest* is a plain-text TOML file declaring a workflow's controls (knobs), their
roles and widgets, knob->effect bindings, the inference cache grid, output fields, readouts, and
views. It is the **primary** authoring surface — plain TOML, no USD authoring — for "what this
workflow controls / outputs / visualizes." (Stage-authored ``RtwtControlBindingAPI`` prims are an
advanced alternative, read by ``binding_graph.py``.)

The controller resolves the manifest path from the carb setting

    exts."omni.rtwt.controller".workflow_manifest = "${app}/../rtwt/workflow/workflow.toml"

Core ships no manifest, so a missing/unset manifest yields ``None`` and the controller simply has
no workflow: delete the specialization and core still launches.

Authority: the USD AppState schema is the typed-knob substrate (attribute types, ``allowedTokens``,
the authored runtime default on the configured ``app_state_prim``); the manifest layers
role/widget/bounds/bindings/cache-grid/readouts/views on top. A control's runtime *default* has
exactly one authority — the value authored on the app-state prim — so a ``ControlSpec`` carries no
``default`` field.
"""

from __future__ import annotations

import os
import tomllib  # stdlib (Python 3.11+)
from dataclasses import dataclass, field
from logging import getLogger

import carb.tokens

logger = getLogger(__name__)


@dataclass(frozen=True)
class BindingSpec:
    """One knob->effect binding. The union of the manifest TOML keys and the
    ``RtwtControlBindingAPI`` properties — one shape, two authoring sources."""

    kind: str
    knobs: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    variant_set: str = ""
    selection_expr: str = ""
    attribute: str = ""
    material_on: str = ""
    material_off: str = ""
    callback: str = ""
    when_expr: str = ""
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ControlSpec:
    """A single control (knob). ``role`` drives cache-relevance: ``inference`` controls feed the
    cache key + the pre-cache product; ``visualization``/``view`` controls do not."""

    id: str
    schema_attr: str = ""
    role: str = "visualization"
    widget: str = ""
    group: str = ""
    label: str = ""
    unit: str | None = None
    values: tuple = ()
    bounds: dict = field(default_factory=dict)
    cache_values: tuple = ()
    images: dict = field(default_factory=dict)
    visible_when: str = ""
    bindings: tuple[BindingSpec, ...] = ()


@dataclass(frozen=True)
class OutputSpec:
    """A model-output field declaration. ``data_format`` keeps core from assuming every
    analysis is a dense voxel grid."""

    id: str
    model_output: str = ""
    target: str = ""
    field_name: str = ""
    role: str = ""
    label: str = ""
    units: str = ""
    data_format: str = ""
    visualizations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadoutSpec:
    """A non-knob value surfaced to the UI (e.g. a colormap transfer function or a scalar stat)."""

    key: str
    type: str
    label: str = ""
    domain_source: str = ""
    field: str = ""


@dataclass(frozen=True)
class ViewSpec:
    """A named camera/view. ``on_select`` is an optional effect (e.g. toggle playback)."""

    name: str
    thumbnail: str = ""
    on_select: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ComparisonResultSet:
    """One pre-baked comparison result set; ``npz`` is its cache filename."""

    npz: str = ""


@dataclass(frozen=True)
class ComparisonSpec:
    """The ``[comparison]`` table: the comparison view's result sets + the default to show.

    The result-set names and their npz filenames are data, not code; a specialization callback maps
    the selected name to the inference ``resultSetOverride``. Absent table -> ``comparison`` is
    ``None`` on the manifest."""

    default_result_set: str = ""
    result_sets: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowManifest:
    """The fully-parsed, immutable manifest. ``controls``/``outputs`` are keyed by id."""

    id: str
    label: str = ""
    app_state_prim: str = "/World/AppState"
    inference_prim: str = "/World/Inference"
    default_stage: str = ""
    title: str = ""
    controls: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    readouts: tuple = ()
    views: tuple = ()
    comparison: "ComparisonSpec | None" = None


def _parse_binding(raw: dict) -> BindingSpec:
    return BindingSpec(
        kind=str(raw.get("kind", "")),
        knobs=tuple(raw.get("knobs", ())),
        targets=tuple(raw.get("targets", ())),
        variant_set=str(raw.get("variant_set", "")),
        selection_expr=str(raw.get("selection_expr", "")),
        attribute=str(raw.get("attribute", "")),
        material_on=str(raw.get("material_on", "")),
        material_off=str(raw.get("material_off", "")),
        callback=str(raw.get("callback", "")),
        when_expr=str(raw.get("when_expr", "")),
        params=dict(raw.get("params", {})),
    )


def _parse_control(cid: str, raw: dict) -> ControlSpec:
    bindings = tuple(_parse_binding(b) for b in (raw.get("bindings") or []))
    return ControlSpec(
        id=cid,
        schema_attr=str(raw.get("schema_attr", "")),
        role=str(raw.get("role", "visualization")),
        widget=str(raw.get("widget", "")),
        group=str(raw.get("group", "")),
        label=str(raw.get("label", "")),
        unit=raw.get("unit"),
        values=tuple(raw.get("values", ())),
        bounds=dict(raw.get("bounds", {})),
        cache_values=tuple(raw.get("cache_values", ())),
        images=dict(raw.get("images", {})),
        # Accept either TOML-idiomatic snake_case or the USD-attr camelCase spelling.
        visible_when=str(raw.get("visible_when", raw.get("visibleWhen", ""))),
        bindings=bindings,
    )


def _parse_output(oid: str, raw: dict) -> OutputSpec:
    return OutputSpec(
        id=oid,
        model_output=str(raw.get("model_output", "")),
        target=str(raw.get("target", "")),
        field_name=str(raw.get("field_name", "")),
        role=str(raw.get("role", "")),
        label=str(raw.get("label", "")),
        units=str(raw.get("units", "")),
        data_format=str(raw.get("data_format", "")),
        visualizations=tuple(raw.get("visualizations", ())),
    )


def _parse_comparison(raw: dict) -> ComparisonSpec | None:
    """Parse the ``[comparison]`` table; ``None`` when absent."""
    if not raw:
        return None
    result_sets = {
        name: ComparisonResultSet(npz=str(rs.get("npz", "")))
        for name, rs in (raw.get("result_sets") or {}).items()
    }
    return ComparisonSpec(
        default_result_set=str(raw.get("default_result_set", "")),
        result_sets=result_sets,
    )


def _parse(data: dict) -> WorkflowManifest | None:
    wf = data.get("workflow") or {}
    wid = wf.get("id")
    if not wid:
        logger.error("workflow manifest missing required [workflow].id")
        return None

    controls = {cid: _parse_control(cid, c) for cid, c in (data.get("controls") or {}).items()}
    outputs = {oid: _parse_output(oid, o) for oid, o in (data.get("outputs") or {}).items()}
    readouts = tuple(
        ReadoutSpec(
            key=str(r.get("key", "")),
            type=str(r.get("type", "")),
            label=str(r.get("label", "")),
            domain_source=str(r.get("domainSource", r.get("domain_source", ""))),
            field=str(r.get("field", "")),
        )
        for r in (data.get("readouts") or [])
    )
    views = tuple(
        ViewSpec(
            name=str(v.get("name", "")),
            thumbnail=str(v.get("thumbnail", "")),
            on_select=dict(v.get("onSelect", v.get("on_select", {})) or {}),
        )
        for v in (data.get("views") or [])
    )

    comparison = _parse_comparison(data.get("comparison") or {})

    return WorkflowManifest(
        id=str(wid),
        label=str(wf.get("label", "")),
        app_state_prim=str(wf.get("app_state_prim", "/World/AppState")),
        inference_prim=str(wf.get("inference_prim", "/World/Inference")),
        default_stage=str(wf.get("default_stage", "")),
        title=str(wf.get("title", "")),
        controls=controls,
        outputs=outputs,
        readouts=readouts,
        views=views,
        comparison=comparison,
    )


class ManifestLoader:
    """Loads a workflow manifest from a TOML file. Tolerant: a missing/unset/invalid manifest
    returns ``None`` rather than raising, so core degrades cleanly to "no workflow"."""

    @staticmethod
    def load(path: str | None) -> WorkflowManifest | None:
        if not path:
            return None
        resolved = os.path.normpath(carb.tokens.get_tokens_interface().resolve(path))
        if not os.path.isfile(resolved):
            logger.warning("workflow manifest not found at %s", resolved)
            return None
        try:
            with open(resolved, "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            logger.error("failed to read/parse workflow manifest %s: %s", resolved, exc)
            return None
        return _parse(data)

    @staticmethod
    def load_configured() -> WorkflowManifest | None:
        """Load the manifest named by the controller's ``workflow_manifest`` carb setting."""
        from . import schema_settings

        return ManifestLoader.load(schema_settings.workflow_manifest_path())
