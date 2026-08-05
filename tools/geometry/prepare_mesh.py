# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Prepare a user-supplied mesh as a CFD inference geometry.

Bringing a new geometry into an existing RTDT environment has two mechanical chores this tool
automates so a future change is fast and repeatable:

1. **Fit the mesh to the simulation domain.** The inference model samples a fixed voxel domain; the
   mesh must live in that same coordinate frame (SI / meters). A geometry authored at its own native
   scale almost never matches, so it is scaled and centred to fit the domain — and the tool prints a
   plain-language notice of *what* it scaled and *why*, so the scaling is never silent.
2. **Emit indexed geometry + the USD boilerplate.** It writes a vertex-deduplicated ASCII PLY
   and prints a ready-to-paste, plugin-backed
   ``OmniSciDataset`` payload with ``OmniSciFileFormatArgsPythonAPI``, ``RtwtModelAPI``, and the
   model tag. The Kit-CAE file-format plugin supplies the mesh topology and arrays from the payload.

Two common mismatches it also handles so the inference mesh lands correctly:

* ``--up-axis Y`` rotates a Y-up source into the domain's Z-up frame (most CAD/character assets are
  Y-up; the simulation domain here is Z-up). Apply it whenever the source up-axis differs from the
  domain's, or the mesh lies on its side.
* ``--close-holes`` attempts to cap simple open boundary loops (collars, cuffs, hems, trimmed
  shells). The topology check reports any remaining open edges; complex input may require repair in
  a dedicated mesh tool. The model needs a closed surface.

Standard library only: this tool accepts binary STL and emits ASCII PLY. Kit-CAE's Trimesh
file-format plugin supports STL, PLY, and 3MF payloads, but converting or fitting PLY/3MF inputs is
outside this tool's scope. Export other sources to binary STL first, then run this tool.

Example:
    python tools/geometry/prepare_mesh.py --in part.stl \\
        --out source/specializations/<spec>/data/showcase/part.ply \\
        --asset-path ../../data/showcase/part.ply \\
        --model-tag showcase/part.ply --prim GearCFD --up-axis Y --close-holes \\
        --domain-min " -1.8 -1.44 -0.36" --domain-max "9.0 1.44 2.16"

Derive ``--domain-min``/``--domain-max`` from the stage's Domain prim:
``min = omni:vtk:origin + omni:vtk:minExtent * omni:vtk:spacing`` and
``max = omni:vtk:origin + omni:vtk:maxExtent * omni:vtk:spacing``.
"""

from __future__ import annotations

import argparse
import struct
import sys


def _read_stl_triangles(path):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 80)[0]
    tris = []
    for t in range(n):
        base = 84 + t * 50 + 12  # skip 80-byte header + count, then the per-triangle normal
        tris.append([struct.unpack_from("<fff", data, base + v * 12) for v in range(3)])
    return tris


def _bounds(points):
    xs, ys, zs = zip(*points)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _boundary_counts(faces):
    """Map each undirected edge -> number of incident faces. count == 1 marks an open boundary edge."""
    from collections import defaultdict
    cnt = defaultdict(int)
    for f in faces:
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            cnt[(a, b) if a < b else (b, a)] += 1
    return cnt


def _close_holes(verts, faces):
    """Attempt to cap simple open boundary loops with winding-agnostic centroid fans.

    Walks the undirected boundary edges into loops and caps each with a fan to its centroid. Returns
    (verts, faces, n_capped, boundary_before, boundary_after). Robust for trimmed/organic shells; for
    a mesh whose boundaries are not simple loops, fall back to a convex hull.
    """
    from collections import defaultdict
    cnt = _boundary_counts(faces)
    before = sum(1 for v in cnt.values() if v == 1)
    adj = defaultdict(set)
    for (a, b), v in cnt.items():
        if v == 1:
            adj[a].add(b)
            adj[b].add(a)
    verts = list(verts)
    visited, capped = set(), 0
    for start in list(adj):
        if start in visited or len(adj[start]) != 2:
            continue
        loop, prev, cur = [start], None, next(iter(adj[start]))
        visited.add(start)
        while cur != start:
            loop.append(cur)
            visited.add(cur)
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
        if len(loop) < 3:
            continue
        cx = sum(verts[v][0] for v in loop) / len(loop)
        cy = sum(verts[v][1] for v in loop) / len(loop)
        cz = sum(verts[v][2] for v in loop) / len(loop)
        ci = len(verts)
        verts.append((cx, cy, cz))
        n = len(loop)
        for k in range(n):
            faces.append([loop[k], loop[(k + 1) % n], ci])
        capped += 1
    after = sum(1 for v in _boundary_counts(faces).values() if v == 1)
    return verts, faces, capped, before, after


def _vec3(s):
    parts = [float(v) for v in s.replace(",", " ").split()]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three numbers, e.g. \"1.0 0 0.5\"")
    return parts


def main(argv=None):
    p = argparse.ArgumentParser(prog="prepare_mesh", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="inp", required=True, help="input binary STL")
    p.add_argument("--out", required=True, help="output ASCII PLY (place it under the model/data root)")
    p.add_argument("--model-tag", required=True, help="model tag: PLY path relative to the model root")
    p.add_argument("--prim", default="NewGeometryCFD", help="OmniSciDataset prim name for the emitted snippet")
    p.add_argument(
        "--asset-path",
        default="",
        help="stage-relative USD asset path to the PLY in the emitted snippet (default: the --out path)",
    )
    p.add_argument("--domain-min", type=_vec3, required=True, help="domain physical min 'x y z' (SI)")
    p.add_argument("--domain-max", type=_vec3, required=True, help="domain physical max 'x y z' (SI)")
    p.add_argument("--fit", type=float, default=0.8, help="fraction of the domain the mesh should fill (default 0.8)")
    p.add_argument("--center", type=_vec3, default=None, help="placement centre 'x y z' (default: domain centre; align to the reference geometry's region for best viz overlap)")
    p.add_argument("--up-axis", choices=["Y", "Z"], default="Z", help="source up-axis; 'Y' rotates the mesh into the domain's Z-up frame (default Z = no rotation)")
    p.add_argument(
        "--close-holes",
        action="store_true",
        help="attempt to cap simple open boundary loops (for trimmed/organic shells)",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    tris = _read_stl_triangles(args.inp)
    if args.up_axis == "Y":
        # Stand a Y-up source upright in the Z-up domain: (x, y, z) -> (x, -z, y).
        tris = [[(x, -z, y) for (x, y, z) in tri] for tri in tris]
    raw_pts = [v for tri in tris for v in tri]
    (nx0, ny0, nz0), (nx1, ny1, nz1) = _bounds(raw_pts)
    native = (nx1 - nx0, ny1 - ny0, nz1 - nz0)
    native_center = ((nx0 + nx1) / 2, (ny0 + ny1) / 2, (nz0 + nz1) / 2)

    dmin, dmax = args.domain_min, args.domain_max
    domain_ext = [dmax[i] - dmin[i] for i in range(3)]
    # Scale so the mesh fits within `fit` of the domain on its most-constrained axis.
    per_axis = [domain_ext[i] / native[i] for i in range(3) if native[i] > 1e-9]
    scale = args.fit * min(per_axis) if per_axis else 1.0
    center = args.center or [(dmin[i] + dmax[i]) / 2 for i in range(3)]

    def xf(v):
        return tuple((v[i] - native_center[i]) * scale + center[i] for i in range(3))

    # Deduplicate vertices so the result is a proper indexed (watertight-capable) surface.
    verts, index, faces = [], {}, []
    for tri in tris:
        face = []
        for v in tri:
            X, Y, Z = xf(v)
            key = (round(X, 6), round(Y, 6), round(Z, 6))
            i = index.get(key)
            if i is None:
                i = len(verts)
                index[key] = i
                verts.append(key)
            face.append(i)
        faces.append(face)

    if args.close_holes:
        verts, faces, capped, b0, b1 = _close_holes(verts, faces)
        print(f"closed holes: capped {capped} loop(s), open boundary edges {b0} -> {b1}", file=sys.stderr)

    open_boundary_edges = sum(
        1 for count in _boundary_counts(faces).values() if count == 1
    )
    if open_boundary_edges:
        repair_hint = (
            "rerun with --close-holes or repair the source mesh externally"
            if not args.close_holes
            else "repair the source mesh externally"
        )
        print(
            f"WARNING: topology check found {open_boundary_edges} open boundary edge(s); "
            f"{repair_hint} before inference.",
            file=sys.stderr,
        )
    else:
        print("topology check: no open boundary edges", file=sys.stderr)

    with open(args.out, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(verts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write(f"element face {len(faces)}\n")
        f.write("property list uchar int vertex_indices\nend_header\n")
        for x, y, z in verts:
            f.write(f"{x} {y} {z}\n")
        for a, b, c in faces:
            f.write(f"3 {a} {b} {c}\n")

    fit_ext = tuple(native[i] * scale for i in range(3))
    asset = args.asset_path or args.out

    # The scaling notice — surfaced, never silent.
    print("=== mesh scaling notice ===", file=sys.stderr)
    if args.up_axis == "Y":
        print("rotated Y-up -> Z-up to match the domain frame.", file=sys.stderr)
    print(f"native size (its own units):  ({native[0]:.3g}, {native[1]:.3g}, {native[2]:.3g})", file=sys.stderr)
    print(f"domain size (SI):             ({domain_ext[0]:.3g}, {domain_ext[1]:.3g}, {domain_ext[2]:.3g})", file=sys.stderr)
    print(f"scaled by {scale:.4g}x -> ({fit_ext[0]:.3g}, {fit_ext[1]:.3g}, {fit_ext[2]:.3g}), centred at {tuple(round(c,3) for c in center)}", file=sys.stderr)
    print("Why: the geometry is being dropped into an existing environment whose domain + model are\n"
          "fixed; it must be fit to that volume. A model/environment built for this geometry's native\n"
          "scale would not need this — the scaling is a consequence of reusing the existing setup.",
          file=sys.stderr)
    print(f"wrote {args.out}: {len(verts)} verts, {len(faces)} faces", file=sys.stderr)

    # Ready-to-paste CFD geometry payload for a composed geometry layer's World prim.
    print(f'''
# --- paste beneath /World in a new geometry layer composed by the application stage ---
    def OmniSciDataset "{args.prim}" (
        prepend apiSchemas = ["OmniSciFileFormatArgsPythonAPI", "RtwtModelAPI"]
        prepend payload = @{asset}@
    )
    {{
        string omni:rtwt:model:tag = "{args.model_tag}"
    }}''')
    return 0


if __name__ == "__main__":
    sys.exit(main())
