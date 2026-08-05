# RTDT validator smoke checks

This directory contains deterministic, Kit-hosted validator smoke fixtures for selected
manifest/schema/stage rules.

They are not cross-model agent evaluations and do not prove runtime streaming, visualization, cache
coverage, or inference quality.

## Validator smoke fixtures

The TOML cases under `prompts/` invoke `tools/validate/rtdt-validate.sh`. That wrapper launches the
built Kit application, so these checks require a built checkout, available schema plugins, and a
writable Packman cache (the launcher refreshes package metadata). They do not require Compose or a
browser.

```bash
python skills/evals/run_eval.py --list
python skills/evals/run_eval.py --eval 01 --prompt
python skills/evals/run_eval.py --eval 01 --validate
python skills/evals/run_eval.py --all --validate
```

The current smoke cases cover:

| ID | Scope |
|---|---|
| `01` | Shipped auto-aero manifest/schema baseline. |
| `02` | Unknown AppState attribute rejection. |
| `03` | Invalid `cache_values` role rejection. |
| `04` | Static cube fixture's schema/control/variant wiring. |

The cube case is not a runnable UI or CAE inference scenario.

## Adding a validator smoke

Add `prompts/NN_name.toml` with:

- `name`, `description`, and an agent-facing `prompt`;
- `[validate]` containing `manifest`, `schemas`, and optional `schema_plugins`, `stage`, `callbacks`,
  or `app`;
- `[expect]` containing `ok` and optional `error_contains`.

Use a fixture under `fixtures/` when an intentionally invalid input is required.

## What empirical agent evaluation would require

To claim that these skills help less capable models, run multiple models from the same clean
repository state on representative authoring tasks, grade their patches against hidden functional
checks, and record model/version, prompts, environment, repetitions, and failure modes. Validator
smokes are regression defenses only; do not present them as that evidence.
