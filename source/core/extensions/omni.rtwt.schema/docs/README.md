# RTWT USD Schema (omni.rtwt.schema)

The structural, use-case-agnostic USD schemas for the Real-Time Digital Twins core. These runtime-registered
(`skipCodeGeneration = true`) API schemas are shared by every workflow:

- `RtwtInferenceResultsAPI` — marks an `OmniSciDataset` whose paired
  `OmniSciFieldAPI:<name>` / `OmniSciArrayAPI:<name>` instances are supplied by inference. Its
  revision token makes publication of all fields on that dataset atomic.
- `RtwtInferenceAPI` / `RtwtInferenceCacheAPI` — mark an inference prim and its cache behavior.
- `RtwtResultFieldSelectionAPI:<wire-output>` — maps one model output to a target
  `OmniSciDataset` plus an `OmniSciFieldAPI` instance name.
- `RtwtTransformAPI` — declares slider-driven transforms (the generic, declaration-driven binding pattern).
- `RtwtModelAPI` — assigns the geometry-model identifier the surrogate consumes.

This is the native Kit-CAE 3 data path. It deliberately does not define a per-field prim or depend
on the retired Data Delegate / `CaeFieldArray` compatibility model.

The **domain-specific** AppState knob schemas (e.g. spoiler / rims / mirrors / velocity, viz modes)
are NOT here — they belong to a specialization (for the reference workflow,
`omni.rtwt.auto_aero.schema`).

> The `Rtwt` class prefix and `omni:rtwt:` attribute namespace are a frozen backward-compat
> contract (baked into shipped stages and cache sidecars); the core/specialization split moved only
> the *defining package*, never the class or attribute names.
