# Developer Guide

## Overview

The Real-Time Wind Tunnel (RTWT) Blueprint is a reference implementation of a real-time CFD digital twin. It combines a physics AI inference server, an Omniverse Kit-based rendering engine, and a web front-end into a deployable system that lets users interactively explore aerodynamic simulation results in real time.

The blueprint is composed of three top-level components that run as Docker services:

- **AeroNIM** — a Triton-based inference server that wraps the DoMINO automotive aerodynamics NIM. A custom Triton Python model (`rtwt`) handles USD stage parsing, surface mesh loading, sampling grid construction, and Warp SimData NanoVDB conversion around the upstream AI model.
- **Kit application** — an NVIDIA Omniverse Kit application that acts as the rendering engine. It uses Kit-CAE 3's OmniSci/OpenUSD-plugin data model and Warp SimData visualization pipeline, communicates with AeroNIM for inference, and streams the rendered output to the web front-end via WebRTC.
- **Trame app** — a Python/Trame web front-end that renders the Kit stream inside a browser and provides the user-facing controls for modifying car configuration, visualization mode, and wind speed.

A fourth service, the **launch proxy**, is included in both Compose profiles and sits in front of Trame and Kit's signaling endpoint when the blueprint is accessed through a single HTTPS URL (for example a Brev secure link). Local users may instead open the Trame port directly. See [Launch Proxy](#launch-proxy-launch-proxy) below for details.

Two Docker Compose *profiles* determine how these services are deployed:

- **`standard`** — runs Kit, AeroNIM, Trame, and the launch proxy. Inference is computed on demand by AeroNIM. Requires either two GPUs with at least 40 GB each or one GPU with more than 80 GB, a custom AeroNIM image built from the NGC base image, and an NGC API key at runtime.
- **`lite`** — runs the Kit app (as `kit-lite`), Trame, and the launch proxy; AeroNIM is omitted. Inference results are served from a pre-baked on-disk cache under [source/specializations/auto-aero/data/cache/](../source/specializations/auto-aero/data/cache/). Useful for single-GPU machines or environments where an NGC key is not available.

The profile is selected via `COMPOSE_PROFILES` in `.env` (see [.env_template](../.env_template)) or `docker compose --profile <name> up`.

This guide is intended for developers who want to understand the codebase, extend the blueprint, or adapt it for a different use case. It assumes familiarity with NVIDIA Omniverse Kit, USD, and Python.

---

## Architecture

The three services communicate as follows:

```
Browser
  │  HTTP (Trame UI)             WebRTC (Kit stream + messaging)
  ▼                                        ▲
Trame app ──────────── Kit application ────┘
                             │
                        HTTP (Triton)
                             ▼
                          AeroNIM
                    (rtwt → DoMINO model)
```

For HTTPS launchable deployments, the optional launch proxy fronts both the Trame UI and Kit's signaling endpoint so the browser only needs one public URL:

```
Browser ──HTTPS──▶ launch-proxy ─┬──▶ web:5173        (Trame UI, /)
                                 └──▶ kit-stream:49100 (/sign_in)
        ──WebRTC media (UDP/TCP)──▶ Kit (direct, not proxied)
```

**Trame app** serves the browser UI and maintains a bidirectional state bridge with the Kit application over the existing WebRTC connection — no separate communication channel is needed. When the user changes a control, the new state is sent to Kit as a `set_state` message.

**Kit application** hosts the USD stage and the CAE visualization pipeline. Application state is represented as USD attributes on `/World/AppState`. The `AppStateOperator` reacts to any attribute change on that prim and delegates to the binding engine, which reads the workflow manifest (`workflow.toml`) and applies each control's bindings to the stage — variant selections, attribute writes, visibility, colormap domains, and inference parameters. When inference inputs change, the `InferenceOperator` serializes the root USD layer and sends it to AeroNIM.

**AeroNIM** receives the serialized USD layer, parses it to extract inference parameters (velocity, active geometry variant, sampling grid definition), and calls the upstream DoMINO model. Results are encoded as NanoVDB byte buffers with Warp SimData (velocity, velocity magnitude, pressure). The Kit application publishes them as fields on an `OmniSciDataset`; Kit-CAE visualization operators resolve those fields through the same Warp SimData path used for plugin-backed source data.

---

## Control Flow

This section traces the full path from a user interaction in the browser to updated visualization in the streamed viewport.

### 1. User interaction → Trame state change

The user moves a slider or clicks a button in the browser. Trame updates its local state (e.g. `velocity = 75.0`). The `app_streamer.js` listener detects the change in the `kit_bridge_keys` set and calls:

```js
window.KitStreamer.send('set_state', { state: { velocity: 75.0, ... } })
```

### 2. `set_state` → AppState prim

The `set_state` handler in `web_api.py` receives the state dict and writes each value to the corresponding attribute on `/World/AppState` inside a single `Sdf.ChangeBlock`:

```python
prim.GetAttribute("omni:rtwt:app_state:velocity").Set(75.0)
```

Attribute names are resolved dynamically from the USD schema registry so the handler stays in sync with schema changes automatically.

### 3. AppState prim dirty → AppStateOperator executes

The Kit-CAE operator framework detects that the `/World/AppState` prim is dirty and schedules `AppStateOperator.exec()`. The operator reads the control state, then delegates to the **binding engine**, which applies the bindings declared in `workflow.toml`. For the automotive-aero workflow those bindings produce:

- `Spoiler`, `Rims`, and `Mirrors` variant selections on `/World/CarHero` and `/World/CarCFD`
- `Mode` and `SliceDirection` variant selections on `/World/CAE`
- colormap domains — velocity range `[0.1, 1.5×v]`, pressure range `[−q, +q]` where `q = ½ × 1.225 × v²` (computed by a specialization callback)
- the velocity attribute on `/World/Inference`
- slider-driven transforms on prims with `RtwtTransformAPI`, the streamlines material swap, and timeline playback

The operator itself holds no aero-specific logic; every effect above comes from the manifest.

### 4. Inference prim dirty → InferenceOperator executes

The attribute write to `/World/Inference` makes that prim dirty, triggering `InferenceOperator.exec()`. The operator resolves results through these paths:

1. Computes a cache key by hashing the inference prim path, the sorted values of the configured `RtwtInferenceAppStateAPI` attributes, and the sorted requested output IDs, then truncating the SHA256 digest to 16 hex characters
2. **In-memory cache** — checks the shared process cache; returns immediately on a hit
3. **On-disk cache** (only when `offline_mode=true`) — looks for `<cache_key>.npz` under `offline_cache_dir`; on a hit, populates the in-memory cache and returns. On a miss with `generate_if_missing=false`, logs an error and returns without contacting Triton
4. **Triton** — serializes the root USD layer with `ExportToString()` and sends it to the Triton `rtwt` model via HTTP, along with `PRIM_PATH`, `BATCH_SIZE`, and `STENCIL_SIZE`. On success, results are written back to the on-disk cache if offline mode is enabled, alongside a plain-text `<cache_key>.json` sidecar recording the originating `app_state`

The `lite` Compose profile sets `offline_mode=true` and `generate_if_missing=false`, so only pre-baked entries are served and Triton is never contacted.
Because the cache key covers AppState values and requested outputs but not the model payload or
domain definition, regenerate changed model/domain data in a new empty staging cache; otherwise an
old file with the same key can be reused. See [README deployment modes](../README.md#deployment-modes).

### 5. AeroNIM: `rtwt` model executes

The `rtwt` Triton Python model:

1. Loads the received USD layer anonymously with `LoadNone` (payloads — wind tunnel, hero car — are never loaded server-side)
2. Reads inference parameters directly from the stage: `omni:rtwt:inference:velocity`, `omni:rtwt:model:tag` from `/World/CarCFD`, and the sampling grid definition from `/World/Domain`
3. Loads the surface mesh file identified by `model_tag` from disk (cached in memory across requests)
4. Constructs the regular 3D point cloud grid from the domain origin, spacing, and extents
5. Calls the upstream DoMINO `model` with mesh tensors, point cloud, velocity, batch size, and stencil size
6. Computes velocity magnitude; converts velocity, velocity magnitude, and pressure to NanoVDB buffers on GPU via Warp SimData
7. Returns the three NanoVDB byte arrays plus `EXTENT_MIN`/`EXTENT_MAX`

### 6. Results land in the Kit stage

`InferenceOperator` receives the response and:

1. Resolves each `RtwtResultFieldSelectionAPI:<wire-output>` to a target `OmniSciDataset` and an `OmniSciFieldAPI` instance name
2. Groups all outputs targeting the same dataset and stores their NanoVDB buffers in the shared `omni.cae.core` cache
3. Publishes one new `omni:rtwt:inference_results:revision` on the dataset, so downstream readers see either the complete previous result or the complete new result, never a partially updated field set

### 7. Visualization operators re-execute

Downstream Kit-CAE operators (streamlines, planar slices, volumes) that select fields from `/World/InferenceResults` detect the revision change and re-execute. The inference extension's registered SimData commands reconstruct the selected cached NanoVDB buffer as a `warp_simdata.Field`; `omni.cae.viz` then updates the rendered geometry or volume.

The live, offline-cache, and comparison-result paths all publish through this mechanism. There is no RTWT Data Delegate and no per-field child prim.

### 8. Updated frame streamed to browser

The Kit renderer produces a new frame incorporating the updated visualization. The WebRTC stream delivers it to the browser `<video>` element, completing the loop.

### State sync signal (Kit → Trame)

After operators finish executing, Kit can push a `state_sync_signal` back to Trame via the messaging bridge to correct any state that was clamped or modified server-side. `app_streamer.js` applies these values with a `_syncingFromKit` guard to prevent echo loops.

---

## Repository Structure

```
digital-twins-for-fluid-simulation/
├── kit-cae/                      # Git submodule — Kit CAE extensions (see below)
├── source/
│   ├── core/                     # Use-case-agnostic core (see source/core/README.md)
│   │   ├── apps/omni.rtwt.kit            # Core base app — shared deps/settings; no stage, cache, or workflow
│   │   └── extensions/
│   │       ├── omni.rtwt.controller      # Binding engine (reads the workflow manifest) + WebRTC web API
│   │       ├── omni.rtwt.inference       # InferenceOperator + cache + native Warp SimData result bridge
│   │       ├── omni.rtwt.schema          # Structural USD schemas (use-case-agnostic)
│   │       └── omni.rtwt.pip_prebundle   # Bundled pip dependencies (tritonclient)
│   └── specializations/
│       └── auto-aero/            # Automotive-aero specialization (see its README.md)
│           ├── apps/                     # Leaf apps: omni.rtwt.webrtc.kit, omni.rtwt.editor.kit
│           ├── stages/                   # USD stage files (see Stage Structure) + layers/
│           ├── data/                     # low_res/ surface meshes (LFS) + cache/ offline results (LFS)
│           ├── extensions/
│           │   ├── omni.rtwt.auto_aero.schema   # AppState knob schemas (the UI control surface)
│           │   └── omni.rtwt.auto_aero.hooks    # Specialization callbacks (e.g. dynamic-pressure colormap)
│           ├── workflow/workflow.toml    # Declarative control / binding / output manifest
│           └── examples/byo-geometry-cube       # Self-contained manifest+stage validation fixture
├── skills/                       # Agentic skills for customizing the blueprint (core / auto-aero)
├── tools/                        # validate (manifest validator), geometry (prepare_mesh), comparison (bake)
├── aeronim/                      # AeroNIM Triton model + container (part of the auto-aero specialization)
│   ├── Dockerfile.aeronim          # Extends DoMINO NIM image; overlays the rtwt model
│   ├── requirements.txt            # Dependencies kept compatible with the upstream AeroNIM models
│   ├── requirements-rtwt.txt       # Isolated RTWT runtime (Warp 1.13 and Warp SimData)
│   └── rtwt/                       # Custom Triton Python model
│       ├── config.pbtxt              # Triton model config (inputs/outputs)
│       └── 1/model.py                # Model implementation
├── trame-app/                    # Web front-end (app.py + static/app_streamer.js)
├── launch-proxy/                 # Optional nginx reverse proxy for HTTPS launchable deployments
├── scripts/                      # Container startup scripts
├── compose.yml                   # Docker Compose: kit, kit-lite, aeronim, web (profiles: standard | lite)
├── .env_template                 # Reference environment variables; copy to .env and edit
├── Dockerfile                    # Kit application container image
└── repo.toml                     # Repo tool configuration (build, format, test)
```

### `kit-cae` Submodule

`kit-cae` is a Git submodule pinned to the Kit-CAE 3.0 `main` line. Its active bundle supplies
`omni.cae.usd_plugins`, `omni.cae.core`, `omni.cae.simdata`, `omni.cae.viz`, and the supporting
schemas and UI extensions. The blueprint does not add Kit-CAE's `source/legacy_extensions` search
path or depend on its Data Delegate compatibility bundle.

The repository's `.gitmodules` file is the source of truth for the clone URL and update branch. A
normal submodule checkout is detached at the exact gitlink recorded by this repository even though
`git submodule update --remote kit-cae` follows `main`.

```sh
# Clone with submodules
git clone --recurse-submodules <repo-url>

# Or initialize after a plain clone
git submodule update --init --recursive

# Deliberately advance the gitlink to a newer commit from Kit-CAE main
git submodule update --remote kit-cae
```

The build selects the Kit SDK/kernel compatible with Kit-CAE 3.0. AeroNIM retains its validated
base dependencies from `aeronim/requirements.txt`, while `aeronim/requirements-rtwt.txt` installs
the matching RTWT inference dependencies into the model's isolated Python path.

---

## Key Components

### AeroNIM (`aeronim/`)

AeroNIM is a customized deployment of the [DoMINO Automotive Aerodynamics NIM](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/overview.html). The base NIM image provides the DoMINO AI model and its Triton model repository. This blueprint overlays a custom Triton Python-backend model named `rtwt` that acts as an orchestration wrapper.

The `rtwt` model's responsibilities:

- Receive the serialized USD layer from the Kit application and parse it to extract inference inputs without loading any visual assets (payloads are excluded via `LoadNone`)
- Resolve the active car surface mesh from `omni:rtwt:model:tag` and load it from `RTWT_MODEL_ROOT` (default `/opt/data`); mesh data is cached in memory across requests
- Build the regular 3D sampling grid from the domain prim's VTK image data attributes
- Call the upstream DoMINO `model` with mesh geometry, sampling grid, and wind velocity
- Convert raw float field arrays (velocity, pressure) to NanoVDB buffers on GPU via Warp SimData and return them to the Kit application

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `RTWT_MODEL_ROOT` | `/opt/data` | Root directory for surface mesh files |
| `CUDA_VISIBLE_DEVICES` | set by compose | GPU device for inference |
| `NGC_API_KEY` | — | Required by the AeroNIM runtime |

The AeroNIM image installs the exact Warp SimData build used by Kit-CAE 3 from public PyPI.

---

### Kit Application (`source/`)

The Kit application hosts the USD stage and CAE visualization pipeline. It runs as either `omni.rtwt.webrtc.kit` (production, streams to browser) or `omni.rtwt.editor.kit` (development, full Kit UI).

#### Extensions

**`omni.rtwt.schema`** (core)

Defines the use-case-agnostic USD API schemas the mechanisms rely on, with no knowledge of any domain: `RtwtInferenceResultsAPI`, `RtwtModelAPI`, `RtwtInferenceCacheAPI`, `RtwtInferenceAPI`, `RtwtResultFieldSelectionAPI`, `RtwtTransformAPI`, and `RtwtControlBindingAPI`. These do not change when you adapt the blueprint.

The **customization-surface** schemas — `RtwtInferenceAppStateAPI` and `RtwtVizAppStateAPI`, which define what the web UI can control — live in the specialization (`omni.rtwt.auto_aero.schema`), not here. Adding or removing an attribute there changes the available controls end-to-end. See [extending.md](extending.md).

**`omni.rtwt.inference`**

Implements `InferenceOperator`, a Kit-CAE operator that executes on prims with `RtwtInferenceAPI` applied. It also registers the `GetAvailableFields` and `GetField` command implementations that expose cache-backed result datasets through Warp SimData. Key Carb settings:

| Setting path | Default | Description |
|---|---|---|
| `/exts/omni.rtwt.inference/triton_http_url` | `localhost:8080` | AeroNIM Triton HTTP URL |
| `/exts/omni.rtwt.inference/triton_timeout_s` | `600` | Request timeout in seconds |
| `/exts/omni.rtwt.inference/triton_batch_size` | `128000` | Inference batch size |
| `/exts/omni.rtwt.inference/triton_stencil_size` | `1` | Stencil size |
| `/exts/omni.rtwt.inference/offline_mode` | `false` | Read/write results to an on-disk cache keyed by the inference cache key |
| `/exts/omni.rtwt.inference/generate_if_missing` | `true` | When `offline_mode=true`, whether a cache miss should fall through to Triton (`false` makes misses fatal) |
| `/exts/omni.rtwt.inference/offline_cache_dir` | *(unset)* | Directory for offline cache files. Set by the auto-aero leaf apps to `${app}/../rtwt/data/cache`; resolved via `carb.tokens` and lexically normalized (symlink-safe) |

The module also exposes `scan_offline_cache_options()`, a helper that reads the `*.json` sidecars in `offline_cache_dir` and reports which `RtwtInferenceAppStateAPI` attribute values are present. The web API uses this to restrict UI options when offline mode is authoritative (see `get_available_options` below).

**`omni.rtwt.controller`**

Two responsibilities:

1. **Binding engine** — `AppStateOperator` runs on the `/World/AppState` prim and is the single entry point for application-state changes. It holds no workflow-specific logic: it reads the control state and applies the bindings declared in the workflow manifest (`workflow.toml`). The engine supports a fixed set of binding kinds — `Variant`, `Attribute`, `Visibility`, `Relationship`, `Material`, `Transform`, `Playback`, `ViewportScale`, `ColormapDomain`, and `Callback` (an escape hatch into specialization hooks). See [Workflow manifest and the binding engine](#workflow-manifest-and-the-binding-engine).

2. **WebRTC messaging bridge** — registers request/signal handlers over `omni.kit.livestream.messaging`, reusing the existing WebRTC connection. Exposes the following to the web front-end:
   - `get_state` / `set_state` — read/write `/World/AppState` attributes
   - `set_view` — switch camera view
   - `get_colormap` — fetch colormap LUT + domain
   - `start_cache` / `stop_cache` — drive the pre-caching workflow (Triton-only)
   - `get_available_options` — report which inference-input values the runtime can serve. Always includes `velocity` — the set of wind speeds the backend supports (so the UI need not hardcode it). When the runtime is locked to the pre-baked cache (offline mode, no-generate), the `options` dict is narrowed and variant-axis keys (`spoiler`, `rims`, `mirrors`) are added. Also carries `enforced` (true iff restricted) and `precaching_available` (false iff enforced, since pre-caching requires Triton). The frontend pulls this once on connect and uses it to drive the velocity slider ticks, grey out unavailable UI options, and hide the CACHE card.

**`omni.rtwt.pip_prebundle`**

Bundles `tritonclient[http]` as a Kit extension so it is available at runtime inside the container without a separate pip install step.

---

### Workflow manifest and the binding engine

The specialization's `workflow/workflow.toml` is the readable source of truth for what the workflow
controls, outputs, and visualizes. The core controller loads it and drives its declared bindings.
Most control behavior is workflow-driven, although a few web and pre-cache paths retain shipped
auto-aero conventions such as `velocity` and `vizMode`.

Each `[controls.<name>]` entry maps a typed AppState attribute to one or more bindings:

| Field | Meaning |
|---|---|
| `schema_attr` | The `/World/AppState` attribute this control reads and writes |
| `role` | `inference` (part of the cache key — a change re-runs the model) or `visualization` (re-render only) |
| `widget`, `group` | How the control is presented in the UI |
| `values` / `bounds` | Allowed discrete values, or slider bounds |
| `cache_values` | Inference-role only: the per-axis list whose Cartesian product is the pre-cache grid |
| `bindings` | What the engine applies on change: `Variant`, `Attribute`, `Visibility`, `Relationship`, `Material`, `Transform`, `Playback`, `ViewportScale`, `ColormapDomain`, `Callback` |

The manifest also declares `[outputs.*]` — the model output-field registry naming each NanoVDB
tensor on the inference wire, its target `OmniSciDataset`, its `field_name`, and the visualization
modes that consume it — plus `[[readouts]]` (non-knob values such as colormap domains), `[[views]]`
(named cameras), and `[comparison]` (the cached comparison view). The repository validator checks
the manifest against the AppState schema and, when supplied a composed stage, cross-checks each
output against its `RtwtResultFieldSelectionAPI`, `OmniSciFieldAPI`, and `OmniSciArrayAPI`
declarations. Run it from the command line with `tools/validate/rtdt-validate.sh`.

**Reuse across use cases.** The core (`source/core/`) does not depend on any specialization —
deleting `source/specializations/auto-aero/` leaves it buildable, a boundary enforced by
`tools/ci/check_core_boundary.py`. Start a new digital-twin workflow as a specialization (a stage
bundle, an AppState schema, a workflow manifest, and an optional model adapter) under
`source/specializations/`. Most adaptations should not require core edits; any change to a remaining
shared convention must generalize the core rather than add a specialization dependency. See
[`source/core/README.md`](../source/core/README.md),
[`source/specializations/auto-aero/README.md`](../source/specializations/auto-aero/README.md), and
[extending.md](extending.md) for the step-by-step.

---

### Trame App (`trame-app/`)

The web front-end is a Python Trame server that renders a full-screen Vuetify3 UI. The Kit WebRTC stream is displayed in a `<video>` element behind the UI panels.

**State model:**

- `kit_bridge_keys` — bidirectional state keys synced between trame and Kit: `vizMode`, `vizField`, `sliceDirection`, `sliderValue`, `spoiler`, `rims`, `mirrors`, `velocity`, `animatedStreaks`, `comparisonResultSet`
- `kit_read_keys` — Kit→trame only, never sent back: `cmapVelocity`, `cmapPressure` (used to render live colormap bars with min/max labels)
- **Option lists** — `velocity_options`, `spoiler_options`, `mirrors_options`, `rims_options`. Populated once on connect from Kit's `get_available_options` reply. `velocity_options` is always a list (Kit reports its supported wind-speed set authoritatively, narrowed by the offline cache when enforced); the variant-axis keys are `None` when unrestricted and a list when the offline cache is authoritative.
- `precaching_available` — `true` by default; set to `false` when the runtime is locked to the offline cache. It gates the CACHE card and hides the too-brief inference snackbar in lite without changing `notification_active` or its control locking.
- `velocity_index` — an integer shim bound to the velocity slider (`step=1`, ticks labelled with `velocity_options`). A pair of `@state.change` handlers keeps `velocity_index` and `velocity` in sync. The slider itself is `v_if`-gated on `velocity_options.length` so it only renders after Kit has reported its supported values.

**`static/app_streamer.js`** — the JavaScript glue layer that:
- Loads `kit-streamer.iife.js` to initialize `window.KitStreamer`
- On connection, registers Kit signal handlers and pulls initial state from Kit (retries up to 20 times with 500 ms backoff)
- After the first successful `get_state`, calls `get_available_options` and applies the returned
  `*_options` / `precaching_available` values directly to Trame state
- Listens to trame state changes and forwards diffs of `kit_bridge_keys` to Kit via `set_state`
- Exposes `window.RTWTControls` for button-driven state changes, so discrete controls use the same client-side state bridge as sliders and switches
- Uses a `_syncingFromKit` guard to prevent echo loops when Kit pushes state corrections back

**Kit signals handled:**
- `state_sync_signal` — Kit→trame state correction (JS)
- `notification_signal` — drives notification state and control locking in both profiles; standard shows the banner, while lite hides only its presentation. `kind === 'transient'` auto-dismisses after 2 s (JS)
- `cache_state_signal` — cache progress updates (Python `@on_kit_signal`)

---

### Comparison view and UI panels

Alongside the live *Explore* experience, the blueprint can show a **cached comparison view**: for one pre-baked configuration it presents a surrogate prediction, a mock ground-truth, and their signed difference. The `comparisonResultSet` control (`off` | `surrogate` | `ground_truth` | `diff`) selects which set is shown. Selecting one writes the inference result-set override, which loads the matching pre-baked `.npz` from the offline cache through the normal inference path — there is no live model call. The comparison entries are produced offline by `tools/comparison/bake.py` (see [its README](../tools/comparison/README.md)); at runtime they are ordinary cached results.

`RTWT_UI_PANELS` (in `.env`) selects which panels the web UI shows:

| Value | Panels |
|---|---|
| `both` (default) | the live Explore panel and the cached Comparison panel |
| `explore` | the live Explore panel only |
| `compare` | the cached Comparison panel only |

---

### Launch Proxy (`launch-proxy/`)

An optional public-edge nginx reverse proxy that lets HTTPS-only deployments — Brev launchables, anything sitting behind a single TLS terminator — present **one** browser-facing URL for both the Trame UI and Kit's WebRTC signaling handshake. It is included in both `standard` and `lite` profiles, so `docker compose up` brings it up automatically; if you don't expose its host ports (`RTWT_HTTP_HOST_PORT`, `RTWT_HTTPS_HOST_PORT`) the rest of the stack works exactly as before.

What the proxy does:
- Listens on `:80` and `:443` inside the container; mapped to `RTWT_HTTP_HOST_PORT` (default `80`) and `RTWT_HTTPS_HOST_PORT` (default `443`) on the host
- Forwards `/sign_in` to `kit-stream:49100` — Kit's WebRTC signaling endpoint
- Forwards everything else to `web:5173` — the Trame UI
- Upgrades the WebSocket connection that `/sign_in` initiates (see the `$connection_upgrade` map in [nginx.conf](../launch-proxy/nginx.conf))
- Generates a self-signed TLS cert under `/etc/nginx/tls/` on first start via [entrypoint.sh](../launch-proxy/entrypoint.sh)

WebRTC media ports (`1024/udp`, `47995-48012/{tcp,udp}`, `49000-49007/{tcp,udp}`) are **not** proxied — they continue to be exposed directly by the `kit` service. WebRTC peer connections only need TLS for the signaling handshake; media flows over DTLS+SRTP regardless of whether the page was loaded over HTTP or HTTPS.

> **Why a network alias?** The proxy upstream block declares `server kit-stream:49100;`. The `kit` service has `aliases: [kit-stream]` on the `rtwt` network, and `kit-lite` inherits that alias via the `*kit-base` YAML anchor in [compose.yml](../compose.yml). One nginx config works for both profiles without any per-profile templating.

> **Production TLS:** The self-signed cert exists so local HTTPS testing works out of the box. In real launchable deployments a managed TLS terminator (Brev's secure link, an ALB, Caddy, etc.) is expected to sit in front of the proxy, talk plain HTTP to it on port 80, and present a trusted cert to the browser.

---

### Browser stream configuration

[kit-streamer/index.js](../kit-streamer/index.js)'s `resolveStreamConfig()` decides what `signalingServer`, `signalingPort`, `mediaServer`, and `forceWSS` values to hand to `@nvidia/omniverse-webrtc-streaming-library` when the page loads. The resolution order is the same for each knob — first match wins:

1. URL query parameter (`?server=`, `?signalingPort=`, `?mediaServer=`, `?forceWSS=`, `?publicIp=`) — useful for ad-hoc overrides without restarting anything
2. The `options` argument passed to `KitStreamer.init(kitServer, options)`
3. `state.kit_stream_config` from trame (populated from `RTWT_*` env vars at trame startup — see below)
4. Page-protocol-aware defaults

The defaults make the common cases work without configuration:

| Knob | HTTP / localhost default | HTTPS (non-localhost) default |
|---|---|---|
| `signalingServer` | `window.location.hostname` | `window.location.hostname` |
| `signalingPort` | `49100` | page port (i.e. `443`) — signaling rides the proxy |
| `mediaServer` | same as `signalingServer` | discovered public IP if available, else signaling server |
| `forceWSS` | `false` | `true` |

So a direct `http://host:80/` deployment connects to `host:49100` exactly like before. A proxied `https://host/` deployment connects to `host:443/sign_in` (which the proxy forwards to Kit) and points media at the host's public IP — necessary because the in-container hostname is typically a private IP that the browser cannot reach.

The trame side of the chain lives in [trame-app/app.py](../trame-app/app.py): on startup it copies the `RTWT_SIGNALING_SERVER`, `RTWT_SIGNALING_PORT`, `RTWT_MEDIA_SERVER`, `RTWT_FORCE_WSS`, and `RTWT_PUBLIC_IP` env vars (plus optional public-IP discovery) into `state.kit_stream_config`, which trame exposes to the browser as `window.trame.state.state.kit_stream_config`.

**Public-IP discovery.** When `RTWT_PUBLIC_IP` is not set and `RTWT_DISCOVER_PUBLIC_IP=1` (the default), trame issues a single `GET http://icanhazip.com` with a 1.5 s timeout at startup. Air-gapped or restricted-egress deployments should set `RTWT_DISCOVER_PUBLIC_IP=0` and either pin `RTWT_PUBLIC_IP` to the externally reachable IP or set `RTWT_MEDIA_SERVER` directly. Discovery happens once at server start, so a deployment whose public IP later changes needs the trame container restarted.

---

## Stage Structure

The RTWT scene is composed from a stack of USD sublayers. Each layer adds to or overrides the layers below it.

### Layer stack

```
Main.usda                    ← edit target; nearly empty; captures interactive overrides
  └── BaseCAEVariants.usda   ← adds Mode + SliceDirection variant sets to /World/CAE
        └── BaseCAE.usda     ← adds all CAE visualization operator prims
              └── Base.usda  ← base scene: AppState, cameras, payload-backed assets + CarCFD reference
```

**`Base.usda`** — establishes the scene: Z-up axis, 0.01 m/unit, 60 fps. Defines `/World/AppState` with default attribute values. Adds the wind tunnel environment and `/World/CarHero` as USD payloads so they can be selectively unloaded. `/World/CarCFD` references the plugin-backed `CarCFD.usda` layer; that layer selects a PLY payload for the active geometry variant. The AeroNIM server opens this stage with `LoadNone` and never loads the visual assets.

**`BaseCAE.usda`** — adds all CAE visualization operators under `/World/CAE`. Uses USD `over` prims as prototypes for the volume and planar-slice operators to avoid duplication — concrete operator prims reference the prototype and override only the OmniSci field-name selection and colormap.

**`BaseCAEVariants.usda`** — adds `Mode` and `SliceDirection` variant sets to `/World/CAE`. Each variant configures visibility and operator enable/disable state for the appropriate prims. The binding engine calls `SetVariantSelection()` and USD composition handles the rest — no conditional Python logic is needed.

**`Main.usda`** — intentionally kept nearly empty and used as the edit target when working in the Kit editor. Any interactive changes (moving a prim, tweaking a value) are captured here as USD overrides rather than modifying the underlying layer specs. This makes it straightforward to inspect what has changed and to selectively promote modifications to a lower layer when they are ready to be permanent.

### Key prims

**`/World/AppState`**

The single point of control for everything the web UI can change. Has two API schemas applied:

- `RtwtInferenceAppStateAPI` — attributes that affect what data is computed (velocity, car configuration); changes trigger new inference
- `RtwtVizAppStateAPI` — attributes that affect how data is visualized (viz mode, slice direction, animated streaks); changes trigger re-render only

> **Developer tip:** When testing in the editor without the web UI, edit the attributes on `/World/AppState` directly. `AppStateOperator` will react exactly as the web app would.

**`/World/CarCFD`**

An `OmniSciDataset` with `OmniSciFileFormatArgsPythonAPI` and `RtwtModelAPI` applied. Each leaf of the nested variant sets (Rims → Mirrors → Spoiler → Ride_Height) authors a PLY payload plus the matching model tag. Kit-CAE 3's Trimesh OpenUSD file-format plugin loads the selected PLY directly, while AeroNIM uses the model tag to find the same one of 16 pre-computed surface meshes under `source/specializations/auto-aero/data/low_res/`.

The encoding scheme for mesh file directory names:

```
variant_number = 500 + mirrors + 2×spoiler + 4×rims + 8×ride_height
  Mirrors:     On=0,       Off=1
  Spoiler:     Off=0,      On=1
  Rims:        Standard=0, Aero=1
  Ride_Height: Standard=0, High=1
```

The `omni:rtwt:model:tag` attribute (from `RtwtModelAPI`) resolves to the relative mesh file path for the active variant. The AeroNIM `rtwt` model reads this attribute from the serialized USD layer to load the correct geometry.

> **Developer tip:** Open `source/specializations/auto-aero/stages/layers/CarCFD.usda` as a standalone stage in the Kit editor and add the `Faces` operator from Kit-CAE to the `CarCFD` prim to verify that the native PLY payload and all selected variants resolve.

**`/World/Domain`**

An `OmniSciDataset` with `OmniSciVtkImageDataAPI` applied. Its `omni:vtk:origin`, `spacing`, `minExtent`, and `maxExtent` attributes define the regular sampling grid for inference. Refinement variants select the resolution; the default targets approximately 2 million sample points.

**`/World/InferenceResults`**

One `OmniSciDataset` that references `/World/Domain` to inherit the sampling grid definition. It applies `RtwtInferenceResultsAPI` and paired `OmniSciArrayAPI:<name>` / `OmniSciFieldAPI:<name>` instances for `Velocity`, `VelocityMagnitude`, `Pressure`, and the comparison delta fields. New results replace the dataset's revision atomically; fields are API instances on this prim, not child prims.

**`/World/Inference`**

The Kit-CAE operator prim for inference. Key API schemas:

| Schema | Instance | Role |
|---|---|---|
| `RtwtInferenceAPI` | — | `omni:rtwt:inference:velocity` — wind speed |
| `RtwtInferenceCacheAPI` | — | `useCache`, `preCaching` |
| `CaeVizDatasetSelectionAPI` | `:domain` | Points to `/World/Domain` |
| `CaeVizDatasetSelectionAPI` | `:model` | Points to `/World/CarCFD` |
| `RtwtResultFieldSelectionAPI` | `:nvdb_velocity` | Dataset: `/World/InferenceResults`; field: `Velocity` |
| `RtwtResultFieldSelectionAPI` | `:nvdb_velocity_magnitude` | Dataset: `/World/InferenceResults`; field: `VelocityMagnitude` |
| `RtwtResultFieldSelectionAPI` | `:nvdb_pressure` | Dataset: `/World/InferenceResults`; field: `Pressure` |

Only the result fields actually needed by the visualization pipeline are declared. Adding an `RtwtResultFieldSelectionAPI` instance is how you request an additional output from the model without transferring unused data. The target dataset must also declare matching `OmniSciFieldAPI` and `OmniSciArrayAPI` instances, and visualization operators select the field by its stable instance name.

**`/World/CAE`**

Parent of all CAE visualization prims. The xform on this prim is used to align the CFD data coordinate system with the hero car model.

| Prim | Type | Purpose |
|---|---|---|
| `BoundingBox_Domain` | `BasisCurves` | Invisible wireframe showing inference domain extents; ROI for slider transforms |
| `Faces_CarCFD` | `Mesh` | Renders CFD surface mesh via `CaeVizFacesAPI` |
| `Volume_VelocityMagnitude` | `Volume` | IndeX volume render of velocity magnitude |
| `Volume_Pressure` | `Volume` | IndeX volume render of pressure |
| `PlanarSlice_VelocityMagnitude` | `Mesh` | Planar slice colored by velocity magnitude |
| `PlanarSlice_Pressure` | `Mesh` | Planar slice colored by pressure |
| `Streamlines` | `BasisCurves` | Streamlines seeded from Probes; two materials: `ScalarColor` / `AnimatedStreaks` |
| `Probes` | `Xform` | Streamline seed positions; carry `RtwtTransformAPI` for slider-driven movement |
| `FlowSimulation_L0` | `Scope` | NVIDIA Flow simulation for the "Flow" visualization mode |

**`source/specializations/auto-aero/stages/layers/WindTunnel/windTunnelEnv.usd`**

A self-contained wind tunnel environment stage. All assets it references are co-located under the `WindTunnel/` directory. This stage can be referenced into any third-party stage independently.

---

## Extending the Blueprint

See [extending.md](extending.md) for step-by-step guides on:

- Replacing the car model with a different geometry
- Adding, changing, or removing configuration options exposed in the web UI

---

## Development Environment Setup

### Prerequisites

See the [README](../README.md) for hardware and software prerequisites.

### Compose profiles

The compose stack ships with two profiles, selected via `COMPOSE_PROFILES` in `.env` or `--profile` on the CLI:

| Profile | Services | Inference | Requirements |
|---|---|---|---|
| `standard` | `kit` + `aeronim` + `web` + `launch-proxy` | Live via Triton | 2 GPUs with at least 40 GB each, or 1 GPU with more than 80 GB; NGC API key; custom AeroNIM image |
| `lite` | `kit-lite` + `web` + `launch-proxy` | Offline, served from [data/cache/](../source/specializations/auto-aero/data/cache/) | 1 GPU |

Bring up the stack with:

```sh
docker compose --profile standard up    # full stack
docker compose --profile lite     up    # offline stack
```

`kit-lite` is defined as a YAML-anchor override of `kit` that only adds `RTWT_OFFLINE_MODE=true`. [scripts/startup.sh](../scripts/startup.sh) sees this and appends `--/exts/omni.rtwt.inference/offline_mode=true` plus `--/exts/omni.rtwt.inference/generate_if_missing=false` to the kit command line. Cache generation is disabled inside the container because the `data/cache/` bind mount runs into host/container UID mismatches; to extend the cache, run the kit app on the host with `offline_mode=true, generate_if_missing=true`.

### Live code changes without rebuilding

The Docker Compose configuration bind-mounts Python source directories directly into the running containers. For the following components, changes take effect on container restart without rebuilding the image:

| Component | Host path | Container path |
|---|---|---|
| Controller extension | `source/core/extensions/omni.rtwt.controller/python/` | `/app/exts/omni.rtwt.controller/omni/rtwt/controller/` |
| Inference extension | `source/core/extensions/omni.rtwt.inference/python/` | `/app/exts/omni.rtwt.inference/omni/rtwt/inference/` |
| Schema extension (core) | `source/core/extensions/omni.rtwt.schema/python/` | `/app/exts/omni.rtwt.schema/omni/rtwt/schema/` |
| AppState schema (aero) | `source/specializations/auto-aero/extensions/omni.rtwt.auto_aero.schema/python/` | `/app/exts/omni.rtwt.auto_aero.schema/omni/rtwt/auto_aero/schema/` |
| Specialization hooks | `source/specializations/auto-aero/extensions/omni.rtwt.auto_aero.hooks/python/` | `/app/exts/omni.rtwt.auto_aero.hooks/omni/rtwt/auto_aero/hooks/` |
| Workflow manifest | `source/specializations/auto-aero/workflow/` | `/app/rtwt/workflow/` |
| Triton `rtwt` model | `aeronim/rtwt/` | `/opt/triton/rtwt/` |
| Trame app | `trame-app/app.py`, `trame-app/static/app_streamer.js` | `/app/app.py`, `/app/static/app_streamer.js` |

To restart a single service after a code change:

```sh
docker compose restart kit       # Standard-profile Kit application
docker compose restart kit-lite  # Lite-profile Kit application
docker compose restart aeronim   # AeroNIM inference server
docker compose restart web       # Trame web front-end
```

### Using the editor app

To work with the full Kit editor instead of the streaming app, override `KIT_APP` when starting the Kit service:

```sh
KIT_APP=omni.rtwt.editor.kit docker compose up kit
```

### Testing application state without the web UI

Open the stage in the editor app and navigate to `/World/AppState`. Edit any attribute directly — `AppStateOperator` will react identically to how the web app would. This is the recommended workflow for testing new controls or visualizations before wiring them up to the UI.

### Stages and data volumes

Both the specialization's `stages/` and `data/` directories are mounted read-only into the Kit and
AeroNIM containers. Edit these files on the host, including with a host-launched USD editor, then
restart the affected services. A Kit editor launched through Compose can inspect and modify the
in-memory stage, but it cannot save changes back to these read-only mounts.
