# rtdt-validate — workflow-manifest validator

Validate a workflow manifest (`workflow.toml`) against its USD AppState schema(s) from the command
line using the controller's validator implementation. This gives customization an
**edit → validate → precise error** loop instead of edit-and-launch-and-hope.

It runs the controller's own validator inside the app (`repo.sh launch -- --exec`), so it uses
**only what the app already ships** — no extra dependencies, and it works on any built checkout.
The launch loads the rtwt extensions and registers the AppState schemas, then validates and exits;
no renderer interaction is needed.

## Run it

```bash
# Validate the app's configured manifest:
tools/validate/rtdt-validate.sh

# Validate a specific (e.g. edited) manifest:
tools/validate/rtdt-validate.sh --manifest source/specializations/auto-aero/workflow/workflow.toml

# Also check a self-contained stage's target prims / variant sets:
tools/validate/rtdt-validate.sh --manifest path/to/workflow.toml --stage path/to/stage.usda
```

Options: `--schemas <Api...>` (AppState API names; defaults to the app's configured set),
`--schema-plugins <dir...>` (prepend schema resource directories to `PXR_PLUGINPATH_NAME`),
`--callbacks <name...>`, `--format text|json`, `--app <kit_app>` (defaults to the editor app).
Exit status: `0` valid, `1` validation errors, `2` launch/usage error.

## What it checks

**Static** (always; manifest + schema only): every control has an unambiguous schema/web mapping;
each `schema_attr` exists on the named AppState schema(s); `values`/`cache_values` match schema
`allowedTokens`; `cache_values` appears only on `role = "inference"` controls; and each binding has
a supported kind, only handler-supported fields, valid knob cardinality, declared control
references, and (with `--callbacks`) a registered callback.

**Stage** (add `--stage`): binding/output target prims exist and `Variant` bindings name a real
variant set; every output targets an `RtwtInferenceResultsAPI` `OmniSciDataset` with a composed
`OmniSciVtkImageDataAPI` grid contract and matching `OmniSciFieldAPI:<field_name>` and
`OmniSciArrayAPI:<field_name>` instances; the stage's
`RtwtResultFieldSelectionAPI:<wire-output>` target and `fieldName` agree with the manifest; and
colormap readouts resolve.

Stage checks need a **fully composed** stage. For auto-aero, `Base.usda` alone is incomplete; use
`--stage source/specializations/auto-aero/stages/Main.usda`. The cube fixture's `stage.usda` is
self-contained and can be validated directly.
