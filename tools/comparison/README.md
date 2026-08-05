# comparison — bake the cached comparison view

`bake.py` produces the pre-baked result sets behind the UI's **Comparison** view. From one surrogate
cache entry (a `.npz` of NanoVDB grid buffers, as written by `omni.rtwt.inference`'s offline cache) it
writes two derived entries using the same NPZ/NanoVDB grid-buffer and extent convention, so the
native Warp SimData result bridge and Kit-CAE visualization can consume both directly:

- `mock_ground_truth.npz` — every field, perturbed by an injected policy function.
- `diff.npz` — only the requested signed `ground_truth − surrogate` fields plus the grid extents.

This is a **one-time maintainer tool**, not a runtime path. It needs Warp 1.13 and Warp SimData
(present in the AeroNIM container) and runs once to generate the shipped comparison cache. At runtime
these entries are ordinary cached fields: the normal native result bridge reads them, with no
bake-time perturbation or separate diff kernel in the application.

## Use-case-agnostic helper + specialization runner

`bake.py` carries no domain vocabulary: the spatial perturbation policy is supplied by the caller via a
`perturb_fn`. The automotive-aero specialization owns that policy and the run wiring in
[`source/specializations/auto-aero/tools/bake_comparison_view.py`](../../source/specializations/auto-aero/tools/bake_comparison_view.py),
which applies a wake-weighted perturbation and calls `bake.bake_comparison(...)`.

## Run it

Run the specialization's bake runner inside the AeroNIM container, writing into the offline cache
directory. The upstream AeroNIM models retain their validated Warp runtime, so the maintainer tool
must use the isolated RTWT packages at `/opt/rtwt-python`. The retained image exposes
`/usr/bin/python3`, not a `python` launcher:

```sh
docker compose --profile standard run --rm --entrypoint /usr/bin/python3 \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e RTWT_BAKE_CORE=/bake_core \
  -e RTWT_BAKE_IN=/out/9eae54bb9f680734.npz \
  -e RTWT_BAKE_OUT=/out \
  -v "$PWD/tools/comparison:/bake_core:ro" \
  -v "$PWD/source/specializations/auto-aero/tools:/bake_tools:ro" \
  -v "$PWD/source/specializations/auto-aero/data/cache:/out" \
  aeronim /bake_tools/bake_comparison_view.py
```

`RTWT_BAKE_IN` is the surrogate cache entry to perturb. The runner prints a report with the diff's
peak and RMS as a percentage of the field range; to retune the difference, rescale
`RTWT_BAKE_AMPLITUDE` (the diff is linear in amplitude, so one rescale converges).

## How the runtime uses the output

The `[comparison]` section of the workflow manifest
([`workflow.toml`](../../source/specializations/auto-aero/workflow/workflow.toml)) maps each result-set
name to its `.npz`:

```toml
[comparison.result_sets.ground_truth]
npz = "mock_ground_truth.npz"
[comparison.result_sets.diff]
npz = "diff.npz"
```

The `comparisonResultSet` control (`off` | `surrogate` | `ground_truth` | `diff`) selects which set is
shown; selecting one loads the matching `.npz` through the inference result-set override, the same path a
live result takes. `RTWT_UI_PANELS` controls whether the Comparison panel is shown (see the
[developer guide](../../docs/developer-guide.md#comparison-view-and-ui-panels)).
