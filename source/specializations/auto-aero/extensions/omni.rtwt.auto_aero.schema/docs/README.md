# RTWT Auto-Aero USD Schema (omni.rtwt.auto_aero.schema)

The automotive-aero specialization's **AppState knob schemas** — the domain-specific control
vocabulary for the virtual wind tunnel:

- `RtwtInferenceAppStateAPI` — surrogate-input knobs: `spoiler`, `rims`, `mirrors`, `velocity`.
- `RtwtVizAppStateAPI` — visualization knobs: `vizMode`, `vizField`, `sliceDirection`,
  `animatedStreaks`, `playAnimation`, `sliderValue`, and the `roi` relationship.

These are runtime-registered (`skipCodeGeneration = true`). The class names and the
`omni:rtwt:app_state:*` attribute names are **preserved** from before the core/specialization split
— a frozen backward-compat contract baked into shipped stages, cache sidecars, and the web bridge —
so only the *defining plugin* moved here from `omni.rtwt.schema`.

The structural, use-case-agnostic schemas (inference results, inference, cache, transforms, model
tags, and the generic `RtwtControlBindingAPI`) live in the core `omni.rtwt.schema`. Deleting this
specialization leaves the core buildable.
