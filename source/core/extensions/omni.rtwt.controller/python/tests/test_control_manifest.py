# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Generic-path proof — the control contract is use-case-agnostic at the frontend.

A use-case's UI is *legitimately custom* (there are too many possible experiences to generalize
the presentation). What MUST stay general is the **functional control contract** that any UI
consumes: ``get_control_manifest`` (knobs/readouts/views) + ``get_state``/``set_state`` over the
generic ``app_streamer.js`` transport.

This test proves that contract carries no aero vocabulary by mapping a NON-aero workflow's knobs
to generic widget descriptors with a tiny reference factory. It is the frontend analog of the CI
core-boundary guard (``tools/ci/check_core_boundary.py``): if a non-aero workflow's manifest maps
cleanly to widgets, the contract is genuinely use-case-agnostic.

The factory below is a *reference/proof*, not a shipped renderer — a custom UI maps the manifest
however it likes; this only documents, by example, that the mapping is mechanical and aero-free.
"""

import os

import omni.kit.test

from omni.rtwt.controller import web_api
from omni.rtwt.controller.control_registry import ControlRegistry
from omni.rtwt.controller.manifest import ControlSpec, ManifestLoader, WorkflowManifest

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# Generic widget-hint -> UI widget type. The manifest's ``widget`` is a hint; a UI maps it to a
# concrete control. ``custom:<impl>`` defers to a use-case-supplied widget (the contract only names
# it). Anything unknown is surfaced as "unsupported" rather than guessed — the generic path is
# deliberately small; rich UIs override.
_WIDGET_TYPES = {
    "select": "dropdown",
    "toggle": "buttongroup",
    "switch": "switch",
    "slider": "range",
    "imageTiles": "imageSelect",
}


def widget_descriptor(knob: dict) -> dict:
    """Pure function: a ``get_control_manifest`` knob (the wire shape a UI receives) -> a generic
    widget descriptor. No aero knowledge — works for any workflow's knobs."""
    widget = knob.get("widget") or ""
    desc = {"key": knob["key"], "label": knob.get("label") or knob["key"]}
    if widget.startswith("custom:"):
        desc["type"] = "custom"
        desc["impl"] = widget.split(":", 1)[1]  # use-case supplies this widget; contract just names it
        return desc
    desc["type"] = _WIDGET_TYPES.get(widget, "unsupported")
    values = knob.get("values")
    if isinstance(values, dict):
        desc["bounds"] = values          # range/slider bounds {min, max, step}
    elif isinstance(values, list):
        desc["options"] = values         # discrete options
    return desc


class TestControlManifestGenericPath(omni.kit.test.AsyncTestCase):
    async def test_fixture_workflow_maps_to_generic_widgets(self):
        """The non-aero fake workflow loads from TOML, composes via the real contract, and every
        knob maps to a generic widget descriptor — proving the contract has no aero vocabulary."""
        manifest = ManifestLoader.load(os.path.join(_FIXTURES, "fake_workflow.toml"))
        self.assertIsNotNone(manifest, "fake_workflow.toml failed to load")
        self.assertEqual(manifest.outputs["stress"].target, "/World/Result")
        self.assertEqual(manifest.outputs["stress"].field_name, "Stress")
        registry = ControlRegistry.build(manifest, [])          # [] = no aero schemas
        out = web_api._compose_control_manifest(registry, None)  # stage=None -> unit-testable

        descs = {k["key"]: widget_descriptor(k) for k in out["knobs"]}
        self.assertEqual(set(descs), {"color", "shape"})
        # select + discrete values -> dropdown with options
        self.assertEqual(descs["shape"]["type"], "dropdown")
        self.assertEqual(descs["shape"]["options"], ["Box", "Sphere"])
        # custom:<impl> -> a custom descriptor naming the external widget the UI supplies
        self.assertEqual(descs["color"]["type"], "custom")
        self.assertEqual(descs["color"]["impl"], "my.module:ColorWidget")

    async def test_factory_covers_common_widget_kinds(self):
        """The reference factory maps the common widget hints (select/toggle/switch/slider) to
        generic descriptors."""
        manifest = WorkflowManifest(
            id="widgets",
            controls={
                "mode":   ControlSpec(id="mode",   role="visualization", widget="select", values=("A", "B")),
                "active": ControlSpec(id="active", role="visualization", widget="toggle", values=("On", "Off")),
                "flag":   ControlSpec(id="flag",   role="visualization", widget="switch"),
                "scale":  ControlSpec(id="scale",  role="visualization", widget="slider",
                                      bounds={"min": 0, "max": 10, "step": 1}),
            },
        )
        registry = ControlRegistry.build(manifest, [])
        out = web_api._compose_control_manifest(registry, None)
        descs = {k["key"]: widget_descriptor(k) for k in out["knobs"]}

        self.assertEqual(descs["mode"]["type"], "dropdown")
        self.assertEqual(descs["mode"]["options"], ["A", "B"])
        self.assertEqual(descs["active"]["type"], "buttongroup")
        self.assertEqual(descs["flag"]["type"], "switch")
        self.assertEqual(descs["scale"]["type"], "range")
        self.assertEqual(descs["scale"]["bounds"], {"min": 0, "max": 10, "step": 1})

    async def test_no_aero_vocabulary_in_descriptors(self):
        """Defensive: nothing the contract emits for a non-aero workflow leaks aero terms (a
        runtime echo of the CI boundary guard)."""
        manifest = ManifestLoader.load(os.path.join(_FIXTURES, "fake_workflow.toml"))
        out = web_api._compose_control_manifest(ControlRegistry.build(manifest, []), None)
        blob = repr(out).lower()
        for term in ("spoiler", "rims", "mirror", "velocity", "aero", "wind"):
            self.assertNotIn(term, blob, f"aero vocabulary {term!r} leaked into the generic manifest")
