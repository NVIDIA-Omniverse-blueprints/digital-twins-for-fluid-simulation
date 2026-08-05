# Auto-Aero — automotive-aerodynamics specialization

This subtree is the **reference specialization**: an automotive external-aerodynamics
("virtual wind tunnel") digital twin built on the use-case-agnostic
[Real-Time Digital Twins core](../../core/README.md). It is the worked example for *how to build a digital-twin
workflow on Real-Time Digital Twins* — and the test for the split: **delete this directory and the core still
builds** (enforced by `tools/ci/check_core_boundary.py`).

Contents:
- `apps/` — the leaf apps (`omni.rtwt.webrtc.kit`, `omni.rtwt.editor.kit`) that extend the
  `omni.rtwt` core base and point at this specialization's stage, offline cache, and workflow
  manifest. Their filenames and the `KIT_APP` default are frozen deployment contracts.
- `stages/`, `data/` — the car / wind-tunnel USD stages and the pre-baked inference cache served
  in offline (lite) mode. The CFD geometry is a plugin-backed `OmniSciDataset` whose variants select
  native PLY payloads; inference fields are published on one `OmniSciDataset` through Warp SimData.
  Mounted at the frozen runtime paths `/app/rtwt/{stages,data}`.
- `extensions/` — the aero AppState knob schema and optional callback adapters for derived state
  (e.g. the dynamic-pressure colormap policy).
- `workflow/` — the plain-text workflow manifest declaring this workflow's controls, knob→effect
  bindings, outputs, and visualization modes.

The DoMINO surrogate-model backend (`aeronim/`, at the repo root) is also part of this
specialization (tagged here, kept in place for its Triton/Docker build). It uses Warp 1.13 and
Warp SimData to encode the model outputs as NanoVDB buffers for the core's native Kit-CAE 3 result
bridge.
