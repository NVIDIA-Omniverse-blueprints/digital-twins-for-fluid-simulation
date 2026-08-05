# prepare_mesh — bring a geometry into a workflow

`prepare_mesh.py` turns an external mesh into a CFD inference geometry for an RTDT workflow. It does
the two mechanical chores that otherwise trip people up:

- **Fits the mesh to the simulation domain** (SI/meters) and prints a plain-language **scaling
  notice** — what it scaled and why — so scaling a dropped-in geometry into a fixed environment is
  never silent.
- **Emits indexed geometry + Kit-CAE 3 USD boilerplate**: a vertex-deduplicated `.ply` plus a
  ready-to-paste, plugin-backed `OmniSciDataset` payload with
  `OmniSciFileFormatArgsPythonAPI`, `RtwtModelAPI`, and the model tag.
- **Fixes two common source mismatches** on request: `--up-axis Y` rotates a Y-up asset into the
  domain's Z-up frame; `--close-holes` attempts to cap simple open boundary loops. Review the
  topology check printed on stderr: complex or non-manifold input may still require repair in a
  dedicated mesh tool before inference.

The conversion tool and the runtime plugin have intentionally different boundaries:

- `prepare_mesh.py` uses only the Python standard library. It accepts **binary STL** and emits
  **ASCII PLY**.
- Kit-CAE 3's Trimesh file-format plugin can load **STL, PLY, and 3MF** payloads. It does not use the
  legacy Trimesh Data Delegate.

To fit or repair any other source format, including PLY, 3MF, or a USD cosmetic asset, export the
target mesh to binary STL first and then run this tool. PLY is the recommended output here because
the resulting file is used both by the Kit-CAE plugin and by the inference model.

```bash
python tools/geometry/prepare_mesh.py \
  --in part.stl \
  --out source/specializations/<spec>/data/<dir>/part.ply \
  --asset-path ../../data/<dir>/part.ply \
  --model-tag <dir>/part.ply \
  --prim PartCFD \
  --domain-min "<x y z>" --domain-max "<x y z>"
```

`--domain-min`/`--domain-max` are the domain's physical bounds (SI). Derive them from the stage's
Domain prim:

```text
min = omni:vtk:origin + omni:vtk:minExtent * omni:vtk:spacing
max = omni:vtk:origin + omni:vtk:maxExtent * omni:vtk:spacing
```

The two PLY paths serve different consumers:

- `--asset-path` is the USD payload path, resolved relative to the USDA layer that receives the
  generated snippet. For `stages/layers/CarCFD.usda`, data in the specialization's `data/`
  directory starts with `../../data/`.
- `--model-tag` is the PLY path relative to `RTWT_MODEL_ROOT` (normally the mounted model/data
  directory) and is consumed by the AeroNIM inference model.

If `--asset-path` is omitted, the emitted payload uses `--out` verbatim. Supply `--asset-path`
whenever that filesystem path is not also correct relative to the target USDA layer.

The generated recipe has this shape:

```usda
def OmniSciDataset "PartCFD" (
    prepend apiSchemas = ["OmniSciFileFormatArgsPythonAPI", "RtwtModelAPI"]
    prepend payload = @../../data/<dir>/part.ply@
)
{
    string omni:rtwt:model:tag = "<dir>/part.ply"
}
```

The PLY file-format plugin composes the mesh topology and array APIs through the payload; do not add
legacy `CaeFieldArray`, `CaeMeshAPI`, or Data Delegate child prims. For variant-driven geometry,
apply both APIs once on the base `OmniSciDataset`, then author the `payload` and model tag in each
leaf variant.

Other options are `--fit <fraction>` (how much of the domain to fill, default 0.8),
`--center "x y z"` (placement; default is the domain centre — align it to the reference geometry's
region for the best overlap with the existing visualization), `--up-axis {Y,Z}` (default Z; use Y
for a Y-up source), and `--close-holes` (attempt to cap simple open boundary loops).

The tool reports the number of remaining open boundary edges. Zero open boundary edges is required
before inference, but is not by itself proof that a complex mesh is manifold or correctly oriented.
If edges remain after `--close-holes`, repair the source mesh externally and rerun the conversion.

See `skills/core/rtdt-customize/references/geometry-and-inference.md` for the full procedure this
tool fits into.
