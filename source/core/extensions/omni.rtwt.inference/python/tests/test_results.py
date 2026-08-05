# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Contract tests for the native Kit-CAE 3 RTWT inference-result bridge."""

from __future__ import annotations

import inspect
from unittest import mock

import numpy as np
import omni.kit.commands
import omni.kit.test
import warp as wp
import warp_simdata as simdata
from omni.cae.core import usd_utils
from omni.cae.simdata import GetAvailableFields, GetField
from pxr import Gf, OmniSci, OmniSciVtk, Sdf, Usd

from omni.rtwt.inference import inference, results

_ORIGIN = (2, 3, 4)
_DIMENSIONS = (2, 2, 1)


def _define_dataset(
    fields: dict[str, tuple[str, str]],
    *,
    origin: tuple[int, int, int] = _ORIGIN,
    dimensions: tuple[int, int, int] = _DIMENSIONS,
) -> tuple[Usd.Stage, Usd.Prim]:
    """Create a complete cache-backed native OmniSci inference-result dataset."""
    stage = Usd.Stage.CreateInMemory()
    dataset = OmniSci.Dataset.Define(stage, "/World/InferenceResults").GetPrim()
    dataset.AddAppliedSchema(results._RESULTS_API)
    dataset.CreateAttribute(results._REVISION_ATTR, Sdf.ValueTypeNames.Token).Set("")
    image_data_api = OmniSciVtk.ImageDataAPI.Apply(dataset)
    image_data_api.CreateMinExtentAttr(Gf.Vec3i(*origin))
    maximum = tuple(
        origin[index] + dimensions[index] - 1
        for index in range(3)
    )
    image_data_api.CreateMaxExtentAttr(Gf.Vec3i(*maximum))

    for field_name, (label, association) in fields.items():
        field_api = OmniSci.FieldAPI.Apply(dataset, field_name)
        field_api.CreateNameAttr(label)
        field_api.CreateAssociationAttr(association)
        OmniSci.ArrayAPI.Apply(dataset, field_name)
    return stage, dataset


def _nanovdb_bytes(
    values: np.ndarray,
    *,
    dtype,
    dimensions: tuple[int, int, int] = _DIMENSIONS,
    origin: tuple[int, int, int] = _ORIGIN,
    device: str = "cuda:0",
) -> np.ndarray:
    source = simdata.Field.from_array(
        wp.array(values, dtype=dtype, device=device),
        simdata.AssociationType.NODE,
    )
    nanovdb = source.to_nanovdb(
        dims=wp.vec3i(*dimensions),
        origin=wp.vec3i(*origin),
        device=device,
    )
    return nanovdb.get_data().array().numpy().copy()


class TestInferenceResults(omni.kit.test.AsyncTestCase):
    def setUp(self):
        self.memory_cache: dict[str, object] = {}
        self.cache_events: list[tuple[str, str]] = []

        def get(key, *args, **kwargs):
            del args, kwargs
            return self.memory_cache.get(key)

        def put_ex(key, value, *args, **kwargs):
            del args, kwargs
            self.cache_events.append(("put", key))
            self.memory_cache[key] = value

        def remove(key, *args, **kwargs):
            del args, kwargs
            self.cache_events.append(("remove", key))
            return self.memory_cache.pop(key, None) is not None

        for name, replacement in (
            ("get", get),
            ("put_ex", put_ex),
            ("remove", remove),
        ):
            patcher = mock.patch.object(results.cache, name, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_result_api_dispatch_names_are_registered(self):
        self.assertIs(
            omni.kit.commands.get_command_class(
                "RtwtInferenceResultsGetAvailableFields"
            ),
            results.RtwtInferenceResultsGetAvailableFields,
        )
        self.assertIs(
            omni.kit.commands.get_command_class("RtwtInferenceResultsGetField"),
            results.RtwtInferenceResultsGetField,
        )

        # Conversion remains owned by Kit-CAE's native OmniSci adapter. Defining
        # an RTWT conversion command here would shadow that complete dataset path.
        self.assertIsNone(
            omni.kit.commands.get_command_class(
                "RtwtInferenceResultsConvertToSimDataSet"
            )
        )
        self.assertIsNotNone(
            omni.kit.commands.get_command_class(
                "OmniSciDatasetConvertToSimDataSet"
            )
        )

    async def test_available_fields_dispatches_from_result_api(self):
        _stage, dataset = _define_dataset(
            {
                "Pressure": ("Static Pressure", "node"),
                "Velocity": ("Velocity", "node"),
            }
        )

        field_infos = await GetAvailableFields.invoke(dataset)
        by_name = {field.name: field for field in field_infos}

        self.assertEqual(set(by_name), {"Pressure", "Velocity"})
        self.assertEqual(by_name["Pressure"].label, "Static Pressure")
        self.assertEqual(
            by_name["Pressure"].association,
            simdata.AssociationType.NODE,
        )
        self.assertEqual(
            by_name["Velocity"].association,
            simdata.AssociationType.NODE,
        )

    async def test_scalar_and_vector_nanovdb_fields_round_trip_through_dispatch(self):
        if wp.get_cuda_device_count() == 0:
            self.skipTest("CUDA is required for NanoVDB tile allocation")

        cases = (
            (
                "Pressure",
                wp.float32,
                np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
            ),
            (
                "Velocity",
                wp.vec3f,
                np.array(
                    [
                        [1.0, 2.0, 3.0],
                        [4.0, 5.0, 6.0],
                        [7.0, 8.0, 9.0],
                        [10.0, 11.0, 12.0],
                    ],
                    dtype=np.float32,
                ),
            ),
        )

        for field_name, dtype, expected in cases:
            with self.subTest(field_name=field_name):
                _stage, dataset = _define_dataset(
                    {field_name: (field_name, "node")}
                )
                raw = _nanovdb_bytes(expected, dtype=dtype)
                results.publish_results(
                    dataset,
                    {field_name: raw},
                    origin=_ORIGIN,
                    dimensions=_DIMENSIONS,
                )

                field = await GetField.invoke(
                    dataset,
                    field_name,
                    device="cuda:0",
                    timeCode=Usd.TimeCode.Default(),
                )

                self.assertIsInstance(field, simdata.Field)
                self.assertIsInstance(field.get_data(), wp.Volume)
                self.assertEqual(field.dtype, dtype)
                self.assertEqual(field.size, 4)
                self.assertEqual(
                    field.association,
                    simdata.AssociationType.NODE,
                )
                np.testing.assert_allclose(field.to_array().numpy(), expected)

    async def test_publish_replaces_revision_atomically_and_merges_other_fields(self):
        _stage, dataset = _define_dataset(
            {
                "Pressure": ("Pressure", "node"),
                "Velocity": ("Velocity", "node"),
            }
        )
        first_pressure = np.array([1, 2, 3, 4], dtype=np.uint8)
        first_revision = results.publish_results(
            dataset,
            {"Pressure": first_pressure},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )
        first_key = results._cache_key(dataset, first_revision)
        first_payload = self.memory_cache[first_key]

        # Publishing owns an immutable copy rather than the producer's array.
        first_pressure[:] = 99
        np.testing.assert_array_equal(
            first_payload["fields"]["Pressure"]["buffer"],
            np.array([1, 2, 3, 4], dtype=np.uint8),
        )
        self.assertFalse(
            first_payload["fields"]["Pressure"]["buffer"].flags.writeable
        )

        velocity = np.array([5, 6, 7], dtype=np.uint8)
        second_revision = results.publish_results(
            dataset,
            {"Velocity": velocity},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )
        second_key = results._cache_key(dataset, second_revision)
        second_payload = self.memory_cache[second_key]

        self.assertNotEqual(first_revision, second_revision)
        self.assertEqual(
            str(dataset.GetAttribute(results._REVISION_ATTR).Get()),
            second_revision,
        )
        self.assertNotIn(first_key, self.memory_cache)
        self.assertEqual(
            set(second_payload["fields"]),
            {"Pressure", "Velocity"},
        )
        np.testing.assert_array_equal(
            second_payload["fields"]["Pressure"]["buffer"],
            np.array([1, 2, 3, 4], dtype=np.uint8),
        )
        np.testing.assert_array_equal(
            second_payload["fields"]["Velocity"]["buffer"],
            velocity,
        )
        self.assertEqual(
            self.cache_events[-2:],
            [("put", second_key), ("remove", first_key)],
        )

        replacement = np.array([8, 9], dtype=np.uint8)
        third_revision = results.publish_results(
            dataset,
            {"Pressure": replacement},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )
        third_payload = self.memory_cache[
            results._cache_key(dataset, third_revision)
        ]
        np.testing.assert_array_equal(
            third_payload["fields"]["Pressure"]["buffer"],
            replacement,
        )
        np.testing.assert_array_equal(
            third_payload["fields"]["Velocity"]["buffer"],
            velocity,
        )

    async def test_partial_publish_drops_fields_from_the_previous_grid(self):
        _stage, dataset = _define_dataset(
            {
                "Pressure": ("Pressure", "node"),
                "Velocity": ("Velocity", "node"),
            }
        )
        first_revision = results.publish_results(
            dataset,
            {
                "Pressure": np.array([1, 2], dtype=np.uint8),
                "Velocity": np.array([3, 4], dtype=np.uint8),
            },
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )

        new_origin = (10, 20, 30)
        new_dimensions = (1, 2, 2)
        maximum = tuple(
            new_origin[index] + new_dimensions[index] - 1
            for index in range(3)
        )
        image_data_api = OmniSciVtk.ImageDataAPI(dataset)
        image_data_api.GetMinExtentAttr().Set(Gf.Vec3i(*new_origin))
        image_data_api.GetMaxExtentAttr().Set(Gf.Vec3i(*maximum))

        second_revision = results.publish_results(
            dataset,
            {"Pressure": np.array([5, 6], dtype=np.uint8)},
            origin=new_origin,
            dimensions=new_dimensions,
        )
        second_payload = self.memory_cache[
            results._cache_key(dataset, second_revision)
        ]

        self.assertNotEqual(first_revision, second_revision)
        self.assertEqual(set(second_payload["fields"]), {"Pressure"})
        self.assertEqual(
            second_payload["fields"]["Pressure"]["origin"],
            new_origin,
        )
        self.assertEqual(
            second_payload["fields"]["Pressure"]["dimensions"],
            new_dimensions,
        )

        third_revision = results.publish_results(
            dataset,
            {"Velocity": np.array([7, 8], dtype=np.uint8)},
            origin=new_origin,
            dimensions=new_dimensions,
        )
        third_payload = self.memory_cache[
            results._cache_key(dataset, third_revision)
        ]
        self.assertEqual(
            set(third_payload["fields"]),
            {"Pressure", "Velocity"},
        )

    async def test_read_rejects_a_cached_field_after_the_composed_grid_changes(self):
        _stage, dataset = _define_dataset(
            {"Pressure": ("Pressure", "node")}
        )
        results.publish_results(
            dataset,
            {"Pressure": np.array([1, 2], dtype=np.uint8)},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )

        image_data_api = OmniSciVtk.ImageDataAPI(dataset)
        changed_maximum = (
            _ORIGIN[0] + _DIMENSIONS[0],
            _ORIGIN[1] + _DIMENSIONS[1] - 1,
            _ORIGIN[2] + _DIMENSIONS[2] - 1,
        )
        image_data_api.GetMaxExtentAttr().Set(Gf.Vec3i(*changed_maximum))

        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "does not match the current composed grid",
        ):
            await results.RtwtInferenceResultsGetField(
                dataset=dataset,
                field_names=["Pressure"],
                device="cpu",
                timeCode=Usd.TimeCode.Default(),
            ).do()

    async def test_publish_does_not_merge_an_unknown_cache_payload_version(self):
        _stage, dataset = _define_dataset(
            {
                "Pressure": ("Pressure", "node"),
                "Velocity": ("Velocity", "node"),
            }
        )
        first_revision = results.publish_results(
            dataset,
            {"Pressure": np.array([1], dtype=np.uint8)},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )
        first_key = results._cache_key(dataset, first_revision)
        self.memory_cache[first_key] = {
            "version": 999,
            "fields": {
                "Velocity": {
                    "buffer": np.array([2], dtype=np.uint8),
                    "origin": _ORIGIN,
                    "dimensions": _DIMENSIONS,
                }
            },
        }

        second_revision = results.publish_results(
            dataset,
            {"Pressure": np.array([3], dtype=np.uint8)},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )
        second_payload = self.memory_cache[
            results._cache_key(dataset, second_revision)
        ]

        self.assertEqual(set(second_payload["fields"]), {"Pressure"})

    async def test_missing_stale_and_incomplete_revisions_are_quietable(self):
        _stage, dataset = _define_dataset({"Pressure": ("Pressure", "node")})

        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "not available yet",
        ):
            await results.RtwtInferenceResultsGetField(
                dataset=dataset,
                field_names=["Pressure"],
                device="cpu",
                timeCode=Usd.TimeCode.Default(),
            ).do()

        dataset.GetAttribute(results._REVISION_ATTR).Set("stale")
        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "no longer available",
        ):
            await results.RtwtInferenceResultsGetField(
                dataset=dataset,
                field_names=["Pressure"],
                device="cpu",
                timeCode=Usd.TimeCode.Default(),
            ).do()

        revision = "incomplete"
        dataset.GetAttribute(results._REVISION_ATTR).Set(revision)
        self.memory_cache[results._cache_key(dataset, revision)] = {
            "version": 1,
            "fields": {},
        }
        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "field 'Pressure' is not available",
        ):
            await results.RtwtInferenceResultsGetField(
                dataset=dataset,
                field_names=["Pressure"],
                device="cpu",
                timeCode=Usd.TimeCode.Default(),
            ).do()

    async def test_get_field_rejects_multi_field_selection(self):
        _stage, dataset = _define_dataset(
            {
                "Pressure": ("Pressure", "node"),
                "Temperature": ("Temperature", "node"),
            }
        )

        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "exactly one field name",
        ):
            await results.RtwtInferenceResultsGetField(
                dataset=dataset,
                field_names=["Pressure", "Temperature"],
                device="cpu",
                timeCode=Usd.TimeCode.Default(),
            ).do()

    async def test_node_association_is_enforced_at_publish_and_read(self):
        _stage, element_dataset = _define_dataset(
            {"Pressure": ("Pressure", "element")}
        )
        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "support only node-associated fields.*Pressure",
        ):
            await results.RtwtInferenceResultsGetAvailableFields(
                dataset=element_dataset,
            ).do()

        with self.assertRaisesRegex(ValueError, "must use association 'node'"):
            results.publish_results(
                element_dataset,
                {"Pressure": np.array([1], dtype=np.uint8)},
                origin=_ORIGIN,
                dimensions=_DIMENSIONS,
            )

        _stage, node_dataset = _define_dataset(
            {"Pressure": ("Pressure", "node")}
        )
        results.publish_results(
            node_dataset,
            {"Pressure": np.array([1], dtype=np.uint8)},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )
        OmniSci.FieldAPI(
            node_dataset,
            "Pressure",
        ).GetAssociationAttr().Set("element")

        with self.assertRaisesRegex(
            usd_utils.QuietableException,
            "must use association 'node'",
        ):
            await results.RtwtInferenceResultsGetField(
                dataset=node_dataset,
                field_names=["Pressure"],
                device="cpu",
                timeCode=Usd.TimeCode.Default(),
            ).do()

    async def test_nanovdb_construction_is_offloaded_and_errors_are_quietable(self):
        _stage, dataset = _define_dataset({"Pressure": ("Pressure", "node")})
        results.publish_results(
            dataset,
            {"Pressure": np.array([1], dtype=np.uint8)},
            origin=_ORIGIN,
            dimensions=_DIMENSIONS,
        )

        with mock.patch.object(
            results.asyncio,
            "to_thread",
            new_callable=mock.AsyncMock,
            side_effect=RuntimeError("invalid NanoVDB header"),
        ) as to_thread:
            with self.assertRaisesRegex(
                usd_utils.QuietableException,
                "Could not construct RTWT NanoVDB field 'Pressure'.*invalid NanoVDB header",
            ):
                await results.RtwtInferenceResultsGetField(
                    dataset=dataset,
                    field_names=["Pressure"],
                    device="cpu",
                    timeCode=Usd.TimeCode.Default(),
                ).do()

        to_thread.assert_awaited_once()
        self.assertIs(to_thread.await_args.args[0], results._field_from_payload)

    async def test_publish_rejects_incomplete_native_dataset_contracts(self):
        _stage, dataset = _define_dataset({"Pressure": ("Pressure", "node")})

        with self.assertRaisesRegex(ValueError, "At least one"):
            results.publish_results(
                dataset,
                {},
                origin=_ORIGIN,
                dimensions=_DIMENSIONS,
            )

        with self.assertRaisesRegex(ValueError, "does not match"):
            results.publish_results(
                dataset,
                {"Pressure": np.array([1], dtype=np.uint8)},
                origin=_ORIGIN,
                dimensions=(9, 9, 9),
            )

        with self.assertRaisesRegex(ValueError, "OmniSciFieldAPI:Missing"):
            results.publish_results(
                dataset,
                {"Missing": np.array([1], dtype=np.uint8)},
                origin=_ORIGIN,
                dimensions=_DIMENSIONS,
            )

        no_grid_stage = Usd.Stage.CreateInMemory()
        no_grid = OmniSci.Dataset.Define(
            no_grid_stage,
            "/NoGrid",
        ).GetPrim()
        no_grid.AddAppliedSchema(results._RESULTS_API)
        no_grid.CreateAttribute(
            results._REVISION_ATTR,
            Sdf.ValueTypeNames.Token,
        ).Set("")
        field_api = OmniSci.FieldAPI.Apply(no_grid, "Pressure")
        field_api.CreateNameAttr("Pressure")
        field_api.CreateAssociationAttr("node")
        OmniSci.ArrayAPI.Apply(no_grid, "Pressure")
        with self.assertRaisesRegex(ValueError, "OmniSciVtkImageDataAPI"):
            results.publish_results(
                no_grid,
                {"Pressure": np.array([1], dtype=np.uint8)},
                origin=_ORIGIN,
                dimensions=_DIMENSIONS,
            )

        unmarked_stage = Usd.Stage.CreateInMemory()
        unmarked = OmniSci.Dataset.Define(unmarked_stage, "/Unmarked").GetPrim()
        with self.assertRaisesRegex(ValueError, results._RESULTS_API):
            results.publish_results(
                unmarked,
                {"Pressure": np.array([1], dtype=np.uint8)},
                origin=_ORIGIN,
                dimensions=_DIMENSIONS,
            )

    async def test_active_inference_path_contains_no_kit_cae_legacy_contracts(self):
        source = "\n".join(
            (
                inspect.getsource(results),
                inspect.getsource(inference),
            )
        )
        forbidden = (
            "CaeDataSet",  # negative assertion
            "NanoVDBFieldArrayAPI",
            "omni.cae.data",  # negative assertion
            "omni.cae.delegate",  # negative assertion
            "from dav",  # negative assertion
            "import dav",  # negative assertion
        )
        for symbol in forbidden:
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, source)
