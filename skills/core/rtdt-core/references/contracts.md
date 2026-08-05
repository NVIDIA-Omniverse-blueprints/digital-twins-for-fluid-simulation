# RTDT current contracts

These are the observed contracts of the current repository, not promises of a fully generic future
architecture. Confirm implementation details in
`source/core/extensions/omni.rtwt.controller/python/` and
`source/core/extensions/omni.rtwt.inference/python/` before changing them.

## Control contract

The browser UI reaches these handlers through Kit livestream messaging:

| Call | Current behavior | Important limit |
|---|---|---|
| `get_control_manifest()` | Returns workflow knobs, readouts, views, and feature flags. | The shipped Trame UI is hand-authored and does not automatically create widgets from this response. |
| `get_state()` | Reads declared control attributes from the manifest's `app_state_prim` and keys them by the final namespace component. | Only controls declared in the workflow manifest are exposed. |
| `set_state(state)` | Writes recognized short keys and returns whether the AppState prim was available. | `true` does not mean every value was accepted. Unknown keys and lite-cache-disallowed values are logged and skipped; read state back when confirmation matters. |
| `get_available_options()` | Returns `enforced`, per-axis `options`, and `precaching_available`. | Per-axis membership is not proof that every Cartesian tuple has a cache entry. |
| `start_cache()` | Walks the Cartesian product of inference-role controls with `cache_values` and waits for visualization sync. | The active cache hash is derived from configured inference AppState schema attributes, so schema and manifest roles must remain aligned. |
| `stop_cache()` | Disables cache read-through and emits an idle signal. | It does not cancel an already-running pre-cache loop. |

State normally flows from an AppState attribute through the binding graph to USD variants,
attributes, relationships, materials, callbacks, or visualization state. A manifest control ID and
the schema attribute's short key should currently be identical: validation checks binding knob IDs,
while runtime state is keyed by schema short names.

The manifest prim paths are runtime configuration, not descriptive metadata. Controller state and
binding paths honor `[workflow].app_state_prim`; inference/cache controller lookups honor
`[workflow].inference_prim`. Both fall back to their documented `/World/...` defaults only when no
workflow registry supplies a path.

`get_control_manifest` is discovery metadata, not a guarantee that every manifest feature has a
generic frontend implementation. Camera selection and several readout conventions also retain
application-specific behavior.

## Workflow and binding boundary

The manifest loader understands `[workflow]`, `[controls.*]`, `[outputs.*]`, `[[readouts]]`,
`[[views]]`, and `[comparison]`. The currently dispatched binding kinds are:

`Variant`, `Attribute`, `ColormapDomain`, `Callback`, `Relationship`, `Visibility`, `Material`,
`Transform`, `Playback`, and `ViewportScale`.

The validator rejects unknown kinds, fields the chosen handler does not consume, missing
handler-required fields, and invalid knob cardinality. The executor only logs and drops an unknown
kind when invalid input bypasses validation. Callback bindings must resolve through the
specialization registry and return an iterable of `(prim_path, attribute_name, value)` writes.
Validation does not simulate every handler or prove visual correctness.

## Kit-CAE extension boundary

The application enables `omni.cae.bundle`. Extensions that directly import CAE modules must still
declare their direct dependencies; the inference extension currently needs `omni.cae.core`,
`omni.cae.simdata`, `omni.cae.usd_plugins`, and `omni.cae.viz` in addition to the RTDT schema.

`omni.cae.usd_plugins` owns the active file-format path. When code must import an arbitrary supported
asset into a stage, use the top-level
`from omni.cae.usd_plugins_importers import import_to_stage` helper. Do not depend on transitive
bundle activation to make direct imports accidentally work.

## Kit-CAE 3.0 data contract

Use the native OmniSci/USD-plugin path throughout new guidance:

- The inference domain is an `OmniSciDataset` with `OmniSciVtkImageDataAPI` and
  `omni:vtk:origin`, `omni:vtk:spacing`, `omni:vtk:minExtent`, and `omni:vtk:maxExtent`.
- The model surface is plugin-backed geometry. The auto-aero stage uses an `OmniSciDataset` with
  `OmniSciFileFormatArgsPythonAPI` and PLY payloads.
- A single result `OmniSciDataset` references the domain and applies `RtwtInferenceResultsAPI`.
  Every field pairs `OmniSciArrayAPI:<Field>` with `OmniSciFieldAPI:<Field>`.
- The result dataset must compose `OmniSciVtkImageDataAPI`, normally by referencing the inference
  domain. The RTWT cache result bridge requires every field to use association token `node`;
  it rejects unspecified, element, and cell associations.
- `omni:rtwt:inference_results:revision` identifies one atomic cache-backed result payload. RTDT
  stores immutable NanoVDB buffers in `omni.cae.core.cache`; the registered `GetField` command
  reconstructs a `warp_simdata.Field` on demand. The bridge does not author USD array values.
- Visualization field selection is authored as token arrays such as
  `cae:viz:field_selection:colors:fieldNames = ["Pressure"]`.

For planar slices, bind the `UnlitScalarColor` material from `cae/mdl/basic.mdl` with MDL
subIdentifier `UnlitScalarColor`.

## Inference wire and outputs

The Kit inference extension serializes the composed USD layer and inference prim path for the Triton
wrapper model named by its application setting. The wrapper model may call another Triton model, so
changing the upstream model can require coordinated wrapper/config changes even when the outer wire
stays stable.

The runtime output request is stage-authored:

1. Apply `RtwtResultFieldSelectionAPI:<wire-id>` to the inference prim.
2. Author exactly one `omni:rtwt:result_field_selection:<wire-id>:target` relationship to the result
   dataset.
3. Author `omni:rtwt:result_field_selection:<wire-id>:fieldName` with the destination field instance.
4. Keep the manifest `[outputs.<wire-id>]` entry synchronized. It is cross-check metadata, not the
   source of the runtime request.

The producer tensor name, wire ID, manifest declaration, result API instances, and visualization
field names must agree. The workflow validator can cross-check these only when a composed stage is
provided.

## Lite cache boundary

Lite mode skips Triton and loads pre-baked payloads. Cache identity includes the configured
inference AppState values, and each sidecar describes available axes. Adding or changing an
inference control, result field, geometry payload, domain, or producer format invalidates assumptions
behind the existing cache. Rebuild and verify every intended tuple before calling a lite integration
complete.
