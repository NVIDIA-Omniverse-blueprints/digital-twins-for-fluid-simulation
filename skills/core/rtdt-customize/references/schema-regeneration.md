# Regenerate RTDT codeless schemas

Run `./repo.sh build -r` first. The build prepares the Kit-CAE 3.0 OpenUSD 25.11 distribution and
the `repo_usd` Python dependencies used below. This repository does not register a root
`./repo.sh schema` command, so do not invent one. The verified generator is
`kit-cae/_build/target-deps/usd/release/bin/usdGenSchema`.

## Auto-aero AppState schema

Run this exact command from the repository root after editing the auto-aero `schema.usda`:

```bash
bash -lc '
set -euo pipefail
RTDT_USD_ROOT="$PWD/kit-cae/_build/target-deps/usd/release"
RTDT_SCHEMA_ROOT="$PWD/source/specializations/auto-aero/extensions/omni.rtwt.auto_aero.schema/python/schemas/omniRtwtAuto"
export USD_PYTHON_DEPS_DIR="${USD_PYTHON_DEPS_DIR:-}"
source "$RTDT_USD_ROOT/scripts/set_usd_env.sh" >/dev/null
export PYTHONPATH="$PWD/kit-cae/_build/repo_usd/packages${PYTHONPATH:+:$PYTHONPATH}"
"$PWD/kit-cae/_build/target-deps/python/bin/python3.12" \
  "$RTDT_USD_ROOT/bin/usdGenSchema" \
  "$RTDT_SCHEMA_ROOT/schema.usda" \
  "$RTDT_SCHEMA_ROOT/resources"
'
```

The warnings about missing `__init__.py`, `CMakeLists.txt`, and `module.cpp` are expected for these
`skipCodeGeneration = true` resource-only schemas. A nonzero exit status or missing generated files
is not expected.

## Core RTDT schema

Use the same command, changing only `RTDT_SCHEMA_ROOT` to:

```bash
RTDT_SCHEMA_ROOT="$PWD/source/core/extensions/omni.rtwt.schema/python/schemas/omniRtwt"
```

## Review and validation gate

Regeneration updates both `resources/generatedSchema.usda` and `resources/plugInfo.json`. Review
those files together with `schema.usda`; do not hand-edit one generated file to make a diff
disappear. Then rebuild and validate the affected workflow:

```bash
./repo.sh build -r
tools/validate/rtdt-validate.sh \
  --manifest source/specializations/auto-aero/workflow/workflow.toml \
  --schemas RtwtInferenceAppStateAPI RtwtVizAppStateAPI \
  --stage source/specializations/auto-aero/stages/Main.usda
```

Treat generator changes to schema type keys, property order, or metadata as reviewable output. Verify
that the built application registers every expected API schema before accepting them.
