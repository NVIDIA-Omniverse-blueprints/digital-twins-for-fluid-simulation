# Extending the Blueprint

This guide walks through the two most common customization scenarios: replacing the car model with a different geometry, and changing what configuration options are exposed to the user in the web UI. These two tasks are closely related — a new car with different configurable features typically requires both.

## Replacing the car model

Swapping in a different vehicle involves four areas: surface mesh files, the CFD dataset stage, the hero (visual) car stage, and the inference pre-cache list.

### Step 1 — Prepare surface mesh files

The AeroNIM inference server requires one surface mesh file per configuration variant. Mesh files must be in a format readable by `trimesh` (PLY, STL, OBJ, etc.).

Organize files under `data/` using a consistent naming scheme. The existing blueprint uses:

```
data/low_res/detailed_car_<N>/aero_suv_low.ply
```

where `N` encodes the active variant combination. Choose a scheme that reflects your own configuration axes. The exact directory structure is up to you — what matters is that each variant's `omni:rtwt:model:tag` attribute resolves unambiguously to one file under `RTWT_MODEL_ROOT`.

### Step 2 — Update `stages/layers/CarCFD.usda`

`CarCFD.usda` defines a `CaeDataSet` prim with nested variant sets. Each leaf variant sets two things:

1. `fileNames` on the `TrimeshFieldArrayClass` prim — the asset path to the surface mesh file (relative to the stage)
2. `omni:rtwt:model:tag` — a string identifying the mesh file relative to `RTWT_MODEL_ROOT`; this is what the AeroNIM `rtwt` model reads at inference time

For a car with two boolean options A and B the variant structure would look like:

```usda
def CaeDataSet "CarCFD" (
    prepend apiSchemas = ["CaeMeshAPI", "RtwtModelAPI"]
    variants = { string A = "On" }
    prepend variantSets = "A"
)
{
    rel cae:mesh:faceVertexCounts = <FaceCounts>
    rel cae:mesh:faceVertexIndices = <Faces>
    rel cae:mesh:points = <Points>

    def "TrimeshFieldArrayClass" { asset[] fileNames }

    variantSet "A" = {
        "On" (
            variants = { string B = "On" }
            prepend variantSets = "B"
        ) {
            variantSet "B" = {
                "On" {
                    over "TrimeshFieldArrayClass" {
                        asset[] fileNames = [@../../data/my_car/a_on_b_on.ply@]
                    }
                    string omni:rtwt:model:tag = "my_car/a_on_b_on.ply"
                }
                "Off" {
                    over "TrimeshFieldArrayClass" {
                        asset[] fileNames = [@../../data/my_car/a_on_b_off.ply@]
                    }
                    string omni:rtwt:model:tag = "my_car/a_on_b_off.ply"
                }
            }
        }
        "Off" (
            variants = { string B = "On" }
            prepend variantSets = "B"
        ) {
            variantSet "B" = {
                "On" {
                    over "TrimeshFieldArrayClass" {
                        asset[] fileNames = [@../../data/my_car/a_off_b_on.ply@]
                    }
                    string omni:rtwt:model:tag = "my_car/a_off_b_on.ply"
                }
                "Off" {
                    over "TrimeshFieldArrayClass" {
                        asset[] fileNames = [@../../data/my_car/a_off_b_off.ply@]
                    }
                    string omni:rtwt:model:tag = "my_car/a_off_b_off.ply"
                }
            }
        }
    }
}
```

> **Verify the mesh:** Open `CarCFD.usda` as a standalone stage in the Kit editor and add the `Faces` operator from kit-cae to the `CarCFD` prim. Switch variants to confirm each mesh file loads and looks correct before proceeding.

### Step 3 — Align CFD data with the scene

The surface mesh files have their own coordinate system that likely does not match the hero car model or the wind tunnel out of the box.

1. Open the full stage (`Main.usda`) in the editor app
2. Make `/World/CAE/Faces_CarCFD` visible temporarily
3. Adjust the xform on `/World/CAE` until the CFD mesh aligns with the hero car geometry — moving this single prim repositions all CAE prims together (domain, slices, streamlines, probes, volumes)
4. Once satisfied, save; the override lands in `Main.usda`
5. Use the `BoundingBox_Domain` wireframe as a spatial reference to reposition probes and slice plane prims within the domain

### Step 4 — Update the hero car stage

The hero (visual) car stage must have variant sets with the **same names and choices** as `CarCFD.usda`. `AppStateOperator` drives both with a single `SetVariantSelection()` call per variant set name — if the names do not match, the visual car will not update when the user changes a configuration option.

Replace or update `stages/layers/CarHero.usda` and the referenced geometry under `stages/layers/CarHero/` with the new visual car assets and matching variant structure.

### Step 5 — Update the inference pre-cache list

The `start_cache` handler in `web_api.py` pre-warms a hard-coded list of all state combinations. Update `_all_cache_states()` to reflect the new configuration axes and their values:

```python
def _all_cache_states() -> list[dict]:
    combos = []
    for velocity in range(25, 101, 25):
        for a in ("On", "Off"):
            for b in ("On", "Off"):
                combos.append({"velocity": float(velocity), "A": a, "B": b})
    return combos
```

If the `lite` Compose profile will be used with the new car, the pre-baked entries under [data/cache/](../data/cache/) must also be regenerated — any sidecar whose `app_state` references the old schema will be ignored, and combinations without a matching entry will be greyed out in the UI. See the "Regenerate the offline cache" step below.

---

## Changing the configuration options exposed in the web UI

The controls available in the web UI are driven by attributes on `/World/AppState`. These attributes are defined by two USD API schemas in `omni.rtwt.schema`:

- **`RtwtInferenceAppStateAPI`** — attributes that affect what data is computed. Changing any of these triggers a new inference call. Use this for parameters like vehicle geometry configuration or wind speed.
- **`RtwtVizAppStateAPI`** — attributes that affect only how existing data is visualized (viz mode, slice direction, etc.). Changing these re-renders without a new inference call and is therefore cheaper.

Adding a new control requires changes in four places. The example below adds a "Wing" option (On/Off) that selects a different geometry variant.

### Step 1 — Add the attribute to the schema

Open `source/extensions/omni.rtwt.schema/python/schemas/omniRtwt/schema.usda` and add the new attribute to `RtwtInferenceAppStateAPI` (since wing configuration affects the geometry used for inference):

```usda
class "RtwtInferenceAppStateAPI" (
    ...
) {
    ...
    uniform token omni:rtwt:app_state:wing = "On" (
        allowedTokens = ["On", "Off"]
        doc = "Wing configuration."
    )
}
```

> **Regenerate the schema:** After editing `schema.usda`, run `usdGenSchema` to regenerate the derived files. From the directory containing `schema.usda`:
>
> ```
> usdGenSchema schema.usda resources/
> ```
>
> This updates `generatedSchema.usda` and related files in `resources/`. The Kit extension will not pick up the new attribute until these files are regenerated.

### Step 2 — Set the default value on `/World/AppState`

Open `stages/Base.usda` and add the attribute with its default value to the `AppState` prim definition:

```usda
def Prim "AppState" (
    prepend apiSchemas = ["RtwtInferenceAppStateAPI", ...]
) {
    ...
    uniform token omni:rtwt:app_state:wing = "On"
}
```

### Step 3 — Handle the attribute in `AppStateOperator`

Open `source/extensions/omni.rtwt.controller/python/app_state.py` and read the new attribute in `exec()`, then propagate it to the relevant prims. For a geometry variant this means adding it to the variant selection block:

```python
wing = prim.GetAttribute("omni:rtwt:app_state:wing").Get() or "On"

with Sdf.ChangeBlock():
    for car_path in ("/World/CarHero", "/World/CarCFD"):
        if not (car_prim := stage.GetPrimAtPath(car_path)):
            continue
        vsets = car_prim.GetVariantSets()
        for set_name, value in (
            ("Spoiler", spoiler), ("Rims", rims), ("Mirrors", mirrors), ("Wing", wing)
        ):
            if vsets.HasVariantSet(set_name):
                vsets.GetVariantSet(set_name).SetVariantSelection(value)
```

Because `web_api.py` discovers AppState attributes from the USD schema registry at runtime, `get_state` and `set_state` will automatically include the new `wing` attribute — no changes to the messaging bridge are needed.

### Step 4 — Add the UI widget in the Trame app

Open `trame-app/app.py` and:

1. Add `'wing'` to `state.kit_bridge_keys` so it is synced bidirectionally with Kit:

```python
state.kit_bridge_keys = [
    'vizMode', 'vizField', 'sliceDirection', 'sliderValue',
    'spoiler', 'rims', 'mirrors', 'velocity', 'animatedStreaks',
    'wing',   # ← new
]
```

2. Add a setter function and default state:

```python
def set_wing(value):
    state.wing = value

# in reset_state():
state.wing = "On"
```

3. Add the UI widget inside the Settings card in the layout section. Each variant-style control follows a restriction pattern: a `<opt>_options` state key (populated on connect from Kit's `get_available_options` reply) is either `None` (any value allowed) or a list of allowed values; the `disabled` expression greys out buttons that are not in the list. This lets the `lite` Compose profile surface only combinations for which a pre-baked cache entry exists:

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

Buttons should update Trame state through `ui_set(...)`, which calls the
browser-side `window.RTWTControls` helper in `trame-app/static/app_streamer.js`.
That keeps discrete button controls on the same state bridge path as sliders and
switches: the browser state updates immediately, then `app_streamer.js` forwards
the changed `kit_bridge_keys` to Kit via `set_state`.

For the new option to participate in offline-cache restriction, also:

- Declare `state.wing_options = None` alongside the other `*_options` state keys
- Add `state.wing_options = opts.get('wing') or None` inside the `_apply_available_options` trigger handler

Continuous controls (like the velocity slider) use a different pattern — an index-bound slider (`step=1`, `v_if="<opt>_options && <opt>_options.length"`) whose ticks are labelled with the cached values, plus `@state.change` handlers that keep the index and the underlying float value in sync. Kit is authoritative for the list (see `get_available_options` and `_SUPPORTED_VELOCITIES` in [web_api.py](../source/extensions/omni.rtwt.controller/python/web_api.py)). See the velocity widget in [trame-app/app.py](../trame-app/app.py) for a worked example.

### Step 5 — Update the pre-cache list

Add the new axis to `_all_cache_states()` in `web_api.py` so all combinations get pre-warmed by the `start_cache` workflow:

```python
for wing in ("On", "Off"):
    combos.append({..., "wing": wing})
```

### Step 6 — Regenerate the offline cache (lite profile only)

If the `lite` Compose profile is in use, the pre-baked entries under [data/cache/](../data/cache/) must also cover the new option. Each entry is a `<cache_key>.npz` plus a `<cache_key>.json` sidecar that records the originating `RtwtInferenceAppStateAPI` values. The `get_available_options` handler scans these sidecars to decide which UI options to expose; a value with no matching sidecar will be greyed out for all users of the lite profile.

To regenerate:

1. On the host (not inside the container — the `data/cache/` bind mount has UID-mismatch issues), run the kit app with `--/exts/omni.rtwt.inference/offline_mode=true --/exts/omni.rtwt.inference/generate_if_missing=true` and a reachable Triton.
2. Drive the app through every combination you want available. On a cache miss, the operator calls Triton and writes the result back to `data/cache/`.
3. Commit the new `.npz` files (LFS-tracked) and `.json` sidecars (plain text, diffable).

Note that changing an attribute's name or value set leaves stale sidecars behind — they remain on disk but reference app-state keys the schema no longer defines. Delete the obsolete pairs when the schema changes.

### Removing an existing control

To remove a control (e.g. the existing Mirrors option):

1. Remove the attribute from the schema in `omni.rtwt.schema`
2. Remove the attribute from `/World/AppState` in `Base.usda`
3. Remove the variant selection logic for it in `AppStateOperator`
4. Remove the UI widget, state key, and `<opt>_options` entries (state declaration + `_apply_available_options` handler) from `trame-app/app.py`
5. Update `_all_cache_states()` to drop the axis
6. If the `lite` profile is in use, remove the now-stale offline cache entries under [data/cache/](../data/cache/), or regenerate (see Step 6 above)

The messaging bridge requires no changes in either case.
