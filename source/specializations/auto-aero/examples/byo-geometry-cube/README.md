# Bring your own geometry — the cube example

This is the smallest static, declarative manifest/schema/stage fixture for a geometry control. The
**Shape** value selects one of two cube variants through the same variant + binding mechanism used by
the auto-aero car, reduced to the minimum needed for validator coverage.

The fixture does not contain a frontend or runnable application. Its manifest control describes
backend wiring; it neither generates a UI widget nor proves streaming, rendering, or runtime control
behavior.

## Files

| File | Role |
|------|------|
| `schema/generatedSchema.usda`, `schema/plugInfo.json` | The example's own AppState schema — one knob, `omni:rtwt:app_state:shape` (`UnitCube` / `TallCube`). |
| `stage.usda` | `/World/AppState` (applies the schema) and `/World/Cube` with a `Shape` variant set holding the two geometries. |
| `workflow.toml` | One `[controls.shape]` control bound to the variant set. |

## The declarative pattern

1. **Schema attribute** — a typed attribute on an AppState schema is the source of truth for the
   value (`omni:rtwt:app_state:shape`, `allowedTokens = ["UnitCube", "TallCube"]`). In a real
   specialization this lives in the schema and is regenerated with `usdGenSchema`; here it is small
   enough to ship directly.
2. **Variant set on the geometry** — author a variant set on the prim (`/World/Cube`'s `Shape`),
   one variant per option, each defining (or referencing) that option's geometry.
3. **AppState default** — author the attribute's default on the app-state prim so the app starts in
   a known state (`/World/AppState`).
4. **Control + binding** — declare the control in `workflow.toml` and bind it to the variant set
   (`kind = "Variant"`, `variant_set = "Shape"`, `targets = ["/World/Cube"]`). This is declarative
   backend wiring; a user-visible control still needs a hand-authored frontend widget.
5. **Validate** — statically confirm the schema, manifest, and stage wiring (below).

## Validate it

```bash
tools/validate/rtdt-validate.sh \
  --manifest source/specializations/auto-aero/examples/byo-geometry-cube/workflow.toml \
  --schemas RtwtCubeAppStateAPI \
  --schema-plugins source/specializations/auto-aero/examples/byo-geometry-cube/schema \
  --stage source/specializations/auto-aero/examples/byo-geometry-cube/stage.usda
```

`--schema-plugins` puts the example's own schema on the path so the validator can resolve its knob;
`--stage` additionally confirms the `Shape` variant set exists on `/World/Cube`. Expect
`workflow valid`.

## What this does and does not do

This fixture statically validates one AppState attribute, one manifest control/binding, and one USD
variant set. It does not provide a UI, launch an application, stream a viewport, or run inference.
A real user-visible control requires explicit frontend work, and a live **inference** input also
requires model-target wiring plus a qualified model (see the inference wire in
`skills/core/rtdt-core/references/contracts.md`). The auto-aero car shows the full inference-wired
pattern; see `skills/auto-aero/rtdt-aero`.
