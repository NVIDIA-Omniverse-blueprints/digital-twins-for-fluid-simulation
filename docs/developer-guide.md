# Developer Guide

## Overview

The Real-Time Wind Tunnel (RTWT) Blueprint is a reference implementation of a real-time CFD digital twin. It combines a physics AI inference server, an Omniverse Kit-based rendering engine, and a web front-end into a deployable system that lets users interactively explore aerodynamic simulation results in real time.

The blueprint is composed of three top-level components that run as Docker services:

- **AeroNIM** — a Triton-based inference server that wraps the DoMINO automotive aerodynamics NIM. A custom Triton Python model (`rtwt`) handles USD stage parsing, surface mesh loading, sampling grid construction, and NanoVDB conversion around the upstream AI model.
- **Kit application** — an NVIDIA Omniverse Kit application that acts as the rendering engine. It uses CAE-specific extensions from the `kit-cae` submodule to drive a USD-based visualization pipeline, communicates with AeroNIM for inference, and streams the rendered output to the web front-end via WebRTC.
- **Trame app** — a Python/Trame web front-end that renders the Kit stream inside a browser and provides the user-facing controls for modifying car configuration, visualization mode, and wind speed.

An optional fourth service, the **launch proxy**, sits in front of Trame and Kit's signaling endpoint when the blueprint is deployed behind a single HTTPS URL (for example a Brev secure link). See [Launch Proxy](#launch-proxy-launch-proxy) below for details.

Two Docker Compose *profiles* determine how these services are deployed:

- **`standard`** — runs all three services. Inference is computed on demand by AeroNIM. Requires two GPUs (rendering and inference), a custom AeroNIM image built from the NGC base image, and an NGC API key at runtime.
- **`lite`** — runs the Kit app (as `kit-lite`) and the Trame app only; AeroNIM is omitted. Inference results are served from a pre-baked on-disk cache under [data/cache/](../data/cache/). Useful for single-GPU machines or environments where an NGC key is not available.

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

**Kit application** hosts the USD stage and the CAE visualization pipeline. Application state is represented as USD attributes on `/World/AppState`. The `AppStateOperator` reacts to any attribute change on that prim and fans out the change to the rest of the stage: car variant selections, visualization mode, colormap domains, and inference parameters. When inference inputs change, the `InferenceOperator` serializes the root USD layer and sends it to AeroNIM.

**AeroNIM** receives the serialized USD layer, parses it to extract inference parameters (velocity, active geometry variant, sampling grid definition), and calls the upstream DoMINO model. Results are returned as NanoVDB field arrays (velocity, velocity magnitude, pressure). The Kit application converts these into renderable volumes, slice planes, and streamlines.

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

The Kit-CAE operator framework detects that the `/World/AppState` prim is dirty and schedules `AppStateOperator.exec()`. The operator reads all state attributes and fans out changes in a single pass:

- Sets `Spoiler`, `Rims`, and `Mirrors` variant selections on `/World/CarHero` and `/World/CarCFD`
- Sets `Mode` and `SliceDirection` variant selections on `/World/CAE`
- Updates colormap domains: velocity range `[0.1, 1.5×v]`, pressure range `[−q, +q]` where `q = ½ × 1.225 × v²`
- Updates velocity attribute on `/World/Inference`
- Applies slider-driven transforms to all prims with `RtwtTransformAPI`
- Switches streamlines material and controls timeline playback

### 4. Inference prim dirty → InferenceOperator executes

The attribute write to `/World/Inference` makes that prim dirty, triggering `InferenceOperator.exec()`. The operator resolves results through three cache tiers:

1. Computes a cache key (SHA256 of all `RtwtInferenceAppStateAPI` attribute values, truncated to 16 hex chars) and the list of requested output names
2. **In-memory cache** — checks the shared process cache; returns immediately on a hit
3. **On-disk cache** (only when `offline_mode=true`) — looks for `<cache_key>.npz` under `offline_cache_dir`; on a hit, populates the in-memory cache and returns. On a miss with `generate_if_missing=false`, logs an error and returns without contacting Triton
4. **Triton** — serializes the root USD layer with `ExportToString()` and sends it to the Triton `rtwt` model via HTTP, along with `PRIM_PATH`, `BATCH_SIZE`, and `STENCIL_SIZE`. On success, results are written back to the on-disk cache if offline mode is enabled, alongside a plain-text `<cache_key>.json` sidecar recording the originating `app_state`

The `lite` Compose profile sets `offline_mode=true` and `generate_if_missing=false`, so only pre-baked entries are served and Triton is never contacted.

### 5. AeroNIM: `rtwt` model executes

The `rtwt` Triton Python model:

1. Loads the received USD layer anonymously with `LoadNone` (payloads — wind tunnel, hero car — are never loaded server-side)
2. Reads inference parameters directly from the stage: `omni:rtwt:inference:velocity`, `omni:rtwt:model:tag` from `/World/CarCFD`, and the sampling grid definition from `/World/Domain`
3. Loads the surface mesh file identified by `model_tag` from disk (cached in memory across requests)
4. Constructs the regular 3D point cloud grid from the domain origin, spacing, and extents
5. Calls the upstream DoMINO `model` with mesh tensors, point cloud, velocity, batch size, and stencil size
6. Computes velocity magnitude; converts velocity, velocity magnitude, and pressure to NanoVDB buffers on GPU via Warp
7. Returns the three NanoVDB byte arrays plus `EXTENT_MIN`/`EXTENT_MAX`

### 6. Results land in the Kit stage

`InferenceOperator` receives the response and for each result field:

1. Stores the numpy array in the shared cache under a new unique key
2. Calls `PredictedFieldDelegate.set_tag(target_prim, new_key)` — this writes the cache key to the `omni:rtwt:field_array:tag` attribute on the target `CaeFieldArray` prim (e.g. `/World/InferenceResults/Velocity`)
3. The attribute write makes the field array prim dirty

### 7. Visualization operators re-execute

Downstream Kit-CAE operators (streamlines, slice planes, volumes) that read from `InferenceResults` field array prims detect the dirty state and re-execute. Each operator:

- Calls `PredictedFieldDelegate` to fetch the numpy array from cache using the tag attribute as key
- Updates the rendered geometry or texture (streamline curves, slice plane dynamic textures, IndeX volume data)

### 8. Updated frame streamed to browser

The Kit renderer produces a new frame incorporating the updated visualization. The WebRTC stream delivers it to the browser `<video>` element, completing the loop.

### State sync signal (Kit → Trame)

After operators finish executing, Kit can push a `state_sync_signal` back to Trame via the messaging bridge to correct any state that was clamped or modified server-side. `app_streamer.js` applies these values with a `_syncingFromKit` guard to prevent echo loops.

---

## Repository Structure

```
digital-twins-for-fluid-simulation/
├── kit-cae/                  # Git submodule — Kit CAE extensions (see below)
├── source/
│   ├── apps/                 # Kit application descriptors (.kit files)
│   │   ├── omni.rtwt.kit               # Base RTWT app — not launched directly; shared deps and settings
│   │   ├── omni.rtwt.webrtc.kit        # WebRTC streaming variant (extends omni.rtwt.kit)
│   │   └── omni.rtwt.editor.kit        # Full editor variant for authoring (extends omni.rtwt.kit)
│   └── extensions/           # Blueprint-specific Kit extensions
│       ├── omni.rtwt.controller        # AppStateOperator + WebRTC messaging bridge
│       ├── omni.rtwt.delegate          # Kit-CAE data delegate for inference result field arrays
│       ├── omni.rtwt.inference         # InferenceOperator — communicates with AeroNIM
│       ├── omni.rtwt.schema            # USD schemas specific to RTWT
│       └── omni.rtwt.pip_prebundle     # Bundled pip dependencies (tritonclient)
├── stages/                   # USD stage files (see Stage Structure)
│   ├── Main.usda               # Edit target layer — intentionally nearly empty
│   ├── BaseCAEVariants.usda    # Adds Mode / SliceDirection variant sets to /World/CAE
│   ├── BaseCAE.usda            # Adds CAE visualization operator prims
│   ├── Base.usda               # Base scene: AppState prim, wind tunnel + car payloads
│   └── layers/                 # Reusable sublayers (cameras, cars, colormaps, wind tunnel)
├── aeronim/                  # AeroNIM Triton model and container
│   ├── Dockerfile.aeronim      # Extends DoMINO NIM image; overlays rtwt model
│   ├── requirements.txt        # Additional Python deps (warp, trimesh, usd-core)
│   └── rtwt/                   # Custom Triton Python model
│       ├── config.pbtxt          # Triton model config (inputs/outputs)
│       └── 1/model.py            # Model implementation
├── trame-app/                # Web front-end
│   ├── app.py                  # Trame server — UI definition and Kit state bridge
│   └── static/                 # Static assets: camera thumbnails, rim images, app_streamer.js
├── launch-proxy/             # Optional nginx reverse proxy for HTTPS launchable deployments
│   ├── Dockerfile              # nginx:alpine + openssl for self-signed cert generation
│   ├── entrypoint.sh           # Generates the cert on first start, then execs nginx
│   └── nginx.conf              # `/` → web:5173, `/sign_in` → kit-stream:49100, ws upgrade
├── data/                     # Surface mesh files for all car variants (one per configuration)
│   ├── low_res/                # Surface meshes per variant (LFS-tracked)
│   └── cache/                  # Pre-baked offline inference results: <key>.npz (LFS) + <key>.json sidecar
├── scripts/                  # Container startup scripts
├── compose.yml               # Docker Compose: kit, kit-lite, aeronim, web services (profiles: standard | lite)
├── .env_template             # Reference environment variables; copy to .env and edit
├── Dockerfile                # Kit application container image
└── repo.toml                 # Repo tool configuration (build, format, test)
```

### `kit-cae` Submodule

`kit-cae` is a Git submodule providing the reusable CAE extensions (`omni.cae.viz`, `omni.cae.data`, `omni.cae.schema`) that this blueprint builds on. The build process handles building and packaging these extensions as part of the overall blueprint build.

```sh
# Clone with submodules
git clone --recurse-submodules <repo-url>

# Or initialize after a plain clone
git submodule update --init --recursive

# Update kit-cae to a newer commit
git submodule update --remote kit-cae
git add kit-cae && git commit -m "Update kit-cae submodule"
```

---

## Key Components

### AeroNIM (`aeronim/`)

AeroNIM is a customized deployment of the [DoMINO Automotive Aerodynamics NIM](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/overview.html). The base NIM image provides the DoMINO AI model and its Triton model repository. This blueprint overlays a custom Triton Python-backend model named `rtwt` that acts as an orchestration wrapper.

The `rtwt` model's responsibilities:

- Receive the serialized USD layer from the Kit application and parse it to extract inference inputs without loading any visual assets (payloads are excluded via `LoadNone`)
- Resolve the active car surface mesh from `omni:rtwt:model:tag` and load it from `RTWT_MODEL_ROOT` (default `/opt/data`); mesh data is cached in memory across requests
- Build the regular 3D sampling grid from the domain prim's VTK image data attributes
- Call the upstream DoMINO `model` with mesh geometry, sampling grid, and wind velocity
- Convert raw float field arrays (velocity, pressure) to NanoVDB buffers on GPU via Warp and return them to the Kit application

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `RTWT_MODEL_ROOT` | `/opt/data` | Root directory for surface mesh files |
| `CUDA_VISIBLE_DEVICES` | set by compose | GPU device for inference |
| `NGC_API_KEY` | — | Required by the AeroNIM runtime |

---

### Kit Application (`source/`)

The Kit application hosts the USD stage and CAE visualization pipeline. It runs as either `omni.rtwt.webrtc.kit` (production, streams to browser) or `omni.rtwt.editor.kit` (development, full Kit UI).

#### Extensions

**`omni.rtwt.schema`**

Defines USD API schemas specific to this blueprint. There are two categories:

- **Stable schemas** — infrastructure schemas not expected to change: `RtwtFieldArrayAPI`, `RtwtModelAPI`, `RtwtInferenceCacheAPI`, `RtwtResultFieldSelectionAPI`, `RtwtTransformAPI`
- **Customization-surface schemas** — schemas to modify when adapting the blueprint: `RtwtInferenceAppStateAPI` and `RtwtVizAppStateAPI` define what the web UI can control; adding or removing attributes here changes the available controls end-to-end

**`omni.rtwt.inference`**

Implements `InferenceOperator`, a Kit-CAE operator that executes on prims with `RtwtInferenceAPI` applied. Key Carb settings:

| Setting path | Default | Description |
|---|---|---|
| `/exts/omni.rtwt.inference/triton_http_url` | `localhost:8080` | AeroNIM Triton HTTP URL |
| `/exts/omni.rtwt.inference/triton_timeout_s` | `600` | Request timeout in seconds |
| `/exts/omni.rtwt.inference/triton_batch_size` | `128000` | Inference batch size |
| `/exts/omni.rtwt.inference/triton_stencil_size` | `1` | Stencil size |
| `/exts/omni.rtwt.inference/offline_mode` | `false` | Read/write results to an on-disk cache keyed by the inference cache key |
| `/exts/omni.rtwt.inference/generate_if_missing` | `true` | When `offline_mode=true`, whether a cache miss should fall through to Triton (`false` makes misses fatal) |
| `/exts/omni.rtwt.inference/offline_cache_dir` | *(unset)* | Directory for offline cache files. Defaulted by [omni.rtwt.kit](../source/apps/omni.rtwt.kit) to `${app}/../rtwt/data/cache`; resolved via `carb.tokens` and lexically normalized (symlink-safe) |

The module also exposes `scan_offline_cache_options()`, a helper that reads the `*.json` sidecars in `offline_cache_dir` and reports which `RtwtInferenceAppStateAPI` attribute values are present. The web API uses this to restrict UI options when offline mode is authoritative (see `get_available_options` below).

**`omni.rtwt.delegate`**

Implements a Kit-CAE data delegate for `CaeFieldArray` prims with `RtwtFieldArrayAPI` applied. The inference results are *pushed* into a shared cache by `InferenceOperator`; the delegate simply reads the `omni:rtwt:field_array:tag` attribute from the prim to obtain the cache key and retrieves the data. Modifying this attribute is also what triggers downstream visualization operators to re-execute.

**`omni.rtwt.controller`**

Two responsibilities:

1. **`AppStateOperator`** — Kit-CAE operator on the `/World/AppState` prim. The single fan-out point for all application state changes. On every execution it: sets car geometry variants, sets CAE visualization mode and slice direction variants, updates colormap domains, forwards velocity to the inference prim, applies slider-driven transforms, switches streamlines materials, and controls timeline playback.

2. **WebRTC messaging bridge** — registers request/signal handlers over `omni.kit.livestream.messaging`, reusing the existing WebRTC connection. Exposes the following to the web front-end:
   - `get_state` / `set_state` — read/write `/World/AppState` attributes
   - `set_view` — switch camera view
   - `get_colormap` — fetch colormap LUT + domain
   - `start_cache` / `stop_cache` — drive the pre-caching workflow (Triton-only)
   - `get_available_options` — report which inference-input values the runtime can serve. Always includes `velocity` — the set of wind speeds the backend supports (so the UI need not hardcode it). When the runtime is locked to the pre-baked cache (offline mode, no-generate), the `options` dict is narrowed and variant-axis keys (`spoiler`, `rims`, `mirrors`) are added. Also carries `enforced` (true iff restricted) and `precaching_available` (false iff enforced, since pre-caching requires Triton). The frontend pulls this once on connect and uses it to drive the velocity slider ticks, grey out unavailable UI options, and hide the CACHE card.

**`omni.rtwt.pip_prebundle`**

Bundles `tritonclient[http]` as a Kit extension so it is available at runtime inside the container without a separate pip install step.

---

### Trame App (`trame-app/`)

The web front-end is a Python Trame server that renders a full-screen Vuetify3 UI. The Kit WebRTC stream is displayed in a `<video>` element behind the UI panels.

**State model:**

- `kit_bridge_keys` — bidirectional state keys synced between trame and Kit: `vizMode`, `vizField`, `sliceDirection`, `sliderValue`, `spoiler`, `rims`, `mirrors`, `velocity`, `animatedStreaks`
- `kit_read_keys` — Kit→trame only, never sent back: `cmapVelocity`, `cmapPressure` (used to render live colormap bars with min/max labels)
- **Option lists** — `velocity_options`, `spoiler_options`, `mirrors_options`, `rims_options`. Populated once on connect from Kit's `get_available_options` reply. `velocity_options` is always a list (Kit reports its supported wind-speed set authoritatively, narrowed by the offline cache when enforced); the variant-axis keys are `None` when unrestricted and a list when the offline cache is authoritative.
- `precaching_available` — `true` by default; set to `false` when the runtime is locked to the offline cache. The CACHE card is `v_show`-gated on this.
- `velocity_index` — an integer shim bound to the velocity slider (`step=1`, ticks labelled with `velocity_options`). A pair of `@state.change` handlers keeps `velocity_index` and `velocity` in sync. The slider itself is `v_if`-gated on `velocity_options.length` so it only renders after Kit has reported its supported values.

**`static/app_streamer.js`** — the JavaScript glue layer that:
- Loads `kit-streamer.iife.js` to initialize `window.KitStreamer`
- On connection, registers Kit signal handlers and pulls initial state from Kit (retries up to 20 times with 500 ms backoff)
- After the first successful `get_state`, calls `get_available_options` and forwards the reply to the `apply_available_options` trame trigger, which populates the `*_options` / `precaching_available` state
- Listens to trame state changes and forwards diffs of `kit_bridge_keys` to Kit via `set_state`
- Exposes `window.RTWTControls` for button-driven state changes, so discrete controls use the same client-side state bridge as sliders and switches
- Uses a `_syncingFromKit` guard to prevent echo loops when Kit pushes state corrections back

**Kit signals handled:**
- `state_sync_signal` — Kit→trame state correction (JS)
- `notification_signal` — show/hide notification banner; `kind === 'transient'` auto-dismisses after 2 s (JS)
- `cache_state_signal` — cache progress updates (Python `@on_kit_signal`)

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
              └── Base.usda  ← base scene: AppState, cameras, wind tunnel + car (as payloads)
```

**`Base.usda`** — establishes the scene: Z-up axis, 0.01 m/unit, 60 fps. Defines `/World/AppState` with default attribute values. Adds the wind tunnel environment and car models as USD *payloads* so they can be selectively unloaded. The AeroNIM server, for example, opens this stage with `LoadNone` and never loads the visual assets.

**`BaseCAE.usda`** — adds all CAE visualization operators and data prims under `/World/CAE`. Uses USD `over` prims as prototypes for the volume and slice operators to avoid duplication — concrete operator prims reference the prototype and override only the field target and colormap.

**`BaseCAEVariants.usda`** — adds `Mode` and `SliceDirection` variant sets to `/World/CAE`. Each variant configures visibility and operator enable/disable state for the appropriate prims. `AppStateOperator` calls `SetVariantSelection()` and USD composition handles the rest — no conditional Python logic is needed.

**`Main.usda`** — intentionally kept nearly empty and used as the edit target when working in the Kit editor. Any interactive changes (moving a prim, tweaking a value) are captured here as USD overrides rather than modifying the underlying layer specs. This makes it straightforward to inspect what has changed and to selectively promote modifications to a lower layer when they are ready to be permanent.

### Key prims

**`/World/AppState`**

The single point of control for everything the web UI can change. Has two API schemas applied:

- `RtwtInferenceAppStateAPI` — attributes that affect what data is computed (velocity, car configuration); changes trigger new inference
- `RtwtVizAppStateAPI` — attributes that affect how data is visualized (viz mode, slice direction, animated streaks); changes trigger re-render only

> **Developer tip:** When testing in the editor without the web UI, edit the attributes on `/World/AppState` directly. `AppStateOperator` will react exactly as the web app would.

**`/World/CarCFD`**

A `CaeDataSet` prim with `CaeMeshAPI` and `RtwtModelAPI` applied. Provides the surface mesh geometry to the visualization and inference pipelines via nested variant sets (Rims → Mirrors → Spoiler → Ride_Height). Each leaf variant points to one of the 16 pre-computed surface mesh files under `data/low_res/`.

The encoding scheme for mesh file directory names:

```
variant_number = 500 + mirrors + 2×spoiler + 4×rims + 8×ride_height
  Mirrors:     On=0,       Off=1
  Spoiler:     Off=0,      On=1
  Rims:        Standard=0, Aero=1
  Ride_Height: Standard=0, High=1
```

The `omni:rtwt:model:tag` attribute (from `RtwtModelAPI`) resolves to the relative mesh file path for the active variant. The AeroNIM `rtwt` model reads this attribute from the serialized USD layer to load the correct geometry.

> **Developer tip:** Open `stages/layers/CarCFD.usda` as a standalone stage in the Kit editor and add the `Faces` operator from kit-cae to the `CarCFD` prim to visualize the surface mesh geometry directly.

**`/World/Domain`**

A `CaeDataSet` prim with a VTK image data API schema that defines the regular sampling grid for inference. Has variants to select refinement level; the default targets approximately 2 million sample points.

**`/World/InferenceResults`**

References `/World/Domain` to inherit the sampling grid definition. Adds `CaeNumPyFieldArray` prims — `Velocity`, `VelocityMagnitude`, `Pressure` — each with `RtwtFieldArrayAPI` applied. These are the prims that the delegate writes into when new inference results arrive.

**`/World/Inference`**

The Kit-CAE operator prim for inference. Key API schemas:

| Schema | Instance | Role |
|---|---|---|
| `RtwtInferenceAPI` | — | `omni:rtwt:inference:velocity` — wind speed |
| `RtwtInferenceCacheAPI` | — | `useCache`, `preCaching` |
| `CaeVizDatasetSelectionAPI` | `:domain` | Points to `/World/Domain` |
| `CaeVizDatasetSelectionAPI` | `:model` | Points to `/World/CarCFD` |
| `RtwtResultFieldSelectionAPI` | `:nvdb_velocity` | Target: `/World/InferenceResults/Velocity` |
| `RtwtResultFieldSelectionAPI` | `:nvdb_velocity_magnitude` | Target: `/World/InferenceResults/VelocityMagnitude` |
| `RtwtResultFieldSelectionAPI` | `:nvdb_pressure` | Target: `/World/InferenceResults/Pressure` |

Only the result fields actually needed by the visualization pipeline are declared. Adding an `RtwtResultFieldSelectionAPI` instance is how you request an additional output from the model without transferring unused data.

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

**`stages/layers/WindTunnel/windTunnelEnv.usd`**

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
| `standard` | `kit` + `aeronim` + `web` | Live via Triton | 2 GPUs, NGC API key, custom AeroNIM image |
| `lite` | `kit-lite` + `web` | Offline, served from [data/cache/](../data/cache/) | 1 GPU |

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
| Controller extension | `source/extensions/omni.rtwt.controller/python/` | `/app/exts/omni.rtwt.controller/omni/rtwt/controller/` |
| Delegate extension | `source/extensions/omni.rtwt.delegate/python/` | `/app/exts/omni.rtwt.delegate/omni/rtwt/delegate/` |
| Inference extension | `source/extensions/omni.rtwt.inference/python/` | `/app/exts/omni.rtwt.inference/omni/rtwt/inference/` |
| Schema extension | `source/extensions/omni.rtwt.schema/python/` | `/app/exts/omni.rtwt.schema/omni/rtwt/schema/` |
| Triton `rtwt` model | `aeronim/rtwt/` | `/opt/triton/rtwt/` |
| Trame app | `trame-app/app.py` | `/app/app.py` |

To restart a single service after a code change:

```sh
docker compose restart kit      # Kit application
docker compose restart aeronim  # AeroNIM inference server
docker compose restart web      # Trame web front-end
```

### Using the editor app

To work with the full Kit editor instead of the streaming app, override `KIT_APP` when starting the Kit service:

```sh
KIT_APP=omni.rtwt.editor.kit docker compose up kit
```

### Testing application state without the web UI

Open the stage in the editor app and navigate to `/World/AppState`. Edit any attribute directly — `AppStateOperator` will react identically to how the web app would. This is the recommended workflow for testing new controls or visualizations before wiring them up to the UI.

### Stages and data volumes

Both `stages/` and `data/` are mounted read-only into the Kit and AeroNIM containers. USD stage edits made in the editor app are written to the host filesystem and are immediately visible to both containers on the next restart.
