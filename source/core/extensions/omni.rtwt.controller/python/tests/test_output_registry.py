# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Output-registry drift guards for native Kit-CAE 3 OmniSci result datasets.

The manifest ``[outputs]`` declaration, the inference prim's
``RtwtResultFieldSelectionAPI`` instances, and the target dataset's paired
``OmniSciFieldAPI`` / ``OmniSciArrayAPI`` instances must agree. These tests
exercise the complete mapping without relying on the auto-aero specialization.
"""

import omni.kit.test
from pxr import Gf, OmniSci, OmniSciVtk, Sdf, Usd

from omni.rtwt.controller import validator
from omni.rtwt.controller.manifest import OutputSpec, WorkflowManifest

_INFERENCE_PRIM = "/World/Inference"
_RESULTS_API = "RtwtInferenceResultsAPI"


def _define_result_dataset(
    stage: Usd.Stage,
    path: str,
    fields: tuple[str, ...],
    *,
    marker: bool = True,
    grid_contract: bool = True,
    omit_array: frozenset[str] = frozenset(),
    omit_field: frozenset[str] = frozenset(),
) -> Usd.Prim:
    """Define one native OmniSci result dataset with the requested field contracts."""
    dataset = OmniSci.Dataset.Define(stage, path).GetPrim()
    if grid_contract:
        grid_path = f"{path}GridContract"
        grid = OmniSci.Dataset.Define(stage, grid_path).GetPrim()
        image_data_api = OmniSciVtk.ImageDataAPI.Apply(grid)
        image_data_api.CreateMinExtentAttr(Gf.Vec3i(2, 3, 4))
        image_data_api.CreateMaxExtentAttr(Gf.Vec3i(3, 4, 4))
        dataset.GetReferences().AddInternalReference(grid.GetPath())
    if marker:
        dataset.AddAppliedSchema(_RESULTS_API)
    for name in fields:
        if name not in omit_field:
            field_api = OmniSci.FieldAPI.Apply(dataset, name)
            field_api.CreateNameAttr(name)
            field_api.CreateAssociationAttr("node")
        if name not in omit_array:
            OmniSci.ArrayAPI.Apply(dataset, name)
    return dataset


def _author_selection(
    inference_prim: Usd.Prim,
    output_id: str,
    target: str,
    field_name: str,
) -> None:
    inference_prim.AddAppliedSchema(f"{validator._RESULT_FIELD_API}:{output_id}")
    inference_prim.CreateRelationship(
        f"omni:rtwt:result_field_selection:{output_id}:target"
    ).SetTargets([target])
    inference_prim.CreateAttribute(
        f"omni:rtwt:result_field_selection:{output_id}:fieldName",
        Sdf.ValueTypeNames.Token,
    ).Set(field_name)


def _stage(
    selections: dict[str, tuple[str, str]],
    datasets: dict[str, tuple[str, ...]],
) -> Usd.Stage:
    stage = Usd.Stage.CreateInMemory()
    inference_prim = stage.DefinePrim(_INFERENCE_PRIM, "Scope")
    for output_id, (target, field_name) in selections.items():
        _author_selection(inference_prim, output_id, target, field_name)
    for target, fields in datasets.items():
        _define_result_dataset(stage, target, fields)
    return stage


def _manifest(outputs: dict[str, tuple[str, str]]) -> WorkflowManifest:
    return WorkflowManifest(
        id="reg_test",
        inference_prim=_INFERENCE_PRIM,
        outputs={
            output_id: OutputSpec(
                id=output_id,
                target=target,
                field_name=field_name,
            )
            for output_id, (target, field_name) in outputs.items()
        },
    )


def _check(manifest: WorkflowManifest, stage: Usd.Stage) -> validator.ValidationReport:
    report = validator.ValidationReport()
    validator._check_outputs(report, manifest, stage)
    return report


class TestOutputRegistryDriftGuard(omni.kit.test.AsyncTestCase):
    async def test_native_dataset_mapping_agreement_is_clean(self):
        outputs = {
            "alpha": ("/World/Results", "Temperature"),
            "beta": ("/World/Results", "Pressure"),
        }
        stage = _stage(outputs, {"/World/Results": ("Temperature", "Pressure")})

        report = _check(_manifest(outputs), stage)

        self.assertTrue(
            stage.GetPrimAtPath("/World/Results").HasAPI(
                OmniSciVtk.ImageDataAPI
            )
        )
        self.assertEqual(report.errors, [], f"unexpected errors: {report.errors}")
        self.assertEqual(report.warnings, [], f"unexpected warnings: {report.warnings}")

    async def test_stage_instance_undeclared_is_error(self):
        stage = _stage(
            {
                "alpha": ("/World/Results", "Temperature"),
                "gamma": ("/World/Results", "Vorticity"),
            },
            {"/World/Results": ("Temperature", "Vorticity")},
        )
        manifest = _manifest({"alpha": ("/World/Results", "Temperature")})

        report = _check(manifest, stage)

        self.assertTrue(any("gamma" in error for error in report.errors), report.errors)
        self.assertFalse(any("alpha" in error for error in report.errors), report.errors)

    async def test_manifest_output_without_stage_instance_warns(self):
        stage = _stage(
            {"alpha": ("/World/Results", "Temperature")},
            {"/World/Results": ("Temperature", "Density")},
        )
        manifest = _manifest(
            {
                "alpha": ("/World/Results", "Temperature"),
                "delta": ("/World/Results", "Density"),
            }
        )

        report = _check(manifest, stage)

        self.assertEqual(report.errors, [], f"unexpected errors: {report.errors}")
        self.assertTrue(any("delta" in warning for warning in report.warnings), report.warnings)

    async def test_missing_target_prim_is_error(self):
        stage = _stage(
            {"alpha": ("/World/Missing", "Temperature")},
            {},
        )
        manifest = _manifest({"alpha": ("/World/Missing", "Temperature")})

        report = _check(manifest, stage)

        self.assertTrue(
            any("alpha" in error and "does not exist" in error for error in report.errors),
            report.errors,
        )

    async def test_target_must_be_marked_omnisci_result_dataset(self):
        stage = Usd.Stage.CreateInMemory()
        inference_prim = stage.DefinePrim(_INFERENCE_PRIM, "Scope")
        _author_selection(inference_prim, "alpha", "/World/Results", "Temperature")
        dataset = _define_result_dataset(
            stage,
            "/World/Results",
            ("Temperature",),
            marker=False,
        )
        self.assertTrue(dataset.IsA(OmniSci.Dataset))

        report = _check(
            _manifest({"alpha": ("/World/Results", "Temperature")}),
            stage,
        )

        self.assertTrue(
            any(_RESULTS_API in error for error in report.errors),
            report.errors,
        )

    async def test_target_must_be_omnisci_dataset(self):
        stage = Usd.Stage.CreateInMemory()
        inference_prim = stage.DefinePrim(_INFERENCE_PRIM, "Scope")
        _author_selection(inference_prim, "alpha", "/World/Results", "Temperature")
        stage.DefinePrim("/World/Results", "Scope").AddAppliedSchema(_RESULTS_API)

        report = _check(
            _manifest({"alpha": ("/World/Results", "Temperature")}),
            stage,
        )

        self.assertTrue(
            any("must be an OmniSciDataset" in error for error in report.errors),
            report.errors,
        )

    async def test_target_requires_composed_image_data_grid_contract(self):
        stage = Usd.Stage.CreateInMemory()
        inference_prim = stage.DefinePrim(_INFERENCE_PRIM, "Scope")
        _author_selection(
            inference_prim,
            "alpha",
            "/World/Results",
            "Temperature",
        )
        _define_result_dataset(
            stage,
            "/World/Results",
            ("Temperature",),
            grid_contract=False,
        )

        report = _check(
            _manifest({"alpha": ("/World/Results", "Temperature")}),
            stage,
        )

        self.assertTrue(
            any(
                "OmniSciVtkImageDataAPI grid contract" in error
                for error in report.errors
            ),
            report.errors,
        )

    async def test_field_name_is_required(self):
        stage = _stage(
            {"alpha": ("/World/Results", "")},
            {"/World/Results": ("Temperature",)},
        )

        report = _check(
            _manifest({"alpha": ("/World/Results", "")}),
            stage,
        )

        self.assertTrue(any("field_name is required" in error for error in report.errors))

    async def test_field_requires_paired_field_and_array_apis(self):
        cases = (
            (frozenset({"Temperature"}), frozenset(), "OmniSciArrayAPI:Temperature"),
            (frozenset(), frozenset({"Temperature"}), "OmniSciFieldAPI:Temperature"),
        )
        for omit_array, omit_field, expected in cases:
            with self.subTest(expected=expected):
                stage = Usd.Stage.CreateInMemory()
                inference_prim = stage.DefinePrim(_INFERENCE_PRIM, "Scope")
                _author_selection(inference_prim, "alpha", "/World/Results", "Temperature")
                _define_result_dataset(
                    stage,
                    "/World/Results",
                    ("Temperature",),
                    omit_array=omit_array,
                    omit_field=omit_field,
                )

                report = _check(
                    _manifest({"alpha": ("/World/Results", "Temperature")}),
                    stage,
                )

                self.assertTrue(any(expected in error for error in report.errors), report.errors)

    async def test_stage_target_and_field_name_drift_are_errors(self):
        stage = _stage(
            {"alpha": ("/World/OtherResults", "Pressure")},
            {
                "/World/Results": ("Temperature",),
                "/World/OtherResults": ("Pressure",),
            },
        )
        manifest = _manifest({"alpha": ("/World/Results", "Temperature")})

        report = _check(manifest, stage)

        self.assertTrue(any("stage target" in error for error in report.errors), report.errors)
        self.assertTrue(any("stage fieldName" in error for error in report.errors), report.errors)

    async def test_drift_surfaces_through_validate_workflow(self):
        stage = _stage(
            {
                "alpha": ("/World/Results", "Temperature"),
                "gamma": ("/World/Results", "Vorticity"),
            },
            {"/World/Results": ("Temperature", "Vorticity")},
        )
        manifest = _manifest({"alpha": ("/World/Results", "Temperature")})

        report = validator.validate_workflow(manifest, [], stage)

        self.assertFalse(report.ok)
        self.assertTrue(any("gamma" in error for error in report.errors), report.errors)
