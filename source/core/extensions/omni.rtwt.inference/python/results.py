# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Warp SimData bridge for cache-backed RTWT NanoVDB inference results."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import warp as wp
import warp_simdata as simdata
from omni.cae.core import cache, usd_utils
from omni.cae.simdata import FieldInfo, GetAvailableFields, GetField, get_prim_fields
from pxr import OmniSci, OmniSciVtk, Usd, UsdUtils

_RESULTS_API = "RtwtInferenceResultsAPI"
_REVISION_ATTR = "omni:rtwt:inference_results:revision"
_CACHE_PREFIX = "omni.rtwt.inference:results"


def _stage_identity(stage: Usd.Stage) -> int:
    """Return a stable process-local identity for a stage."""
    stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
    return stage_id if stage_id else id(stage)


def _cache_key(dataset: Usd.Prim, revision: str) -> str:
    return f"{_CACHE_PREFIX}:{_stage_identity(dataset.GetStage())}:{dataset.GetPath()}:{revision}"


def _as_int3(value: Sequence[int], *, label: str) -> tuple[int, int, int]:
    values = tuple(int(component) for component in value)
    if len(values) != 3:
        raise ValueError(f"{label} must contain exactly three components; got {values}")
    return values


def _validate_dataset(dataset: Usd.Prim, field_names: Sequence[str]) -> None:
    if not dataset or not dataset.IsValid():
        raise ValueError("Inference result target is not a valid USD prim")
    if not dataset.IsA(OmniSci.Dataset):
        raise ValueError(f"Inference result target {dataset.GetPath()} must be an OmniSciDataset")
    if _RESULTS_API not in dataset.GetAppliedSchemas():
        raise ValueError(f"Inference result target {dataset.GetPath()} must apply {_RESULTS_API}")
    if not dataset.HasAPI(OmniSciVtk.ImageDataAPI):
        raise ValueError(
            f"Inference result target {dataset.GetPath()} must provide a composed "
            "OmniSciVtkImageDataAPI grid contract"
        )

    for field_name in field_names:
        if not dataset.HasAPI(OmniSci.FieldAPI, field_name):
            raise ValueError(
                f"Inference result field '{field_name}' is not declared with "
                f"OmniSciFieldAPI:{field_name} on {dataset.GetPath()}"
            )
        if not dataset.HasAPI(OmniSci.ArrayAPI, field_name):
            raise ValueError(
                f"Inference result field '{field_name}' is not declared with "
                f"OmniSciArrayAPI:{field_name} on {dataset.GetPath()}"
            )
        association = str(
            OmniSci.FieldAPI(dataset, field_name).GetAssociationAttr().Get() or "none"
        )
        if association != "node":
            raise ValueError(
                f"Inference result field '{field_name}' on {dataset.GetPath()} must use "
                f"association 'node'; got '{association}'"
            )


def _validate_grid(dataset: Usd.Prim, origin: tuple[int, int, int], dimensions: tuple[int, int, int]) -> None:
    if any(dimension <= 0 for dimension in dimensions):
        raise ValueError(f"Inference result dimensions must be positive; got {dimensions}")

    image_data_api = OmniSciVtk.ImageDataAPI(dataset)
    min_extent = image_data_api.GetMinExtentAttr().Get()
    max_extent = image_data_api.GetMaxExtentAttr().Get()
    if min_extent is None or max_extent is None:
        raise ValueError(
            f"Inference result dataset {dataset.GetPath()} must provide omni:vtk:minExtent and "
            "omni:vtk:maxExtent through OmniSciVtkImageDataAPI"
        )

    expected_origin = tuple(int(component) for component in min_extent)
    expected_dimensions = tuple(int(max_extent[i] - min_extent[i] + 1) for i in range(3))
    if origin != expected_origin or dimensions != expected_dimensions:
        raise ValueError(
            f"Inference result grid {origin=} {dimensions=} does not match {dataset.GetPath()} "
            f"grid origin={expected_origin} dimensions={expected_dimensions}"
        )


def _payload_matches_grid(
    field_payload: Any,
    origin: tuple[int, int, int],
    dimensions: tuple[int, int, int],
) -> bool:
    """Return whether a cached field belongs to the grid being published."""
    if not isinstance(field_payload, Mapping):
        return False
    try:
        cached_origin = _as_int3(field_payload["origin"], label="cached origin")
        cached_dimensions = _as_int3(
            field_payload["dimensions"],
            label="cached dimensions",
        )
    except (KeyError, TypeError, ValueError):
        return False
    return cached_origin == origin and cached_dimensions == dimensions


def publish_results(
    dataset: Usd.Prim,
    fields: Mapping[str, np.ndarray],
    *,
    origin: Sequence[int],
    dimensions: Sequence[int],
) -> str:
    """Atomically publish one or more NanoVDB fields on an RTWT result dataset.

    Existing fields not present in ``fields`` are retained only when they belong to
    the same grid. This permits the live inference operator and the static comparison
    operator to publish disjoint field sets without retaining stale fields after a
    grid variant changes or exposing a mixed, partially updated revision.

    Returns the new revision token.
    """
    if not fields:
        raise ValueError("At least one inference result field is required")

    field_names = tuple(fields)
    _validate_dataset(dataset, field_names)
    origin3 = _as_int3(origin, label="origin")
    dimensions3 = _as_int3(dimensions, label="dimensions")
    _validate_grid(dataset, origin3, dimensions3)

    revision_attr = dataset.GetAttribute(_REVISION_ATTR)
    if not revision_attr:
        raise ValueError(f"{dataset.GetPath()} does not provide {_REVISION_ATTR}")

    old_revision = str(revision_attr.Get() or "")
    old_key = _cache_key(dataset, old_revision) if old_revision else ""
    old_payload = cache.get(old_key) if old_key else None
    merged_fields: dict[str, dict[str, Any]] = {}
    if isinstance(old_payload, dict) and old_payload.get("version") == 1:
        old_fields = old_payload.get("fields")
        if isinstance(old_fields, Mapping):
            merged_fields.update(
                {
                    field_name: field_payload
                    for field_name, field_payload in old_fields.items()
                    if _payload_matches_grid(field_payload, origin3, dimensions3)
                }
            )

    for field_name, array in fields.items():
        raw = np.ascontiguousarray(array).view(np.uint8).reshape(-1).copy()
        raw.flags.writeable = False
        merged_fields[field_name] = {
            "buffer": raw,
            "origin": origin3,
            "dimensions": dimensions3,
        }

    new_revision = uuid.uuid4().hex
    new_key = _cache_key(dataset, new_revision)
    payload = {"version": 1, "fields": merged_fields}
    cache.put_ex(
        new_key,
        payload,
        prims=[cache.PrimWatch(dataset, on="delete")],
        force=True,
    )

    if not revision_attr.Set(new_revision):
        cache.remove(new_key)
        raise RuntimeError(f"Could not publish inference result revision on {dataset.GetPath()}")

    if old_key:
        cache.remove(old_key)
    return new_revision


def _field_payload(dataset: Usd.Prim, field_name: str) -> dict[str, Any]:
    revision = str(dataset.GetAttribute(_REVISION_ATTR).Get() or "")
    if not revision:
        raise usd_utils.QuietableException(
            f"Inference results are not available yet on {dataset.GetPath()}"
        )

    payload = cache.get(_cache_key(dataset, revision))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise usd_utils.QuietableException(
            f"Inference result revision '{revision}' is no longer available for {dataset.GetPath()}"
        )

    fields = payload.get("fields")
    field_payload = fields.get(field_name) if isinstance(fields, Mapping) else None
    if not isinstance(field_payload, dict):
        raise usd_utils.QuietableException(
            f"Inference field '{field_name}' is not available in revision '{revision}' "
            f"for {dataset.GetPath()}"
        )

    try:
        cached_origin = _as_int3(
            field_payload["origin"],
            label="cached origin",
        )
        cached_dimensions = _as_int3(
            field_payload["dimensions"],
            label="cached dimensions",
        )
        _validate_grid(dataset, cached_origin, cached_dimensions)
    except (KeyError, TypeError, ValueError) as exc:
        raise usd_utils.QuietableException(
            f"Inference field '{field_name}' in revision '{revision}' does not match "
            f"the current composed grid on {dataset.GetPath()}: {exc}"
        ) from exc

    return field_payload


def _field_from_payload(
    field_payload: Mapping[str, Any],
    *,
    device: str,
) -> simdata.Field:
    """Construct a Warp SimData field from one immutable cached NanoVDB payload."""
    raw = field_payload["buffer"]
    wp_raw = wp.array(raw, dtype=wp.uint8, device=device)
    volume = wp.Volume(wp_raw)
    return simdata.Field.from_volume(
        volume,
        dims=wp.vec3i(*field_payload["dimensions"]),
        association=simdata.AssociationType.NODE,
        origin=wp.vec3i(*field_payload["origin"]),
    )


class RtwtInferenceResultsGetAvailableFields(GetAvailableFields):
    """Enumerate OmniSci field metadata on an RTWT inference result dataset."""

    async def do(self) -> list[FieldInfo]:
        field_infos = get_prim_fields(self.dataset)
        unsupported = [
            field.name
            for field in field_infos
            if field.association != simdata.AssociationType.NODE
        ]
        if unsupported:
            raise usd_utils.QuietableException(
                f"RTWT NanoVDB results on {self.dataset.GetPath()} support only "
                f"node-associated fields; unsupported fields: {', '.join(unsupported)}"
            )
        return field_infos


class RtwtInferenceResultsGetField(GetField):
    """Expose a cached NanoVDB buffer as an active Warp SimData field."""

    async def do(self) -> simdata.Field:
        if len(self.field_names) != 1:
            raise usd_utils.QuietableException(
                "RTWT NanoVDB results require exactly one field name per selection; "
                f"got {self.field_names}"
            )

        field_name = self.field_names[0]
        field_payload = _field_payload(self.dataset, field_name)

        field_api = OmniSci.FieldAPI(self.dataset, field_name)
        association = str(field_api.GetAssociationAttr().Get(self.timeCode) or "none")
        if association != "node":
            raise usd_utils.QuietableException(
                f"RTWT NanoVDB field '{field_name}' on {self.dataset.GetPath()} must use "
                f"association 'node'; got '{association}'"
            )

        try:
            return await asyncio.to_thread(
                _field_from_payload,
                field_payload,
                device=self.device,
            )
        except Exception as exc:
            raise usd_utils.QuietableException(
                f"Could not construct RTWT NanoVDB field '{field_name}' for "
                f"{self.dataset.GetPath()}: {exc}"
            ) from exc
