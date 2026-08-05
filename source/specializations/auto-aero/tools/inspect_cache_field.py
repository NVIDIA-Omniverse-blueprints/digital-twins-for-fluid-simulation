#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

"""Diagnostic: decode a cached comparison/inference .npz and report field distributions.

Sanity-checks the NanoVDB decode path used by the comparison-view bake: prints percentiles + the
fraction of zero (masked/background) voxels per field, and verifies cross-field coherence
(‖velocity‖ ≈ velocity_magnitude). Run in the aeronim container, same mounts as the bake.
"""

import os
import sys

_RTWT_PYTHON_PATH = os.environ.get("RTWT_PYTHON_PATH")
if _RTWT_PYTHON_PATH:
    sys.path.insert(0, _RTWT_PYTHON_PATH)

import numpy as np


def _stats(name, a):
    flat = a.reshape(-1, 3) if (a.ndim == 2 and a.shape[1] == 3) else a.reshape(-1)
    mag = np.linalg.norm(flat, axis=1) if flat.ndim == 2 else np.abs(flat)
    nz = mag > 0
    pct = np.percentile(mag[nz], [50, 90, 99, 99.9]) if nz.any() else [0, 0, 0, 0]
    print(f"  {name:26s} n={mag.size} zero_frac={1.0 - nz.mean():.3f} "
          f"p50={pct[0]:.3g} p90={pct[1]:.3g} p99={pct[2]:.3g} p99.9={pct[3]:.3g} max={mag.max():.3g}")
    return flat


def main() -> int:
    core = os.environ.get("RTWT_BAKE_CORE", "/bake_core")
    npz_path = os.environ.get("RTWT_INSPECT_IN", "/out/9eae54bb9f680734.npz")
    device = os.environ.get("RTWT_BAKE_DEVICE", "cuda")
    sys.path.insert(0, core)
    import warp as wp
    wp.init()
    import bake

    with np.load(npz_path) as npz:
        emin = npz["EXTENT_MIN"].astype(np.int32).ravel()
        emax = npz["EXTENT_MAX"].astype(np.int32).ravel()
        members = {k: npz[k] for k in npz.files}
    dims = emax - emin + 1
    print(f"[inspect] {npz_path}  dims={tuple(int(d) for d in dims)}  members={sorted(members)}")

    vel = mag = None
    for name in ("nvdb_velocity", "nvdb_velocity_magnitude", "nvdb_pressure"):
        if name not in members:
            continue
        is_vec = name == "nvdb_velocity"
        dense = bake.decode(members[name], dims, emin, vector=is_vec, device=device)
        flat = _stats(name, dense)
        if name == "nvdb_velocity":
            vel = flat
        elif name == "nvdb_velocity_magnitude":
            mag = flat

    if vel is not None and mag is not None:
        recomputed = np.linalg.norm(vel, axis=1)
        err = np.abs(recomputed - mag)
        denom = np.maximum(mag, 1e-6)
        rel = err[mag > 0] / denom[mag > 0]
        print(f"[inspect] coherence ‖velocity‖ vs velocity_magnitude: "
              f"max_abs_err={err.max():.4g} mean_rel_err={rel.mean():.4g} p99_rel_err={np.percentile(rel, 99):.4g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
