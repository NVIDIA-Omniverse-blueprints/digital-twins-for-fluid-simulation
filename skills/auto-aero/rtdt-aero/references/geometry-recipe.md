# Auto-aero geometry recipe

Use this after the general Kit-CAE 3.0 procedure in
`skills/core/rtdt-customize/references/geometry-and-inference.md`.

## Coordinate contract

For the current `/World/Domain` `Approx_2M` variant:

- origin `(0, 0, 0)`;
- spacing `(0.036, 0.036, 0.036)`;
- minimum extent `(-50, -40, -10)`;
- maximum extent `(250, 40, 60)`;
- physical bounds `(-1.8, -1.44, -0.36)` through `(9.0, 1.44, 2.16)`.

The visual stage is Z-up with `metersPerUnit = 0.01`. `/World/CAE` maps the inference SI frame into
the presentation frame. Do not infer cosmetic placement from the inference mesh's raw coordinates
alone.

Re-read `source/specializations/auto-aero/stages/Base.usda` before using these numbers because it is
the domain's authoring layer; a domain change invalidates this recipe. Validate cross-layer targets
and variants against the fully composed
`source/specializations/auto-aero/stages/Main.usda`.

## Pattern A: another variant of the trained car family

Use the existing nested variant tree in
`source/specializations/auto-aero/stages/layers/CarCFD.usda`:

1. Prepare the new PLY in the same coordinate frame and preprocessing convention as the shipped
   surfaces.
2. Add the AppState token and regenerate the schema.
3. Add matching hero/CFD variant choices.
4. Put the PLY `payload` and `omni:rtwt:model:tag` in the new CFD variant leaf. Preserve the outer
   `OmniSciDataset`, `OmniSciFileFormatArgsPythonAPI`, and `RtwtModelAPI`.
5. Add the manifest control/bindings and frontend widget.
6. Run standard-profile inference, compare against a trusted baseline, then rebuild lite cache data
   if this axis will ship in lite.

This is appropriate for rims, mirrors, spoiler, and similarly trained car-family variations.
Ride-height payloads exist as a dormant nested dimension in `CarCFD.usda`, but ride height is not an
active shipped control/axis. Exposing it requires the complete schema, manifest/binding, matching
hero-asset variant, AppState default, frontend, inference, and cache work above.

## Pattern B: a distinct inference geometry

1. Create the destination and prepare the PLY:

   ```bash
   mkdir -p source/specializations/auto-aero/data/<geometry>
   python tools/geometry/prepare_mesh.py \
     --in <input-binary-stl> \
     --out source/specializations/auto-aero/data/<geometry>/<model>.ply \
     --asset-path ../../data/<geometry>/<model>.ply \
     --model-tag <geometry>/<model>.ply \
     --prim NewCFD \
     --domain-min "-1.8 -1.44 -0.36" \
     --domain-max "9.0 1.44 2.16" \
     --center "1.49 0 0.33" \
     [--up-axis Y] [--close-holes]
   ```

   Review the scaling notice and inspect the result. The emitted prim belongs in a new layer under
   `stages/layers/`, so `../../data/...` is the correct stage-relative `--asset-path`;
   `--model-tag` remains relative to the model/data root.

2. Create `source/specializations/auto-aero/stages/layers/<geometry>.usda` with the normal `World`
   root and paste the emitted plugin-backed model prim beneath it:

   ```usda
   #usda 1.0
   (
       defaultPrim = "World"
       metersPerUnit = 0.01
       upAxis = "Z"
   )

   def Xform "World"
   {
       def OmniSciDataset "NewCFD" (
           prepend apiSchemas = ["OmniSciFileFormatArgsPythonAPI", "RtwtModelAPI"]
           prepend payload = @../../data/<geometry>/<model>.ply@
       )
       {
           string omni:rtwt:model:tag = "<geometry>/<model>.ply"
       }
   }
   ```

   Then compose that prim under `World` in `Base.usda`:

   ```usda
   def "NewCFD" (
       prepend references = @./layers/<geometry>.usda@</World/NewCFD>
   )
   {
   }
   ```

   Do not paste `NewCFD` as a sibling inside `CarCFD.usda`: `Base.usda` references only
   `CarCFD.usda@</World/CarCFD>`, so an unrelated sibling in that layer would not compose into the
   application stage.

   For Pattern A's nested variant tree, do not duplicate the complete emitted prim in every choice.
   Apply the APIs once on the base `OmniSciDataset`, then move only the emitted `payload` and
   `omni:rtwt:model:tag` opinions into each variant leaf.

3. Add an inference AppState token for a live model choice. Add a `Geometry` variant set on
   `/World/Inference`; each choice authors
   `cae:viz:dataset_selection:model:target` to exactly one model dataset. Remove any stronger direct
   target opinion that would mask the variant.
4. Add corresponding cosmetic visibility/variant wiring. Derive its transform from `/World/CAE`
   plus the asset's up-axis conversion so the cosmetic and field overlap.
5. Add the manifest control with `role = "inference"`, explicit cache values if pre-caching is
   supported, and `Variant` bindings. Keep its ID equal to the schema attribute short key.
6. Add the frontend widget and validate with the composed stage.
7. Run standard-profile inference and verify PLY plugin loading, model target, result revision,
   cache-backed Warp SimData field reconstruction, visualization, and numerical behavior.

The shipped model is trained for its documented automotive domain. A wing, building, or unrelated
shape may execute but remain out of distribution; meaningful results require a qualified model
behind the same inference wire.

## Result and visualization invariants

Do not duplicate result datasets for geometry choices. Every model choice writes to
`/World/InferenceResults`, which references `/World/Domain`, applies `RtwtInferenceResultsAPI`, and
pairs each `OmniSciArrayAPI:<Field>` with `OmniSciFieldAPI:<Field>`.

Keep `RtwtResultFieldSelectionAPI` mappings and manifest outputs unchanged unless the producer fields
also change. Visualization operators consume names through token-array `fieldNames` attributes.

## Lite completion gate

A geometry axis changes the cache identity. Before shipping lite:

- explicitly choose the tuples the lite release will support; do not assume the manifest's full
  Cartesian pre-cache product is the intended shipped set;
- verify every intended tuple has a payload and correct sidecar;
- test every supported tuple, not only each axis independently;
- test an unsupported tuple and confirm it is rejected without leaving a stale field;
- confirm result revisions change when the selected payload changes.
