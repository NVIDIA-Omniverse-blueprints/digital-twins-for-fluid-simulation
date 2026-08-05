# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Automotive-aero specialization callbacks.

``dynamic_pressure`` is the named ``ColormapDomain`` policy referenced by the ``velocity`` control
in ``workflow.toml``. It encodes the aero-specific colormap physics, keeping it out of the
use-case-agnostic core:

* velocity colormap legend domain ``(0.1, 1.5*v)``  (the field shaders use ``(0.0, 1.5*v)``);
* pressure domain ``(-q, q)`` where ``q = 1/2 * rho * v^2`` (dynamic pressure, air density 1.225).

Both callbacks are pure functions returning concrete ``(prim_path, attribute, value)`` writes; the
controller engine applies them inside its change block.
"""

from pxr import Gf

from omni.rtwt.controller import control_registry

# Air density (kg/m^3) for the dynamic-pressure colormap domain.
_AIR_DENSITY = 1.225

# The inference prim that owns the result fields; writing its resultSetOverride re-runs inference.
_INFERENCE_PRIM = "/World/Inference"

# Diff VOLUME render prims, keyed by the "{vizMode}_{vizField}" selector. They color by the *Delta field
# prims, which /World/InferenceDiff pre-loads from diff.npz at startup, so revealing one never races the
# live inference. They default to invisible (a local stage opinion); the diff view makes the matching one
# visible at runtime while the *Delta Mode variant hides the normal prims.
# Slices are intentionally absent: the *Delta Mode variants re-colour the LIVE slice prim in place (delta
# field + diverging colormap), so there is no separate slice render prim. Re-texturing an already-drawn prim
# forces a clean present, whereas revealing a previously hidden separate prim incurs a render cold-start.
_DELTA_PRIMS = {
    "Volume_VelocityMagnitude": "/World/CAE/Volume_VelocityMagnitudeDelta",
    "Volume_Pressure": "/World/CAE/Volume_PressureDelta",
}


def dynamic_pressure(state: dict) -> list:
    """Return the velocity/pressure colormap + shader domain writes for the current state.

    The planar-slice domains are diff-aware: in the comparison diff view the slices are re-coloured in
    place (their Mode variant points them at the signed-delta fields + the diverging delta colormap), so
    their inputs:domain uses the fixed ±delta scale; otherwise the live dynamic-pressure scale. Only the
    cheap inputs:domain shader param changes here per tick (it does NOT re-probe the slice), so the slider
    stays smooth — the field + colormap swap lives in the Mode variant and changes only on a result-set
    switch.
    """
    velocity = float(state.get("velocity", 25.0))
    vel_max = 1.5 * velocity
    q = 0.5 * _AIR_DENSITY * velocity * velocity
    diff = state.get("comparisonResultSet") == "diff"
    vel_slice_domain = Gf.Vec2f(-2.0, 2.0) if diff else Gf.Vec2f(0.0, vel_max)
    pres_slice_domain = Gf.Vec2f(-10.0, 10.0) if diff else Gf.Vec2f(-q, q)
    return [
        # Colormap legend prims (note the 0.1 minimum on the velocity legend).
        ("/World/Colormaps/VelocityColormap", "domain", Gf.Vec2f(0.1, vel_max)),
        ("/World/Colormaps/PressureColormap", "domain", Gf.Vec2f(-q, q)),
        # Field shader domains (0.0 minimum for velocity normalization).
        ("/World/CAE/Streamlines/Materials/AnimatedStreaks/Shader", "inputs:domain", Gf.Vec2f(0.0, vel_max)),
        ("/World/CAE/Streamlines/Materials/ScalarColor/Shader", "inputs:domain", Gf.Vec2f(0.0, vel_max)),
        ("/World/CAE/PlanarSlice_VelocityMagnitude/Materials/UnlitScalarColor/Shader", "inputs:domain", vel_slice_domain),
        ("/World/CAE/PlanarSlice_Pressure/Materials/UnlitScalarColor/Shader", "inputs:domain", pres_slice_domain),
    ]


def comparison_override(state: dict) -> list:
    """Map the selected comparison result set to the inference ``resultSetOverride`` filename.

    The ``comparisonResultSet`` control drives the comparison view. ``"off"`` clears the override so the
    live combo renders; ``surrogate``/``ground_truth`` resolve to their pre-baked ``.npz`` (filenames from
    the manifest) and the inference operator shows that exact cached result. Writing a tracked attribute on
    the inference prim re-runs the operator, the same pass a ``velocity`` change uses.

    ``diff`` is rendered from the signed deltas that /World/InferenceDiff pre-loads onto the *Delta field
    prims at startup; the live result prims are hidden in diff mode. The override is not cleared for diff
    (an empty override re-runs the live inference — a real NIM call in standard mode — for prims that are
    not even shown), so the hidden live prims stay pinned to the cached ``surrogate`` npz: disk-only, no
    NIM call, no spurious "inferring" indicator. Only ``off`` clears the override, returning the explore
    view to the live combo.
    """
    rs = state.get("comparisonResultSet", "off")
    npz = ""
    if rs != "off":
        reg = control_registry.get_workflow_registry()
        spec = getattr(reg.manifest, "comparison", None) if reg else None
        if spec:
            # diff hides the live prims and draws the pre-loaded deltas, so keep the live inference pinned to
            # a CACHED result (the surrogate) rather than clearing the override and triggering a NIM call.
            lookup = "surrogate" if rs == "diff" else rs
            chosen = spec.result_sets.get(lookup) or spec.result_sets.get(spec.default_result_set)
            if chosen:
                npz = chosen.npz
    writes = [(_INFERENCE_PRIM, "omni:rtwt:inference:resultSetOverride", npz)]

    # Diff view: the *Delta render prims color by the pre-loaded *Delta fields and the *Delta Mode variant
    # hides the normal prims; here we reveal the matching delta render prim (and hide the rest). For any
    # non-diff result set every delta prim is hidden. These visibility writes are applied inside the engine's
    # change block (the operator pass), so the swap repaints cleanly.
    active = _DELTA_PRIMS.get(f"{state.get('vizMode')}_{state.get('vizField')}") if rs == "diff" else None
    for path in _DELTA_PRIMS.values():
        writes.append((path, "visibility", "inherited" if path == active else "invisible"))
    return writes
