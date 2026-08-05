# Core controller tests — fake-workflow fixture (home)

This directory is the home for the **behavioral fake-workflow test** that proves the
core/specialization boundary: the use-case-agnostic core drives a tiny *non-aero* workflow with no dependency on the
automotive-aero specialization.

The fixture — a minimal workflow manifest (controls / bindings / outputs unrelated to cars/aero,
including at least one non-voxel `data_format = vertex_array` output and one `custom:` widget), a
minimal stage, and a stub model adapter — plus the test that drives it through the core
`ManifestLoader` / `ControlRegistry` / `BindingExecutor`, is authored alongside the
workflow-manifest loader and binding engine. Authoring it here (rather than in the
specialization) keeps it shipping with `source/core/` into the future standalone repo.

Until then, the static **boundary guard** (`tools/ci/check_core_boundary.py`, wired into
`repo.toml [repo_build.post_build]` and `.github/workflows/boundary-guard.yml`) enforces the
no-core→specialization-dependency invariant.
