# Real-Time Digital Twins — specialization-independent core

This subtree is the **specialization-independent core** of the Real-Time Digital Twins blueprint:
the reusable mechanisms shared by digital-twin workflows. It does not depend on a specific
specialization, although a few web and controller paths retain historical auto-aero conventions.
It is the future standalone repository.

Contents:
- `apps/omni.rtwt.kit` — the core base app (Kit-CAE 3 + the core extensions; no stage, cache, or
  workflow baked in — those come from a specialization). It uses the active
  `omni.cae.usd_plugins` / `omni.cae.simdata` / `omni.cae.viz` stack.
- `extensions/` — the structural USD schema, the USD-Controller binding engine + web API, the
  inference operator + offline cache + native Warp SimData result bridge, and the pip prebundle.

**Invariant: core must never depend on a specialization.** Deleting
`source/specializations/auto-aero/` leaves the core buildable. This is enforced by
`tools/ci/check_core_boundary.py` (run in the build and via GitHub Actions). Start a new
digital-twin demo by adding a specialization (a stage bundle + a workflow manifest + an optional
model adapter) under `source/specializations/`. Change core only when deliberately generalizing a
shared contract or one of the remaining cross-workflow conventions.

> Naming note: code identifiers keep the historical `rtwt` / `omni:rtwt:` brand — a frozen
> backward-compat contract that spans both the core mechanisms and the wind-tunnel specialization.
> The neutral `rtdt` brand is used only for new, isolated artifacts (the agentic `skills/` and
> top-level docs); the wholesale `rtwt`->`rtdt` code migration is deferred. Active scientific-data
> prims use the `OmniSci*` schemas supplied by CAE OpenUSD Plugins; legacy `CaeDataSet` and
> `CaeFieldArray` types are intentionally not part of this integration.
