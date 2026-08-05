# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""One-time bake of a cached **comparison view** from an existing surrogate cache entry.

Given one surrogate ``.npz`` (flat NanoVDB *grid* buffers + IJK extents, as produced by
``omni.rtwt.inference``'s offline cache), this produces two derived cache entries using the same
NPZ/NanoVDB grid-buffer and extent convention, so the native Warp SimData result bridge and Kit-CAE
visualization can consume both directly:

* ``mock_ground_truth.npz`` — every field, perturbed by an injected ``perturb_fn``.
* ``diff.npz``              — only the requested signed ``GT - surrogate`` fields plus extents.

This module is **use-case-agnostic** (no aero vocabulary): the spatial perturbation policy is supplied
by the caller via ``perturb_fn`` (the specialization owns the policy; see the auto-aero bake runner).

It is a **maintainer/bake tool**, not a runtime path — it needs Warp SimData (e.g. the AeroNIM
container), and only runs once to generate the shipped comparison cache. The runtime treats the
results as ordinary cached fields (no new diff kernel).

NanoVDB round-trip notes (verified against Warp SimData):
* The npz members are **raw grid buffers** -> reconstruct with the ``wp.Volume(bytes)`` ctor, NOT
  ``wp.Volume.load_from_nvdb`` (which parses a ``.nvdb`` *file* header).
* Values map to ijk in **ij / Fortran order** (i fastest); ``decode`` returns a flat array aligned with
  :func:`voxel_coords`, so a spatially-varying ``perturb_fn`` can use the per-voxel coordinates directly.
* Re-encode reuses ``warp_simdata.Field.from_array(...).to_nanovdb(...)`` with the source
  dims/origin/voxel_size, giving a byte-compatible buffer the native result bridge reads identically.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import warp as wp
import warp_simdata as simdata

# perturb_fn(field_name, dense_values, world_coords, ijk) -> perturbed dense_values.
#   dense_values : (N,) float32 (scalar) or (N, 3) float32 (vector), ij (Fortran) order.
#   world_coords : (N, 3) float32 world XYZ, aligned element-for-element with dense_values.
#   ijk          : (N, 3) int32 voxel indices (incl. origin), aligned likewise.
PerturbFn = Callable[[str, np.ndarray, np.ndarray, np.ndarray], np.ndarray]

VELOCITY_FIELD = "nvdb_velocity"
VELOCITY_MAGNITUDE_FIELD = "nvdb_velocity_magnitude"
PRESSURE_FIELD = "nvdb_pressure"


def _bg(vector: bool):
    return wp.vec3f(0.0, 0.0, 0.0) if vector else wp.float32(0.0)


def decode(buf_u8: np.ndarray, dims, origin, *, vector: bool, device: str = "cuda") -> np.ndarray:
    """Decode a raw NanoVDB grid buffer (one npz member) to dense float values in ij (Fortran) order.

    Returns ``(N,)`` for a scalar grid or ``(N, 3)`` for a vec3f grid, where ``N = Ni*Nj*Nk``.
    Reshape spatially with ``arr.reshape(Ni, Nj, Nk[, 3], order="F")``.
    """
    Ni, Nj, Nk = (int(d) for d in dims)
    wp_bytes = wp.array(np.ascontiguousarray(buf_u8, dtype=np.uint8), dtype=wp.uint8, device=device)
    volume = wp.Volume(wp_bytes)  # raw-grid ctor (NOT load_from_nvdb, which is for .nvdb files)
    field = simdata.Field.from_volume(
        volume,
        dims=wp.vec3i(Ni, Nj, Nk),
        association=simdata.AssociationType.NODE,
        origin=wp.vec3i(int(origin[0]), int(origin[1]), int(origin[2])),
    )
    arr = field.to_array().numpy()  # copy kernel -> AoS, ij order
    return arr.reshape(-1, 3) if vector else arr.reshape(-1)


def encode(dense: np.ndarray, dims, origin, spacing, *, vector: bool, device: str = "cuda") -> np.ndarray:
    """Inverse of :func:`decode`. Returns a flat uint8 raw-grid buffer (npz-ready)."""
    dense = np.ascontiguousarray(dense)
    if vector:
        wp_arr = wp.array(dense.reshape(-1, 3).astype(np.float32, copy=False), dtype=wp.vec3f, device=device)
    else:
        wp_arr = wp.array(dense.reshape(-1).astype(np.float32, copy=False), dtype=wp.float32, device=device)
    field = simdata.Field.from_array(wp_arr, simdata.AssociationType.NODE)
    nvdb = field.to_nanovdb(
        dims=wp.vec3i(int(dims[0]), int(dims[1]), int(dims[2])),
        origin=wp.vec3i(int(origin[0]), int(origin[1]), int(origin[2])),
        voxel_size=wp.vec3f(float(spacing[0]), float(spacing[1]), float(spacing[2])),
        bg_value=_bg(vector),
        device=device,
    )
    return nvdb.get_data().array().numpy()


def voxel_coords(dims, origin, spacing, world_origin=(0.0, 0.0, 0.0)):
    """Per-voxel ``(ijk, world_xyz)`` in ij (Fortran) order, aligned with :func:`decode` output."""
    Ni, Nj, Nk = (int(d) for d in dims)
    gi, gj, gk = np.indices((Ni, Nj, Nk))
    ijk = np.stack([gi + int(origin[0]), gj + int(origin[1]), gk + int(origin[2])], axis=-1)
    ijk_flat = ijk.reshape(-1, 3, order="F").astype(np.int32)  # ij/Fortran flatten matches decode
    world = (np.asarray(world_origin, np.float32)
             + ijk_flat.astype(np.float32) * np.asarray(spacing, np.float32))
    return ijk_flat, world


def _write_set(path: Path, members: dict, *, kind: str, outputs: list, source: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        np.savez(f, **members)
    tmp.replace(path)
    # Sidecar mirrors inference.py:_sidecar_payload keys (requested_outputs/created) plus a
    # comparison marker; we deliberately omit `app_state` so scan_offline_cache_options() ignores it.
    path.with_suffix(".json").write_text(json.dumps({
        "comparison_kind": kind,
        "source_surrogate": source,
        "requested_outputs": sorted(outputs),
        "created": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def bake_comparison(
    surrogate_npz_path: str | Path,
    perturb_fn: PerturbFn,
    out_dir: str | Path,
    *,
    fields_vector: tuple[str, ...] = (VELOCITY_FIELD,),
    fields_scalar: tuple[str, ...] = (VELOCITY_MAGNITUDE_FIELD, PRESSURE_FIELD),
    diff_fields: tuple[str, ...] = (VELOCITY_MAGNITUDE_FIELD, PRESSURE_FIELD),
    spacing: tuple[float, float, float] = (0.036, 0.036, 0.036),
    world_origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    device: str = "cuda",
    validate_roundtrip: bool = True,
) -> dict:
    """Bake ``mock_ground_truth.npz`` + ``diff.npz`` from one surrogate cache entry.

    ``spacing`` only affects the world coords handed to ``perturb_fn`` and the re-encoded voxel_size;
    it does not change the IJK grid. Returns a report dict (per-field value ranges + diff peak%/RMS%).
    """
    surrogate_npz_path = Path(surrogate_npz_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with np.load(surrogate_npz_path) as npz:
        extent_min = npz["EXTENT_MIN"].astype(np.int32).ravel()
        extent_max = npz["EXTENT_MAX"].astype(np.int32).ravel()
        members = {k: npz[k] for k in npz.files}

    dims = (extent_max - extent_min + 1)
    origin = extent_min
    ijk, world = voxel_coords(dims, origin, spacing, world_origin)
    all_fields = tuple(fields_vector) + tuple(fields_scalar)

    # 1. Decode every present field to dense floats (the surrogate).
    surrogate_dense: dict[str, np.ndarray] = {}
    for name in all_fields:
        if name in members:
            surrogate_dense[name] = decode(members[name], dims, origin,
                                           vector=name in fields_vector, device=device)

    # Optional: prove the decode->encode round-trip is lossless before perturbing.
    if validate_roundtrip:
        for name, v in surrogate_dense.items():
            is_vec = name in fields_vector
            rt = decode(encode(v, dims, origin, spacing, vector=is_vec, device=device),
                        dims, origin, vector=is_vec, device=device)
            if not np.allclose(v, rt, atol=1e-4, rtol=1e-3):
                raise RuntimeError(f"nvdb round-trip mismatch for {name!r} "
                                   f"(max abs diff {np.abs(v - rt).max():.3e})")

    # 2. Inject the (use-case-specific) perturbation -> mock ground-truth dense fields.
    gt_dense: dict[str, np.ndarray] = {
        name: np.ascontiguousarray(perturb_fn(name, dense.copy(), world, ijk), dtype=np.float32)
        for name, dense in surrogate_dense.items()
    }
    # Keep speed magnitude consistent with the perturbed velocity vector.
    if VELOCITY_FIELD in gt_dense and VELOCITY_MAGNITUDE_FIELD in surrogate_dense:
        gt_dense[VELOCITY_MAGNITUDE_FIELD] = np.linalg.norm(gt_dense[VELOCITY_FIELD], axis=1).astype(np.float32)

    # 3. Encode the mock ground-truth (all fields).
    gt_members: dict[str, np.ndarray] = {
        name: encode(dense, dims, origin, spacing, vector=name in fields_vector, device=device)
        for name, dense in gt_dense.items()
    }
    gt_members["EXTENT_MIN"] = extent_min
    gt_members["EXTENT_MAX"] = extent_max

    # 4. Signed diff = GT - surrogate for the (scalar) diff fields.
    diff_members: dict[str, np.ndarray] = {}
    report: dict[str, dict] = {}
    for name in diff_fields:
        if name not in surrogate_dense or name not in gt_dense:
            continue
        d = (gt_dense[name] - surrogate_dense[name]).astype(np.float32)
        diff_members[name] = encode(d, dims, origin, spacing, vector=False, device=device)
        s = surrogate_dense[name]
        abss, absd = np.abs(s), np.abs(d)
        rng = float(s.max() - s.min()) or 1.0
        # Robust scale: 99th pct of |field| over non-zero voxels (the field has sparse outlier voxels
        # that inflate the raw range, so % "of range" understates a visually meaningful diff).
        field_p99 = float(np.percentile(abss[abss > 0], 99)) if np.any(abss > 0) else 0.0
        diff_p99 = float(np.percentile(absd, 99))
        report[name] = {
            "value_range": [float(s.min()), float(s.max())],
            "field_abs_p99": field_p99,          # robust field scale (p99 of |field| over non-zero voxels)
            "diff_max": float(absd.max()),
            "diff_p99": diff_p99,
            "diff_rms": float(np.sqrt(np.mean(d.astype(np.float64) ** 2))),
            "diff_peak_pct_of_range": float(absd.max() / rng * 100.0),
            "diff_p99_pct_of_field_p99": float(diff_p99 / field_p99 * 100.0) if field_p99 else 0.0,
            "suggested_colormap_half_range": diff_p99,   # symmetric diverging colormap half-range
        }
    diff_members["EXTENT_MIN"] = extent_min
    diff_members["EXTENT_MAX"] = extent_max

    # 5. Write the two derived cache sets (+ comparison sidecars).
    src = surrogate_npz_path.name
    _write_set(out_dir / "mock_ground_truth.npz", gt_members,
               kind="comparison_ground_truth", outputs=list(gt_dense.keys()), source=src)
    _write_set(out_dir / "diff.npz", diff_members,
               kind="comparison_diff", outputs=list(report.keys()), source=src)

    return {"dims": [int(d) for d in dims], "fields": report}
