# Extending the Blueprint

This guide covers the two most common ways to adapt the blueprint: replacing the car with a different geometry, and changing which controls the web UI exposes. The two are related — a new vehicle with different configurable features usually needs both.

**How customization works.** The blueprint separates a use-case-agnostic **core** (`source/core/`) from the automotive-aero **specialization** (`source/specializations/auto-aero/`). You adapt the blueprint by editing the specialization — its USD stages, its AppState schema, and a plain-text **workflow manifest** (`workflow/workflow.toml`) — not by editing core operator code. A generic binding engine in the core reads the manifest and applies each control's effect to the stage, so adding a control is a manifest entry plus a schema attribute, not a new branch in Python.

> The `source/core/README.md` and `source/specializations/auto-aero/README.md` files describe the split in more detail. For an agent-assisted walkthrough of these same procedures, see the `skills/core/rtdt-customize` and `skills/auto-aero/rtdt-aero` skills.

## Replacing the car model

Swapping in a different vehicle touches four areas: the surface mesh files, the CFD dataset stage, the hero (visual) stage, and the pre-cache grid.

### Step 1 — Prepare the surface mesh files

The stock workflow uses one PLY surface mesh per configuration variant. Kit-CAE 3's Trimesh
file-format plugin supports STL, PLY, and 3MF payloads; the preparation tool intentionally has a
narrower contract: `tools/geometry/prepare_mesh.py` accepts binary STL and emits ASCII PLY. It does
the two chores that otherwise go wrong silently: it fits the mesh to the inference domain (in
meters) and prints a scaling notice, and it emits an indexed PLY plus a ready-to-paste,
plugin-backed `OmniSciDataset` recipe. Review its topology check; use `--close-holes` for simple
open boundary loops, and repair complex or non-manifold input externally before inference.

```sh
python tools/geometry/prepare_mesh.py \
  --in my_car.stl \
  --out source/specializations/auto-aero/data/my_car/a_on_b_on.ply \
  --asset-path ../../data/my_car/a_on_b_on.ply \
  --model-tag my_car/a_on_b_on.ply --prim CarCFD \
  --domain-min "<x y z>" --domain-max "<x y z>"
```

Organize the files under `source/specializations/auto-aero/data/` with a scheme that reflects your own configuration axes. The exact layout is up to you; what matters is that each variant's `omni:rtwt:model:tag` resolves to one file under `RTWT_MODEL_ROOT` (the mounted data directory). See [tools/geometry/README.md](../tools/geometry/README.md) for `--up-axis`, `--close-holes`, and the full option set.

### Step 2 — Update the CFD dataset stage

`source/specializations/auto-aero/stages/layers/CarCFD.usda` defines a plugin-backed
`OmniSciDataset` with nested variant sets. Apply `OmniSciFileFormatArgsPythonAPI` and
`RtwtModelAPI` once on the base prim. Each leaf variant then authors two things:

1. `payload` — the surface mesh asset path, resolved relative to `CarCFD.usda`; the Kit-CAE
   file-format plugin composes the mesh topology and array APIs from this asset
2. `omni:rtwt:model:tag` — the mesh path relative to `RTWT_MODEL_ROOT`; this is what the AeroNIM `rtwt` model reads at inference time

For a car with two boolean options A and B the variant structure looks like:

```usda
def OmniSciDataset "CarCFD" (
    prepend apiSchemas = ["OmniSciFileFormatArgsPythonAPI", "RtwtModelAPI"]
    variants = { string A = "On" }
    prepend variantSets = "A"
)
{
    variantSet "A" = {
        "On" (
            variants = { string B = "On" }
            prepend variantSets = "B"
        ) {
            variantSet "B" = {
                "On" (
                    prepend payload = @../../data/my_car/a_on_b_on.ply@
                ) {
                    string omni:rtwt:model:tag = "my_car/a_on_b_on.ply"
                }
                "Off" (
                    prepend payload = @../../data/my_car/a_on_b_off.ply@
                ) {
                    string omni:rtwt:model:tag = "my_car/a_on_b_off.ply"
                }
            }
        }
        "Off" (
            variants = { string B = "On" }
            prepend variantSets = "B"
        ) {
            variantSet "B" = {
                "On" (
                    prepend payload = @../../data/my_car/a_off_b_on.ply@
                ) {
                    string omni:rtwt:model:tag = "my_car/a_off_b_on.ply"
                }
                "Off" (
                    prepend payload = @../../data/my_car/a_off_b_off.ply@
                ) {
                    string omni:rtwt:model:tag = "my_car/a_off_b_off.ply"
                }
            }
        }
    }
}
```

Do not recreate the legacy `CaeMeshAPI`, `CaeFieldArray`, or Trimesh Data Delegate child prims.
Kit-CAE 3 reads the native payload through the CAE OpenUSD plugin and adapts the resulting
`OmniSciDataset` to Warp SimData for visualization.

> **Verify the mesh:** Open `CarCFD.usda` as a standalone stage in the Kit editor, apply the `Faces`
> operator from Kit-CAE to the `CarCFD` prim, and switch variants to confirm each mesh file loads
> and looks correct before proceeding.

### Step 3 — Align the CFD data with the scene

The surface mesh files have their own coordinate system, which likely does not match the hero car or the wind tunnel out of the box.

1. Open the full stage (`source/specializations/auto-aero/stages/Main.usda`) in the editor app.
2. Make `/World/CAE/Faces_CarCFD` visible temporarily.
3. Adjust the xform on `/World/CAE` until the CFD mesh aligns with the hero car geometry — moving this single prim repositions all CAE prims together (domain, slices, streamlines, probes, volumes), so the inference results and the visual car stay co-located.
4. Save; the override lands in `Main.usda`.
5. Use the `BoundingBox_Domain` wireframe as a spatial reference to reposition probes and slice-plane prims within the domain.

### Step 4 — Update the hero (visual) stage

The hero stage must declare variant sets with the **same names and choices** as `CarCFD.usda`. The binding engine drives both with one `SetVariantSelection()` per variant-set name (see the `Variant` bindings in the manifest), so mismatched names leave the visual car unchanged when the user switches an option.

Replace `source/specializations/auto-aero/stages/layers/CarHero.usda` and the geometry it references with the new visual assets and a matching variant structure.

### Step 5 — Update the pre-cache grid

The standard profile's in-memory pre-cache walk is the Cartesian product of the `cache_values` declared on inference-role controls in `workflow.toml` — for the stock car, 4 velocities × spoiler × rims × mirrors = 32 combinations. To change that walk, edit those `cache_values`; there is no hard-coded combination list. The lite profile is separate: its supported set is exactly the on-disk tuples you intentionally generate and verify. The shipped lite set contains eight tuples (four velocities × spoiler on/off, with mirrors On and rims Standard). See [Step 6](#step-6--regenerate-the-offline-cache-lite-profile-only) below.

---

## Changing the configuration options exposed in the web UI

The web UI's controls are declared in the workflow manifest and backed by typed attributes on `/World/AppState`. Two USD API schemas define those attributes:

- **`RtwtInferenceAppStateAPI`** — attributes that change what is computed (geometry configuration, wind speed). Changing one triggers a new inference.
- **`RtwtVizAppStateAPI`** — attributes that change only how existing results are drawn (viz mode, slice direction). Changing one re-renders without a new inference and is therefore cheaper.

Both live in the specialization's schema (`omni.rtwt.auto_aero.schema`). The core schema (`omni.rtwt.schema`) holds only use-case-agnostic mechanisms (inference result contracts, the inference cache, transforms, and the control-binding schema) and is not edited to add a control.

Adding a control touches four places. None of them is operator code. The example below adds a "Wing" option (On/Off) that selects a geometry variant.

### Step 1 — Add the attribute to the schema

Add the attribute to `RtwtInferenceAppStateAPI` (wing changes the geometry used for inference, so it is inference-role) in `source/specializations/auto-aero/extensions/omni.rtwt.auto_aero.schema/python/schemas/omniRtwtAuto/schema.usda`:

```usda
uniform token omni:rtwt:app_state:wing = "On" (
    allowedTokens = ["On", "Off"]
    doc = "Wing configuration."
)
```

> **Regenerate the schema:** first run `./repo.sh build -r`, then use the verified Kit-CAE 3
> OpenUSD 25.11 command in
> [schema-regeneration.md](../skills/core/rtdt-customize/references/schema-regeneration.md).
> This repository does not register a root `./repo.sh schema` command. Regeneration updates both
> `resources/generatedSchema.usda` and `resources/plugInfo.json`; review both generated files.

### Step 2 — Set the default on `/World/AppState`

Add the attribute and its default to the `AppState` prim in `source/specializations/auto-aero/stages/Base.usda`:

```usda
def Prim "AppState" (
    prepend apiSchemas = ["RtwtInferenceAppStateAPI", ...]
) {
    ...
    uniform token omni:rtwt:app_state:wing = "On"
}
```

### Step 3 — Declare the control in the manifest

Add a `[controls.wing]` entry to `source/specializations/auto-aero/workflow/workflow.toml`. A control maps a schema attribute to one or more **bindings** that the engine applies whenever the value changes:

```toml
[controls.wing]
schema_attr  = "omni:rtwt:app_state:wing"
role         = "inference"        # re-computes; use "visualization" for draw-only knobs
widget       = "toggle"
group        = "Geometry"
values       = ["On", "Off"]
cache_values = ["On", "Off"]      # inference-role only: joins the pre-cache product
bindings = [
  { kind = "Variant", knobs = ["wing"], targets = ["/World/CarHero", "/World/CarCFD"], variant_set = "Wing" },
]
```

`role` selects the cache behavior: an `inference` value is part of the cache key, so a change re-runs the model; a `visualization` value is not. `cache_values` (inference-role only) is the per-axis list whose Cartesian product forms the standard in-memory pre-cache walk. Adding an inference axis changes cache identity; if that axis will be exposed in lite, explicitly choose and rebake the supported disk tuples.

The `bindings` array is how a value reaches the stage. The available kinds:

| Kind | Effect |
|---|---|
| `Variant` | Select a variant on a `variant_set` of the target prims |
| `Attribute` | Set a USD `attribute` on the target prims |
| `Visibility` | Show or hide the target prims |
| `Relationship` | Point a relationship at a target |
| `Material` | Bind one of two materials |
| `Transform` | Apply a slider value to a region-of-interest transform |
| `Playback` | Start or stop timeline playback |
| `ViewportScale` | Set the render-resolution scale |
| `ColormapDomain` / `Callback` | Call a registered specialization hook for effects that need workflow-specific logic |

Most controls need only `Variant`, `Attribute`, or `Visibility`. `Callback` is the escape hatch for derived state — the stock workflow uses one for the dynamic-pressure colormap policy — and resolves to a function registered in `omni.rtwt.auto_aero.hooks`.

### Step 4 — Add the UI widget and browser mapping

The web UI is not yet generated from the manifest, so this is the one remaining coordinated
frontend edit. In `trame-app/app.py`:

1. Add `'wing'` to `state.kit_bridge_keys` so it is synced bidirectionally with Kit:

```python
state.kit_bridge_keys = [
    'vizMode', 'vizField', 'sliceDirection', 'sliderValue',
    'spoiler', 'rims', 'mirrors', 'velocity', 'animatedStreaks',
    'wing',   # ← new
]
```

2. Add a default in `reset_state()`:

```python
state.wing = "On"
```

Add the same default to `resetControlState()` in `trame-app/static/app_streamer.js`. If this control
changes the fixed comparison result, also add it to `FIXED_COMBO` and regenerate the comparison data.

3. Add the widget inside the Settings card. Each variant-style control follows a restriction pattern: a `<opt>_options` state key (populated on connect from Kit's `get_available_options` reply) is either `None` (any value allowed) or a list of allowed values; the `disabled` expression greys out buttons whose value is not in the list. This lets the `lite` profile surface only per-axis values present in cache sidecars:

```python
html.Div("Wing", classes="text-caption text-center mb-1")
with vuetify.VRow(dense=True, classes="mb-3"):
    for val in ["On", "Off"]:
        with vuetify.VCol():
            vuetify.VBtn(
                val,
                block=True,
                variant="outlined",
                color=(f"wing === '{val}' ? 'green-darken-2' : 'default'",),
                classes=(f"wing === '{val}' ? 'font-weight-bold' : ''",),
                disabled=(f"notification_active || cache_state === 'caching' || (wing_options && !wing_options.includes('{val}'))",),
                click=ui_set("wing", val),
            )
```

Buttons update Trame state through `ui_set(...)`, which calls the browser-side `window.RTWTControls` helper in `trame-app/static/app_streamer.js`. That keeps discrete button controls on the same state bridge as sliders and switches: the browser state updates immediately, then `app_streamer.js` forwards the changed `kit_bridge_keys` to Kit via `set_state`.

For the new option to participate in offline-cache restriction, also:

- Declare `state.wing_options = None` alongside the other `*_options` state keys.
- Add `setOpt('wing_options', opts.wing ?? null);` in
  `pullAvailableOptionsFromKit()` in `trame-app/static/app_streamer.js`, beside the existing
  `spoiler_options`, `mirrors_options`, and `rims_options` mappings. These are per-axis unions across
  sidecars, not proof that every cross-axis tuple exists.

Continuous controls (like the velocity slider) use a different pattern — an index-bound slider (`step=1`, `v_if="<opt>_options && <opt>_options.length"`) whose ticks are labelled with the available values, plus `@state.change` handlers that keep the index and the underlying float value in sync. Kit reports the supported value set authoritatively through `get_available_options`, so the UI does not hardcode it. See the velocity widget in [trame-app/app.py](../trame-app/app.py) for a worked example.

Because `web_api.py` discovers AppState attributes from the USD schema registry and reads the
manifest at runtime, Kit-side `get_state` and `set_state` include the new attribute automatically.
The hand-built frontend still needs the `kit_bridge_keys` entry above and, for a cache-restricted
inference control, the explicit browser-side option mapping.

### Step 5 — Validate the manifest

Check the manifest against the schema before launching:

```sh
tools/validate/rtdt-validate.sh \
  --manifest source/specializations/auto-aero/workflow/workflow.toml \
  --schemas RtwtInferenceAppStateAPI RtwtVizAppStateAPI \
  --stage source/specializations/auto-aero/stages/Main.usda
```

This command invokes the controller's validator implementation: every control's `schema_attr` must
exist on the AppState schema, `values`/`cache_values` must match the schema's `allowedTokens`,
`cache_values` is valid only on inference-role controls, and bindings must use supported semantics
and declared knobs. See [tools/validate/README.md](../tools/validate/README.md) for stage-level
checks and options.

### Step 6 — Regenerate the offline cache (lite profile only)

If the new option will be exposed in the `lite` profile, the pre-baked entries under `source/specializations/auto-aero/data/cache/` must cover every supported tuple containing it. Each entry is a `<cache_key>.npz` plus a `<cache_key>.json` sidecar recording the originating `RtwtInferenceAppStateAPI` values. The `get_available_options` handler scans these sidecars to decide which per-axis values to expose; it does not prove tuple completeness.

To regenerate, follow the exact host launch and sidecar/payload coverage check in
[README deployment modes](../README.md#deployment-modes), using these gates:

1. Create a new empty staging directory. The cache key does not include the model payload or domain, so baking into the tracked cache can silently reuse stale entries after those inputs change.
2. On the host (not inside the container — the Compose data mount is read-only and can also have UID-mismatch issues), run Kit with a reachable Triton and `--/exts/omni.rtwt.inference/offline_mode=true --/exts/omni.rtwt.inference/generate_if_missing=true --/exts/omni.rtwt.inference/offline_cache_dir=/absolute/path/to/empty/staging-cache`.
3. Drive every tuple you intend to support. Starting empty ensures each tuple calls Triton and writes a fresh pair.
4. Validate every staged pair in lite mode, then replace the tracked 16-hex-character tuple pairs as one curated set. Preserve or deliberately regenerate `mock_ground_truth.*` and `diff.*`.
5. Commit the approved `.npz` files (LFS-tracked) and `.json` sidecars (plain text, diffable).

Do not leave obsolete pairs after changing the schema, model, domain, outputs, or supported tuples. Stale sidecars can widen the per-axis options reported to lite users.

### Removing an existing control

Reverse the four places:

1. Remove the attribute from the schema in `omni.rtwt.auto_aero.schema` and regenerate.
2. Remove the attribute from `/World/AppState` in `Base.usda`.
3. Remove the `[controls.X]` block (and its `cache_values`) from `workflow.toml`.
4. Remove the widget, default, and `<opt>_options` entries from `trame-app/app.py`; remove its bridge,
   reset default, and option mapping from `trame-app/static/app_streamer.js`.
5. If it participated in `FIXED_COMBO`, remove it there and regenerate the comparison data.

If the `lite` profile is in use, replace the now-stale offline cache entries under `source/specializations/auto-aero/data/cache/`, or regenerate (see Step 6). No operator-code changes are needed in either direction.
