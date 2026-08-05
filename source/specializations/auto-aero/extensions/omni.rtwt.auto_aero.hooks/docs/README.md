# omni.rtwt.auto_aero.hooks

Automotive-aero **specialization** callback adapters for the use-case-agnostic controller binding
engine.

A binding of kind `ColormapDomain` / `Callback` in the workflow manifest names a callback this
extension registers into `omni.rtwt.controller`'s `CallbackRegistry` at startup. A callback is a
**pure function** `f(control_state) -> [(prim_path, attribute, value), ...]` — it performs no Kit
calls and does no change-block reasoning; the engine applies the returned writes.

Currently provides:

- **`auto_aero.dynamic_pressure`** — the velocity → colormap/shader domain physics (velocity
  range `0.1..1.5v` on the legend, `0.0..1.5v` on the field shaders; pressure range `±½ρv²`).
  Referenced by the `velocity` control in `workflow/workflow.toml`.

This extension is part of the automotive-aero specialization: delete `source/specializations/`
and the core still builds and launches (it simply has no aero callbacks registered).
