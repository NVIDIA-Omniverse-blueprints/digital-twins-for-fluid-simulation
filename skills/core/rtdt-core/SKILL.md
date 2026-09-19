---
name: rtdt-core
description: Shared foundation for Real-Time Digital Twins (RTDT) work. Use when starting or health-checking the standard or lite streaming stack, deciding whether a task needs a built Kit application, or reasoning about the current control and inference contracts. Read this before using rtdt-customize or rtdt-aero.
---

# RTDT Core

Use this skill as the operational and contract foundation for RTDT work. The repository combines a
workflow/controller layer, a specialization, USD stages, a browser UI, Kit-CAE 3.0 visualization,
and either live Triton inference (`standard`) or an offline result cache (`lite`). Some controller
interfaces are workflow-driven, but the shipped frontend and a few runtime paths still contain
auto-aero conventions; do not assume the application is fully specialization-neutral.

The supported build, container, and runtime host is Linux (Ubuntu 22.04 or 24.04). Do not infer
Windows or WSL support from cross-platform tooling in dependencies.

## Choose the execution mode

- **Static authoring or review:** inspect and edit TOML, USD text, Python, or documentation without
  starting Compose. A built checkout is required only for checks that import Kit/USD schemas.
- **Standard profile:** live Kit rendering plus AeroNIM/Triton inference. Use either two GPUs with
  at least 40 GB each or one GPU with more than 80 GB, and follow the NGC authentication requirements.
  On a one-GPU host, set `CUDA_DEVICE_KIT` and `CUDA_DEVICE_AERONIM` to the same host index (normally
  `0`); the `.env_template` defaults assume a two-GPU host.
- **Lite profile:** one-GPU rendering with a fixed pre-baked cache. It cannot synthesize a missing
  inference result.

Before a runtime launch, initialize the Kit-CAE submodule and Git LFS assets, copy `.env_template`
to `.env`, and select exactly one profile; `standard` and `lite` cannot run together because they
publish the same Kit streaming ports. Compose builds and packages the Kit application
inside `Dockerfile`; a separate host `./repo.sh build` is required only for host-side tests or
launches. Standard additionally requires a valid NGC API key and registry login.

Treat `.env` as secret-bearing. Do not print the fully resolved Compose model with
`docker compose config`, because it expands values such as `NGC_API_KEY`. Use
`docker compose --profile <name> config --quiet` for validation, or extract only a known-safe field
without emitting the full command output.

## Start, stop, and check the application

Run these commands from the repository root:

```bash
docker compose --profile standard up -d
docker compose --profile lite up -d
```

Stop the profile explicitly. When changing profiles, remove every service from the Compose project
before starting the other profile:

```bash
docker compose --profile standard down
docker compose --profile lite down
docker compose --profile '*' down
```

The first image build and Kit startup can take several minutes. Use the profile-aware preflight with
a bounded retry window:

```bash
skills/core/rtdt-core/scripts/check_readiness.sh --profile standard --wait-seconds 600
skills/core/rtdt-core/scripts/check_readiness.sh --profile lite --wait-seconds 600
```

The preflight does not parse `.env`. When `.env` changes the published web or proxy port, pass the
same value explicitly with `--web-port` or `--proxy-port` (or export the matching environment
variable before running it). The shipped standard Compose topology publishes Triton on host port
`8080`; use `--triton-port` only when a Compose override changes that host mapping. This preflight
validates the bundled local topology, not an AWS split-host or other remote-Triton deployment.

The preflight reports Compose services, the direct web endpoint, the launch proxy, and Triton/model
readiness where applicable. It does **not** prove that a browser established the WebRTC stream, that
the scene rendered correctly, or that a control round-trip succeeded. Verify those separately when
the task requires an end-to-end runtime claim.

For a blank scene or missing controls during startup:

1. Read `docker compose logs kit-lite` (or `kit` for standard). `app ready` can precede
   `RTX ready` by several minutes while shaders compile; a reachable web page is not renderer readiness.
2. Keep the browser open through initialization. Confirm the scene appears and the loading message
   gives way to controls, including velocity options, without a reload.
3. Change velocity and visualization mode; verify the rendered result changes, not just the selected
   button. If it fails, capture Kit logs, browser console errors, a screenshot, and OS/GPU/driver details
   before diagnosing. Compare a restart with retained caches to distinguish cold-start delay.

## Execution rules

- Run repository commands with the documented `./repo.sh` entry points. Code importing `pxr`,
  `omni.*`, or `carb` must execute in the built Kit application, commonly with
  `./repo.sh launch -n <app> -- --exec <script> --no-window`.
- Use `python` for pure-standard-library orchestration. Do not use a system interpreter for
  Kit-dependent code.
- A one-shot Kit script must flush its output, request application shutdown, and return a reliable
  exit status. A long-lived stream handler must never terminate the host application.
- The current request/response control API is transported through the browser's WebRTC messaging
  channel. Do not claim a direct external HTTP or Python control endpoint exists.

## Current contracts

Read [contracts.md](references/contracts.md) before changing controller behavior, output fields,
cache semantics, or inference integration. In particular:

- `get_control_manifest` is useful metadata, but the shipped frontend does not render arbitrary
  controls from it.
- Stage-authored result-selection APIs determine which inference outputs are requested.
- Kit-CAE 3.0 results declare native OmniSci field metadata, while RTDT stores immutable NanoVDB
  buffers in `omni.cae.core.cache` and reconstructs a `warp_simdata.Field` through `GetField` on
  demand. It does not author native USD array values.
- The AeroNIM base models retain their validated Warp version from `aeronim/requirements.txt`.
  RTWT's Warp 1.13 and Warp SimData dependencies are installed from `requirements-rtwt.txt` into
  an isolated model path. Do not merge these environments unless the upstream NIM supports the
  newer Warp runtime.
- Lite cache availability is enforced per control axis; it is not a list of guaranteed-valid tuples.

For workflow/schema/geometry authoring, continue with
[rtdt-customize](../rtdt-customize/SKILL.md). For the shipped wind tunnel, continue with
[rtdt-aero](../../auto-aero/rtdt-aero/SKILL.md).

## Resources

- [contracts.md](references/contracts.md) — control, output, cache, and inference boundaries.
- [check_readiness.sh](scripts/check_readiness.sh) — bounded profile-aware runtime preflight.
