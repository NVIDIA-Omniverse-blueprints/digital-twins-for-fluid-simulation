# Workflow manifest reference

The loader in `source/core/extensions/omni.rtwt.controller/python/manifest.py` is the authority for
which keys are parsed. The validator checks selected schema and stage invariants; it is not a full
runtime simulator.

## `[workflow]`

| Key | Parsed meaning | Current caveat |
|---|---|---|
| `id` | Required workflow identifier. | A missing ID prevents loading. |
| `label`, `title` | Display metadata. | Presentation remains frontend-specific. |
| `app_state_prim` | AppState path, default `/World/AppState`. | Authoritative for controller state lookup and binding execution. |
| `inference_prim` | Inference path, default `/World/Inference`. | Authoritative for controller inference/cache lookup and validator output cross-checking. |
| `default_stage` | Parsed stage metadata. | Application startup settings remain authoritative for which stage opens. |

## `[controls.<id>]`

| Field | Meaning |
|---|---|
| `schema_attr` | Full AppState attribute name. It must exist on a configured applied AppState API. |
| `role` | `inference`, `visualization`, or `view`. Only inference controls belong in the pre-cache product. |
| `widget` | Frontend hint such as `toggle`, `slider`, or `imageTiles`; it does not create a widget. |
| `group`, `label`, `unit` | Presentation metadata. |
| `values` | Declared values; token/string values are checked against schema `allowedTokens`. |
| `bounds` | Numeric UI metadata such as `{ min, max, step }`. |
| `cache_values` | Values traversed by pre-cache. Valid only for `role = "inference"`. |
| `images` | Value-to-image metadata returned by the control manifest. |
| `visible_when` / `visibleWhen` | Frontend visibility expression metadata. |
| `bindings` | Effects evaluated when AppState changes. |

Keep `<id>` equal to the last namespace component of `schema_attr`. The binding graph validates and
tracks manifest IDs, while `get_state` and `set_state` currently expose schema short keys.

The AppState prim is authoritative for the runtime default; the control table has no parsed
`default` field.

## Bindings

Every binding declares `kind` and `knobs`; `when_expr` is a shared gate and is required for
`Playback` and `ViewportScale`. Every other field, including `targets`, is handler-specific. The
validator rejects unknown kinds, fields the selected handler does not consume, missing required
fields, and invalid knob cardinality. The executor only logs and drops an invalid binding if
validation was bypassed.

| Kind | Behavior | Required and optional fields beyond `kind`/`knobs` |
|---|---|---|
| `Variant` | Selects a variant on each target. | `targets`, `variant_set`; optional `selection_expr`, `when_expr` |
| `Attribute` | Writes the one knob value to an existing attribute. | `targets`, `attribute`; optional `when_expr` |
| `Relationship` | Replaces the named relationship target with the one knob value interpreted as a prim path. | `targets`, `attribute`; optional `when_expr` |
| `Visibility` | Makes targets visible when the one knob value is truthy, invisible otherwise. | `targets`; optional `when_expr` |
| `Material` | Chooses a material below each target using the one knob's Python truthiness. | `targets`; at least one of `material_on`/`material_off`; optional `when_expr` |
| `Transform` | Runs the repository's ROI slider transform helper. | `params.roi_rel` |
| `Callback` | Invokes a registered callback and applies its returned writes. | `callback`; optional `when_expr`; no `targets` |
| `ColormapDomain` | Uses the callback handler for a named specialization callback. | `callback`; optional `when_expr`; no `targets` |
| `Playback` | Plays while `when_expr` evaluates true; otherwise stops. | `when_expr` |
| `ViewportScale` | Chooses `params.on` or `params.off` from `when_expr`. | `params`; `when_expr` |

A binding must list at least one knob. `Attribute`, `Material`, `Relationship`, `Transform`, and
`Visibility` consume one value and therefore require exactly one knob. `Variant` may list multiple
knobs when `selection_expr` composes them; every `{control-id}` placeholder supports letters,
digits, `_`, `.`, `:`, and `-`, must name a declared control, and must also appear in `knobs`.
Callbacks and condition-driven handlers may list multiple state dependencies.

A callback must return an iterable of three-item writes:
`(prim_path, attribute_name, value)`. It should not author the stage directly while the executor is
inside its change block.

`Material` and `Visibility` use Python truthiness; non-empty tokens such as `"On"` and `"Off"` are
both true. Prefer a boolean control. For token-driven materials, mutually exclusive `when_expr`
bindings can each apply an explicit `material_on`. For token-driven visibility, use a `Variant` or a
`Callback` that authors both visible and invisible states; a false gate is a no-op and cannot hide a
previously visible target.

## Expressions

`selection_expr` replaces `{controlId}` placeholders with current values.

`when_expr` supports:

- `&&`, `||`, and parentheses;
- `==`;
- `in [...]` and `not in [...]`;
- bare tokens and control IDs.

Comparisons are string-wise. There is no general Python expression evaluation, quoting, arithmetic,
ordering comparison, or unary negation. A malformed expression is logged and evaluates false.

## `[outputs.<wire-id>]`

Parsed fields are `model_output`, `target`, `field_name`, `role`, `label`, `units`, `data_format`,
and `visualizations`.

These entries document and validate the wire; they do not choose runtime requests. The inference
prim's `RtwtResultFieldSelectionAPI:<wire-id>` instances choose the requested outputs. With a stage,
the validator cross-checks IDs, target relationships, destination `fieldName`, result dataset type,
`RtwtInferenceResultsAPI`, and paired OmniSci field/array APIs.

## `[[readouts]]`, `[[views]]`, and `[comparison]`

- A readout parses `key`, `type`, `label`, `field`, and `domainSource`/`domain_source`. The current
  web API has special behavior for `type = "colormap"`.
- A view parses `name`, `thumbnail`, and `onSelect`/`on_select`. Camera discovery and selection retain
  fixed runtime behavior.
- `[comparison]` parses `default_result_set` and
  `[comparison.result_sets.<name>].npz`. A specialization callback must map the selected logical name
  to the stage's result-set override.

## Validator coverage

Static validation checks schema attributes, token values, cache-role rules, binding knob references,
selection placeholders, and optionally callback registration. With `--stage`, it additionally checks
binding targets, variant sets, output/result wiring, and colormap readouts.

It does not prove:

- that the shipped frontend exposes the control;
- that a callback produces correct writes;
- that all handler-specific fields are meaningful;
- that lite cache tuples exist;
- that the WebRTC stream or visualization is correct;
- that model results are physically valid.
