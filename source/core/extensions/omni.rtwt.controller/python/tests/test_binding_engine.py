# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Generic-path tests: the use-case-agnostic core drives a NON-aero workflow, plus the
control-manifest composition and validator behavior — none of which reference aero vocabulary."""

import os

import omni.kit.test
from pxr import Sdf, Usd

from omni.rtwt.controller import app_state, control_registry, validator, web_api
from omni.rtwt.controller.binding_contract import (
    SINGLE_VALUE_BINDING_KINDS,
    SUPPORTED_BINDING_KINDS,
)
from omni.rtwt.controller.binding_executor import BindingExecutor
from omni.rtwt.controller.binding_executor import _HANDLERS
from omni.rtwt.controller.binding_graph import BindingGraph
from omni.rtwt.controller.control_registry import ControlRegistry
from omni.rtwt.controller.manifest import BindingSpec, ControlSpec, ManifestLoader, WorkflowManifest

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestBindingEngine(omni.kit.test.AsyncTestCase):
    def _fake_manifest(self) -> WorkflowManifest:
        m = ManifestLoader.load(os.path.join(_FIXTURES, "fake_workflow.toml"))
        self.assertIsNotNone(m, "fake_workflow.toml failed to load")
        return m

    async def test_generic_workflow_drives_core(self):
        """The core engine applies a NON-aero workflow's Variant + Attribute bindings to a generic
        stage (core carries no specialization vocabulary)."""
        stage = Usd.Stage.CreateInMemory()
        widget = stage.DefinePrim("/World/Widget", "Xform")
        widget.CreateAttribute("color", Sdf.ValueTypeNames.String).Set("black")
        vset = widget.GetVariantSets().AddVariantSet("Shape")
        vset.AddVariant("Box")
        vset.AddVariant("Sphere")
        vset.SetVariantSelection("Box")

        registry = ControlRegistry.build(self._fake_manifest(), [])  # no aero schemas
        graph = BindingGraph.build(registry, None)  # manifest bindings only (skip usdrt read)
        BindingExecutor(stage, {"color": "red", "shape": "Sphere"}, graph.bindings()).apply()

        self.assertEqual(widget.GetVariantSet("Shape").GetVariantSelection(), "Sphere")
        self.assertEqual(widget.GetAttribute("color").Get(), "red")

    async def test_get_control_manifest_composes(self):
        """get_control_manifest composes knobs/readouts/views from any workflow (here non-aero)."""
        registry = ControlRegistry.build(self._fake_manifest(), [])
        out = web_api._compose_control_manifest(registry, None)
        self.assertEqual({k["key"] for k in out["knobs"]}, {"color", "shape"})
        shape = next(k for k in out["knobs"] if k["key"] == "shape")
        self.assertEqual(shape["values"], ["Box", "Sphere"])
        self.assertEqual(shape["role"], "inference")

    async def test_validator_flags_cache_values_on_non_inference(self):
        """cache_values require role='inference' (actionable validation error)."""
        bad = WorkflowManifest(
            id="x",
            controls={"v": ControlSpec(id="v", role="visualization", cache_values=("a", "b"))},
        )
        report = validator.validate_workflow(bad, [], stage=None)
        self.assertFalse(report.ok)
        self.assertTrue(any("cache_values" in e for e in report.errors), report.errors)

    async def test_validator_flags_undeclared_knob(self):
        """A binding referencing an undeclared knob is an error."""
        bad = WorkflowManifest(
            id="x",
            controls={
                "a": ControlSpec(
                    id="a",
                    role="visualization",
                    bindings=(BindingSpec(kind="Attribute", knobs=("ghost",), targets=("/p",), attribute="z"),),
                )
            },
        )
        report = validator.validate_workflow(bad, [], stage=None)
        self.assertFalse(report.ok)
        self.assertTrue(any("ghost" in e for e in report.errors), report.errors)

    async def test_binding_state_is_keyed_by_manifest_id_not_schema_short_key(self):
        """Bindings use declared control ids even when the schema/web short key differs."""
        manifest = WorkflowManifest(
            id="mapped",
            app_state_prim="/Custom/State",
            controls={
                "speedControl": ControlSpec(
                    id="speedControl",
                    schema_attr="example:app_state:speed",
                    role="inference",
                )
            },
        )
        registry = ControlRegistry.build(manifest, [])
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/Custom/State", "Scope")
        prim.CreateAttribute("example:app_state:speed", Sdf.ValueTypeNames.Float).Set(42.0)

        self.assertEqual(
            app_state._read_control_state(prim, registry),
            {"speedControl": 42.0},
        )
        self.assertEqual(registry.id_to_short(), {"speedControl": "speed"})
        self.assertEqual(registry.short_to_id(), {"speed": "speedControl"})

    async def test_duplicate_schema_short_keys_fail_validation_and_registry_build(self):
        """Different namespaces may not collapse onto the same web/runtime key."""
        manifest = WorkflowManifest(
            id="ambiguous",
            controls={
                "first": ControlSpec(id="first", schema_attr="one:state:mode"),
                "second": ControlSpec(id="second", schema_attr="two:state:mode"),
            },
        )
        report = validator.validate_workflow(manifest, [], stage=None)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("short key 'mode' is ambiguous" in error for error in report.errors),
            report.errors,
        )
        with self.assertRaisesRegex(ValueError, "ambiguous control short key 'mode'"):
            ControlRegistry.build(manifest, [])

    async def test_manifest_prim_paths_drive_runtime_lookup(self):
        """Controller runtime helpers use workflow paths, not /World conventions."""
        manifest = WorkflowManifest(
            id="custom_paths",
            app_state_prim="/Custom/State",
            inference_prim="/Custom/Prediction",
        )
        registry = ControlRegistry.build(manifest, [])
        stage = Usd.Stage.CreateInMemory()
        stage.DefinePrim("/Custom/State", "Scope")
        stage.DefinePrim("/Custom/Prediction", "Scope")

        previous = control_registry._WORKFLOW_REGISTRY
        control_registry._WORKFLOW_REGISTRY = registry
        try:
            self.assertEqual(str(web_api._app_state_prim(stage).GetPath()), "/Custom/State")
            self.assertEqual(str(web_api._inference_prim(stage).GetPath()), "/Custom/Prediction")
        finally:
            control_registry._WORKFLOW_REGISTRY = previous

    async def test_validator_rejects_unknown_binding_kind(self):
        manifest = WorkflowManifest(
            id="unknown_binding",
            controls={
                "mode": ControlSpec(
                    id="mode",
                    schema_attr="example:app_state:mode",
                    bindings=(BindingSpec(kind="Magic", knobs=("mode",)),),
                )
            },
        )
        report = validator.validate_workflow(manifest, [], stage=None)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("binding kind 'Magic' is unsupported" in error for error in report.errors),
            report.errors,
        )

    async def test_validator_rejects_fields_ignored_by_binding_handler(self):
        manifest = WorkflowManifest(
            id="ignored_field",
            controls={
                "mode": ControlSpec(
                    id="mode",
                    schema_attr="example:app_state:mode",
                    bindings=(
                        BindingSpec(
                            kind="Callback",
                            knobs=("mode",),
                            targets=("/World/WouldBeIgnored",),
                            callback="example.callback",
                        ),
                    ),
                )
            },
        )
        report = validator.validate_workflow(
            manifest,
            [],
            stage=None,
            callback_names={"example.callback"},
        )
        self.assertFalse(report.ok)
        self.assertTrue(
            any("does not support 'targets'" in error for error in report.errors),
            report.errors,
        )

    async def test_validator_requires_exactly_one_knob_for_single_value_handler(self):
        bindings = {
            "Attribute": BindingSpec(
                kind="Attribute",
                knobs=("primary", "secondary"),
                targets=("/World/Target",),
                attribute="value",
            ),
            "Material": BindingSpec(
                kind="Material",
                knobs=("primary", "secondary"),
                targets=("/World/Target",),
                material_on="Materials/On",
            ),
            "Relationship": BindingSpec(
                kind="Relationship",
                knobs=("primary", "secondary"),
                targets=("/World/Target",),
                attribute="selection",
            ),
            "Transform": BindingSpec(
                kind="Transform",
                knobs=("primary", "secondary"),
                params={"roi_rel": "example:roi"},
            ),
            "Visibility": BindingSpec(
                kind="Visibility",
                knobs=("primary", "secondary"),
                targets=("/World/Target",),
            ),
        }
        self.assertEqual(set(bindings), set(SINGLE_VALUE_BINDING_KINDS))

        for kind, binding in bindings.items():
            with self.subTest(kind=kind):
                manifest = WorkflowManifest(
                    id=f"ambiguous_{kind}",
                    controls={
                        "primary": ControlSpec(
                            id="primary",
                            schema_attr="example:app_state:primary",
                            bindings=(binding,),
                        ),
                        "secondary": ControlSpec(
                            id="secondary",
                            schema_attr="example:app_state:secondary",
                        ),
                    },
                )
                report = validator.validate_workflow(manifest, [], stage=None)
                self.assertFalse(report.ok)
                self.assertTrue(
                    any(
                        f"binding kind '{kind}' requires exactly one control id in knobs" in error
                        for error in report.errors
                    ),
                    report.errors,
                )

    async def test_validator_accepts_runtime_selection_placeholder_syntax(self):
        report = validator.ValidationReport()
        validator._check_binding_semantics(
            report,
            "control 'model.axis:choice-id'",
            BindingSpec(
                kind="Variant",
                knobs=("model.axis:choice-id", "mode"),
                targets=("/World/Model",),
                variant_set="Model",
                selection_expr="{model.axis:choice-id}_{mode}",
            ),
            {"model.axis:choice-id", "mode"},
            None,
        )
        self.assertTrue(report.ok, report.errors)

    async def test_validator_requires_one_variant_knob_without_selection_expr(self):
        manifest = WorkflowManifest(
            id="ambiguous_variant",
            controls={
                "primary": ControlSpec(
                    id="primary",
                    schema_attr="example:app_state:primary",
                    bindings=(
                        BindingSpec(
                            kind="Variant",
                            knobs=("primary", "secondary"),
                            targets=("/World/Model",),
                            variant_set="Model",
                        ),
                    ),
                ),
                "secondary": ControlSpec(
                    id="secondary",
                    schema_attr="example:app_state:secondary",
                ),
            },
        )
        report = validator.validate_workflow(manifest, [], stage=None)
        self.assertFalse(report.ok)
        self.assertTrue(
            any(
                "binding kind 'Variant' requires exactly one control id in knobs "
                "when selection_expr is empty"
                in error
                for error in report.errors
            ),
            report.errors,
        )

    async def test_validator_rejects_malformed_selection_placeholder(self):
        report = validator.ValidationReport()
        validator._check_binding_semantics(
            report,
            "control 'mode'",
            BindingSpec(
                kind="Variant",
                knobs=("mode",),
                targets=("/World/Model",),
                variant_set="Model",
                selection_expr="{bad id}",
            ),
            {"mode"},
            None,
        )
        self.assertFalse(report.ok)
        self.assertTrue(
            any("selection_expr contains a malformed placeholder" in error for error in report.errors),
            report.errors,
        )

    async def test_validator_rejects_unknown_stage_authored_binding_kind(self):
        manifest = WorkflowManifest(
            id="stage_binding",
            controls={
                "mode": ControlSpec(
                    id="mode",
                    schema_attr="example:app_state:mode",
                )
            },
        )
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/World/Binding", "Scope")
        prim.AddAppliedSchema("RtwtControlBindingAPI:bad")
        prim.CreateAttribute(
            "omni:rtwt:binding:bad:type",
            Sdf.ValueTypeNames.Token,
        ).Set("Magic")
        prim.CreateAttribute(
            "omni:rtwt:binding:bad:knobs",
            Sdf.ValueTypeNames.TokenArray,
        ).Set(["mode"])

        report = validator.validate_workflow(manifest, [], stage=stage)
        self.assertFalse(report.ok)
        self.assertTrue(
            any(
                "stage-authored binding 'bad'" in error
                and "binding kind 'Magic' is unsupported" in error
                for error in report.errors
            ),
            report.errors,
        )

    async def test_validator_requires_schema_attr_for_stateful_controls(self):
        manifest = WorkflowManifest(
            id="unmapped",
            controls={"mode": ControlSpec(id="mode", role="visualization")},
        )
        report = validator.validate_workflow(manifest, [], stage=None)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("schema_attr is required" in error for error in report.errors),
            report.errors,
        )

    async def test_validator_and_executor_binding_vocabularies_match(self):
        """A kind advertised by validation always has a runtime handler, and vice versa."""
        self.assertEqual(set(_HANDLERS), set(SUPPORTED_BINDING_KINDS))
