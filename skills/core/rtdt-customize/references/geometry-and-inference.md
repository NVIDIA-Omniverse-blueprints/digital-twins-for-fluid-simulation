# Geometry and inference with Kit-CAE 3.0

Separate the cosmetic asset from the inference surface. A visual mesh can be rich and transformed for
presentation; the inference surface must be a clean PLY payload in the model/domain coordinate frame.
The field result is a third object: one native OmniSci dataset whose revision atomically selects
cache-backed NanoVDB buffers.

## 1. Inspect the domain and model assumptions

Read the active stage and served model before converting anything:

- domain origin, spacing, minimum extent, maximum extent, units, and up axis;
- model training geometry class and preprocessing requirements;
- required watertightness and surface orientation;
- existing transforms between inference space, visualization space, and the cosmetic asset.

Running successfully on a new shape does not establish physical validity. Treat geometry outside the
training distribution as a model qualification problem.

## 2. Prepare the PLY and native USDA

Use the repository mesh utility for conversion and geometric cleanup:

```bash
python tools/geometry/prepare_mesh.py \
  --in <input-binary-stl> \
  --out source/specializations/<specialization>/data/<geometry>/<model>.ply \
  --asset-path ../../data/<geometry>/<model>.ply \
  --model-tag <geometry>/<model>.ply \
  --prim ModelCFD \
  --domain-min "<x y z>" \
  --domain-max "<x y z>" \
  --center "<x y z>" \
  [--up-axis Y] [--close-holes]
```

Review and report any scaling notice. Inspect the generated surface for orientation, topology,
domain fit, and reasonable scale. This example assumes the emitted prim will be pasted into a
`stages/layers/*.usda` layer, so `../../data/...` is the correct layer-relative payload path.
Recompute `--asset-path` from the receiving layer if authoring elsewhere; keep `--model-tag`
relative to the model/data root.

The utility emits the current, ready-to-paste native USDA for a sibling model prim. For a nested
variant tree, apply `OmniSciFileFormatArgsPythonAPI` and `RtwtModelAPI` once on the base
`OmniSciDataset`, then move only the emitted `payload` and `omni:rtwt:model:tag` opinions into each
variant leaf.

## 3. Author plugin-backed model geometry

The auto-aero pattern is an outer `OmniSciDataset` that applies
`OmniSciFileFormatArgsPythonAPI` and the local `RtwtModelAPI`, with each variant leaf composing a PLY
payload:

```usda
def OmniSciDataset "ModelCFD" (
    prepend apiSchemas = ["OmniSciFileFormatArgsPythonAPI", "RtwtModelAPI"]
    prepend payload = @../../data/<geometry>/<model>.ply@
)
{
    string omni:rtwt:model:tag = "<geometry>/<model>.ply"
}
```

The file-format plugin lazily composes the mesh dataset and its native arrays. The snippet above is
the sibling-prim form emitted by the tool; follow the variant-leaf caveat from step 2 when geometry
is selected by variants. Do not inline old field-array adapter prims.

The inference prim selects the model through
`cae:viz:dataset_selection:model:target`. If a control swaps model geometry, author the target only
inside the corresponding variant choices; a stronger direct relationship opinion will mask the
variant.

## 4. Author the inference domain

The current uniform-grid domain is:

```usda
def OmniSciDataset "Domain" (
    prepend apiSchemas = ["OmniSciVtkImageDataAPI"]
)
{
    uniform float3 omni:vtk:origin = (0, 0, 0)
    uniform float3 omni:vtk:spacing = (0.036, 0.036, 0.036)
    uniform int3 omni:vtk:minExtent = (-50, -40, -10)
    uniform int3 omni:vtk:maxExtent = (250, 40, 60)
}
```

Preserve the model's expected coordinate system. Changing domain dimensions or spacing is an
inference-contract change, not a cosmetic edit.

## 5. Author one result dataset

Reference the domain and apply the result schema plus paired field/array API instances:

```usda
def OmniSciDataset "InferenceResults" (
    prepend apiSchemas = [
        "RtwtInferenceResultsAPI",
        "OmniSciArrayAPI:Pressure",
        "OmniSciFieldAPI:Pressure"
    ]
    prepend references = </World/Domain>
)
{
    uniform token omni:rtwt:inference_results:revision = ""
    string omni:sci:field:Pressure:name = "Pressure"
    uniform token omni:sci:field:Pressure:association = "node"
}
```

The inference implementation copies each NanoVDB payload into an immutable
`omni.cae.core.cache` entry and changes the dataset revision only after the complete payload is
ready. It does not author USD array values. When a consumer requests a field, the registered
`GetField` command reconstructs a `warp_simdata.Field` from the cached buffer. Consumers should
treat one revision as an atomic snapshot.

## 6. Connect wire outputs and visualization

For each producer output:

```usda
def Prim "Inference" (
    prepend apiSchemas = ["RtwtResultFieldSelectionAPI:nvdb_pressure"]
)
{
    rel omni:rtwt:result_field_selection:nvdb_pressure:target = </World/InferenceResults>
    uniform token omni:rtwt:result_field_selection:nvdb_pressure:fieldName = "Pressure"
}
```

Mirror the same wire ID, target, and field in `[outputs.nvdb_pressure]`. The stage API drives the
runtime request; the manifest entry provides cross-check metadata.

Visualization operators select fields by name:

```usda
uniform token[] cae:viz:field_selection:colors:fieldNames = ["Pressure"]
```

For a planar slice, bind `Materials/UnlitScalarColor` using `cae/mdl/basic.mdl` and subIdentifier
`UnlitScalarColor`.

## 7. Expose a geometry control

For an inference-affecting choice:

1. add a typed token to the inference AppState API and regenerate the schema;
2. add a manifest control whose ID equals the schema short key;
3. give it `role = "inference"` and explicit `cache_values` when pre-caching is supported;
4. bind it to model-target variants and any cosmetic visibility variants;
5. author the AppState default;
6. add the frontend widget if users must drive it.

For a cosmetic-only choice, use a visualization AppState attribute and omit `cache_values`.

## 8. Validate and qualify

Run manifest/schema/stage validation, then test the standard profile for live inference. Confirm:

- the selected PLY payload resolves through the USD plugin;
- the inference target changes as intended;
- every requested output updates on the result dataset;
- field-selection names resolve;
- the visualization and cosmetic geometry align;
- results are numerically and physically qualified for the new geometry.

Lite mode requires a rebuilt cache and verified sidecars for every supported tuple. Per-axis option
lists alone are insufficient evidence that all tuples exist.
