#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Auto-aero bake runner for the cached comparison view (maintainer tool — run once).

Generates ``mock_ground_truth.npz`` + ``diff.npz`` from the default-combo surrogate cache entry,
using the use-case-agnostic bake helper ``tools/comparison/bake.py`` plus this specialization's
**wake-weighted perturbation policy**. Runs in a Warp SimData environment (the AeroNIM container):

    docker compose --profile standard run --rm --entrypoint /usr/bin/python3 \
      -e CUDA_VISIBLE_DEVICES=0 \
      -e RTWT_BAKE_CORE=/bake_core -e RTWT_BAKE_IN=/out/9eae54bb9f680734.npz -e RTWT_BAKE_OUT=/out \
      -v "$PWD/tools/comparison:/bake_core:ro" \
      -v "$PWD/source/specializations/auto-aero/tools:/bake_tools:ro" \
      -v "$PWD/source/specializations/auto-aero/data/cache:/out" \
      aeronim /bake_tools/bake_comparison_view.py

Calibration: run once at the default amplitude, read the printed diff peak%/RMS%, then re-run with
``-e RTWT_BAKE_AMPLITUDE=<amplitude * 5.0 / observed_peak_pct>`` to hit the ~5% peak target (the diff
is linear in amplitude, so one rescale converges).
"""

import json
import os
import sys

_RTWT_PYTHON_PATH = os.environ.get("RTWT_PYTHON_PATH")
if _RTWT_PYTHON_PATH:
    sys.path.insert(0, _RTWT_PYTHON_PATH)

import numpy as np

# Streamwise axis = +i (X): the Approx_2M domain is i in [-50, 250] (long downstream tail) vs the
# near-symmetric j in [-40, 40] and k in [-10, 60]; the only strongly asymmetric axis is i, extending
# far past the body into the wake. j = 0 is the Y symmetry plane. (Confirm the wake lobe sits *behind*
# the car visually after the first bake; if not, flip/repick the axis here.)
def wake_weighted_perturbation(
    field_name: str,
    dense: np.ndarray,
    world: np.ndarray,   # (N,3) world XYZ (unused here; we weight in normalized ijk for unit-robustness)
    ijk: np.ndarray,     # (N,3) int voxel indices, ij (Fortran) order
    *,
    amplitude: float = 0.05,   # peak fractional perturbation; calibrate to ~5% diff-of-range
    onset_frac: float = 0.35,  # streamwise fraction where the wake begins (behind the body)
    ramp_frac: float = 0.20,   # streamwise ramp length (fraction of the streamwise extent)
    lat_scale_frac: float = 0.22,  # lateral Gaussian width (fraction of the cross-stream extent)
) -> np.ndarray:
    """Smooth, spatially-varying multiplicative perturbation ``GT = surrogate * (1 + a*w(x))`` with
    ``w(x)`` peaking in the downstream wake core. Velocity (vector) is scaled component-wise so the
    direction is preserved and the recomputed speed stays consistent."""
    i = ijk[:, 0].astype(np.float64)
    j = ijk[:, 1].astype(np.float64)
    i0, i1 = float(i.min()), float(i.max())
    j0, j1 = float(j.min()), float(j.max())

    # Streamwise: smoothstep onset that saturates downstream of the body.
    t = (i - i0) / max(i1 - i0, 1.0)
    x = np.clip((t - onset_frac) / max(ramp_frac, 1e-6), 0.0, 1.0)
    stream = x * x * (3.0 - 2.0 * x)
    # Lateral: Gaussian centered on the Y symmetry plane (j = 0) -> wake core along the centerline.
    jscale = lat_scale_frac * max(j1 - j0, 1.0)
    lateral = np.exp(-((j - 0.0) / jscale) ** 2)

    w = (stream * lateral).astype(np.float32)          # in [0,1], peaks in the downstream-center wake
    factor = (1.0 + amplitude * w).astype(np.float32)

    if dense.ndim == 2 and dense.shape[1] == 3:        # velocity vector -> scale all components
        return dense * factor[:, None]
    return dense * factor                               # scalar field (pressure)


def main() -> int:
    core = os.environ.get("RTWT_BAKE_CORE", "/bake_core")
    in_npz = os.environ.get("RTWT_BAKE_IN", "/out/9eae54bb9f680734.npz")
    out_dir = os.environ.get("RTWT_BAKE_OUT", "/out")
    amplitude = float(os.environ.get("RTWT_BAKE_AMPLITUDE", "0.05"))
    device = os.environ.get("RTWT_BAKE_DEVICE", "cuda")

    sys.path.insert(0, core)
    import warp as wp  # noqa: E402 — must be importable from the bake env (aeronim container)

    wp.init()
    import bake  # noqa: E402 — the bake helper (tools/comparison/bake.py)

    print(f"[bake] core={core} in={in_npz} out={out_dir} amplitude={amplitude} device={device}")

    def perturb(name, dense, world, ijk):
        return wake_weighted_perturbation(name, dense, world, ijk, amplitude=amplitude)

    report = bake.bake_comparison(in_npz, perturb, out_dir, device=device)
    print("[bake] REPORT:\n" + json.dumps(report, indent=2))
    print("[bake] amplitude calibration: rescale RTWT_BAKE_AMPLITUDE by 5.0 / diff_peak_pct to hit ~5%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
