---
name: rtdt-customize
description: Customize an RTDT workflow, AppState schema, USD stage, frontend control, or Kit-CAE 3.0 geometry/result wiring. Use when adding or changing controls, variants, bindings, output fields, visualization selections, or bring-your-own geometry. Read rtdt-core first; use rtdt-aero as the specialization-specific companion for the shipped wind tunnel.
---

# RTDT Customize

Read [rtdt-core](../rtdt-core/SKILL.md) before using this skill. Most workflow changes span four
surfaces: typed AppState schema, workflow manifest, USD stage, and the hand-built Trame frontend.
Changing only one surface is usually incomplete.

## Classify the change

- **Backend-only control:** schema + manifest + binding, used without a new shipped UI widget.
- **User-visible control:** backend wiring plus the matching Trame widget and bridged state key.
- **Visual-only geometry:** cosmetic USD composition and visibility/variant wiring; no new result.
- **Inference geometry:** plugin-backed PLY surface, inference target wiring, model compatibility,
  and cache consequences.
- **Output field:** producer wire, stage result selection, result dataset APIs, manifest metadata,
  and visualization selection must all agree.

## Authoring loop

1. Read the current schema, `workflow.toml`, stage, and frontend together.
2. Add or update the AppState attribute. Preserve its USD type, `allowedTokens`, and authored default;
   regenerate the specialization schema using the repository's
   [verified codeless-schema workflow](references/schema-regeneration.md).
3. Add or update `[controls.<id>]`. Keep the control ID equal to the schema attribute short key.
4. Author only binding kinds implemented by the controller. Use
   [manifest-reference.md](references/manifest-reference.md) for exact semantics.
5. Author the stage-side target: variant set, attribute, relationship, material, callback write, or
   Kit-CAE 3.0 dataset/field APIs.
6. For a visible control, update `trame-app/app.py`. The current UI does not generate widgets from
   `get_control_manifest`. If an inference control participates in lite-cache restrictions, also
   map its `<key>_options` in `pullAvailableOptionsFromKit()` in
   `trame-app/static/app_streamer.js`.
7. Validate the manifest/schema. Add a composed stage when checking targets, variants, outputs, or
   colormap readouts:

   ```bash
   tools/validate/rtdt-validate.sh \
     --manifest <workflow.toml> \
     --schemas <AppStateAPI...> \
     --stage <composed-stage.usda>
   ```

8. Run the smallest relevant unit/static checks, then use the appropriate Compose profile for
   runtime verification. A clean validator result is necessary but does not prove rendering,
   streaming, callback behavior, or model accuracy.

## Bring-your-own geometry

Use [geometry-and-inference.md](references/geometry-and-inference.md) for the Kit-CAE 3.0 pattern.
`tools/geometry/prepare_mesh.py` remains useful for converting, fitting, centering, repairing, and
writing the PLY surface. Treat its scaling notice as a required review item.

`prepare_mesh.py` emits the current Kit-CAE 3 plugin-backed recipe: an `OmniSciDataset` payload with
`OmniSciFileFormatArgsPythonAPI`, `RtwtModelAPI`, and `omni:rtwt:model:tag`. Its output is
ready-to-paste native USDA for a sibling model prim when the command supplies the required
`--model-tag` and a `--asset-path` relative to the layer that will receive it. For a nested variant
tree, apply the APIs once on the base dataset and move only the emitted `payload` and
`omni:rtwt:model:tag` opinions into each variant leaf.

The directory
`source/specializations/auto-aero/examples/byo-geometry-cube/` is a **static manifest/schema/stage
validator fixture**. It demonstrates control-to-variant wiring; it is not a runnable frontend,
streaming application, or CAE inference example.

## Output-field checklist

For every new field, verify all of the following:

- producer tensor and Triton configuration;
- `RtwtResultFieldSelectionAPI:<wire-id>` target and `fieldName`;
- paired `OmniSciArrayAPI:<Field>` and `OmniSciFieldAPI:<Field>` on the one result dataset;
- `[outputs.<wire-id>]` metadata;
- `cae:viz:field_selection:<role>:fieldNames` on each consumer;
- cache data and sidecars for lite mode.

Do not introduce a second result dataset merely to hold another field. Keep fields on the
`RtwtInferenceResultsAPI` dataset unless the runtime contract itself is deliberately redesigned.

## Resources

- [manifest-reference.md](references/manifest-reference.md) — parsed manifest fields and binding
  behavior.
- [schema-regeneration.md](references/schema-regeneration.md) — exact Kit/OpenUSD 25.11 codeless
  schema regeneration commands and review gate.
- [geometry-and-inference.md](references/geometry-and-inference.md) — Kit-CAE 3.0 geometry, domain,
  result, visualization, and cache contracts.
- [rtdt-aero](../../auto-aero/rtdt-aero/SKILL.md) — exact auto-aero files and geometry recipe.
