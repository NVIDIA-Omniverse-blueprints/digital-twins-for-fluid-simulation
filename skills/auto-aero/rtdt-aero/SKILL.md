---
name: rtdt-aero
description: Apply RTDT customization specifically to the shipped auto-aero virtual wind tunnel. Use when changing car CFD geometry variants, wind-tunnel controls, output fields, Kit-CAE 3.0 visualization, lite cache coverage, or the fixed comparison result sets. Read rtdt-core and rtdt-customize first.
---

# RTDT Auto-Aero

Read [rtdt-core](../../core/rtdt-core/SKILL.md) and
[rtdt-customize](../../core/rtdt-customize/SKILL.md) first. This skill maps their contracts onto the
shipped specialization.

## File map

| Concern | Repository-relative path |
|---|---|
| AppState schema | `source/specializations/auto-aero/extensions/omni.rtwt.auto_aero.schema/python/schemas/omniRtwtAuto/schema.usda` |
| Application entry and fully composed stage | `source/specializations/auto-aero/stages/Main.usda` |
| Base scene, domain, inference, and results | `source/specializations/auto-aero/stages/Base.usda` |
| CFD PLY variants | `source/specializations/auto-aero/stages/layers/CarCFD.usda` |
| Visualization operators and materials | `source/specializations/auto-aero/stages/BaseCAE.usda` |
| Visualization variants | `source/specializations/auto-aero/stages/BaseCAEVariants.usda` |
| Workflow | `source/specializations/auto-aero/workflow/workflow.toml` |
| Frontend state and widgets | `trame-app/app.py` |
| Browser state bridge and cache-option mapping | `trame-app/static/app_streamer.js` |
| Offline cache | `source/specializations/auto-aero/data/cache/` |

If a path changes, locate the current file before editing; do not guess an abbreviated schema path.

## Change a car geometry axis

The active shipped geometry controls are `Rims`, `Mirrors`, and `Spoiler`. `Ride_Height` is not a
shipped control axis. It is a nested CFD payload dimension in `CarCFD.usda`, selected as `High` by
`Base.usda`, but has no AppState attribute, manifest control/binding, active matching `CarHero`
variant, or frontend widget. Treat it as payload inventory, not as an already wired control.

Use the active controls as the template for a new axis:

1. Add the typed token/default to the correct AppState schema and regenerate the schema.
2. Add matching variant sets to the hero and CFD compositions as needed.
3. In `CarCFD.usda`, keep the outer `OmniSciDataset` with
   `OmniSciFileFormatArgsPythonAPI` and `RtwtModelAPI`; put each PLY payload and
   `omni:rtwt:model:tag` in the correct variant leaf.
4. Add the manifest control and `Variant` bindings. Keep the control ID equal to the schema short
   key.
5. Author the AppState default, bridged state key, and frontend widget. Keep that default aligned in
   Python `reset_state()` and JavaScript `resetControlState()`. For an inference axis, declare its
   `<key>_options` state and add the matching `setOpt(...)` mapping in
   `trame-app/static/app_streamer.js` so lite-mode restrictions reach the UI. If the axis affects
   the fixed comparison result, also update `FIXED_COMBO` and its baked data.
6. Validate schema/manifest/stage wiring and run live inference in the standard profile.

For a genuinely new geometry rather than another car variant, follow
[geometry-recipe.md](references/geometry-recipe.md).

## Change an output or visualization

Keep these synchronized:

- AeroNIM tensor name and `aeronim/rtwt/config.pbtxt`;
- `RtwtResultFieldSelectionAPI:<wire-id>` on the inference prim;
- paired `OmniSciArrayAPI:<Field>` and `OmniSciFieldAPI:<Field>` on `/World/InferenceResults`;
- `[outputs.<wire-id>]` in `workflow.toml`;
- `cae:viz:field_selection:<role>:fieldNames` on every consuming operator;
- lite cache payloads and sidecars.

Planar slices use `Materials/UnlitScalarColor` from `cae/mdl/basic.mdl`. Do not restore the removed
texture-slice material pattern.

## Cache consequences

Every inference AppState axis contributes to result identity. An inference-role control with
`cache_values` expands the intended pre-cache product, but that manifest product is not itself proof
of complete cache coverage.

The shipped lite cache intentionally covers eight tuples: four velocities by two spoiler states,
with mirrors fixed at `On` and rims fixed at `Standard`. The manifest's inference `cache_values`
describe a 32-tuple Cartesian product. Per-axis options reported by the runtime are unions across
available entries; they do not prove that an arbitrary cross-axis tuple exists.

After changing inference geometry, domain, outputs, or cache axes:

1. explicitly choose the tuples the lite release will support;
2. create a new empty staging cache, then run Kit on the host with reachable standard-profile Triton,
   `--/exts/omni.rtwt.inference/offline_mode=true` and
   `--/exts/omni.rtwt.inference/generate_if_missing=true`, and an absolute
   `--/exts/omni.rtwt.inference/offline_cache_dir=<staging-path>`; the cache key omits the model
   payload and domain, so reusing the tracked cache can produce stale hits; drive each approved tuple as documented in
   [README deployment modes](../../../README.md#deployment-modes); the shipped Compose mounts the
   cache read-only and its CACHE button only warms memory;
3. verify payload and sidecar consistency for every intended tuple;
4. test every supported tuple in lite mode, plus an unsupported tuple to confirm it is rejected
   without leaving stale results;
5. do not call the lite integration complete while any supported tuple falls back, freezes, or is
   absent.

For comparison result sets, follow [tools/comparison/README.md](../../../tools/comparison/README.md).
Its container command uses the isolated RTWT Warp SimData runtime; do not substitute the AeroNIM
base interpreter path or a retired in-repository post-processing tool.

## Fixed comparison view

`[comparison]` names pre-baked result sets and their `.npz` files. The current comparison callback
maps the logical selection to `resultSetOverride`; it does not perform live inference.

Changing comparison files is a coordinated data change:

- keep manifest names, callback behavior, stage delta field mappings, and baked filenames aligned;
- keep the frontend `FIXED_COMBO` in `trame-app/static/app_streamer.js` aligned with the baked
  comparison tuple, including when a new inference control or default affects result identity;
- preserve the signed-difference convention used by the visualization;
- regenerate with the same native result format consumed by the Kit-CAE 3.0 inference path;
- validate the fixed view in the browser after loading each result set.

Do not generalize this recipe to arbitrary result sets without updating the callback and frontend.

## Validate

Static manifest/schema validation:

```bash
tools/validate/rtdt-validate.sh \
  --manifest source/specializations/auto-aero/workflow/workflow.toml \
  --schemas RtwtInferenceAppStateAPI RtwtVizAppStateAPI
```

Add `--stage source/specializations/auto-aero/stages/Main.usda` when checking targets, variant sets,
result wiring, or colormap readouts. `Base.usda` is the authoring layer for the base scene, domain,
inference, and results; it is not the full validation scope. `Main.usda` composes the visualization
layers and is the correct static approximation of the application stage. Interpret any remaining
warnings against runtime-authored state.

## Resources

- [geometry-recipe.md](references/geometry-recipe.md) — exact Kit-CAE 3.0 geometry procedure.
- `source/specializations/auto-aero/workflow/workflow.toml` — active control/output registry.
- `skills/evals/` — deterministic Kit-hosted validator smoke fixtures.
