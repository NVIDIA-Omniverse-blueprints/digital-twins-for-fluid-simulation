import argparse
import hashlib
import os
import re
import urllib.request
from pathlib import Path
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as vuetify
from trame.widgets import html

# -----------------------------------------------------------------------------
# Trame Initialization
# -----------------------------------------------------------------------------
server = get_server()
state, ctrl = server.state, server.controller

def _env_value(name):
    return os.environ.get(name, "").strip()

def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _panels_mode():
    mode = os.environ.get("RTWT_UI_PANELS", "both").strip().lower()
    return mode if mode in {"both", "explore", "compare"} else "both"

# Which panels the right-hand UI builds: "both" (default), or "explore"/"compare"
# to build only that one panel (no mode tabs). "compare" enters the pinned
# comparison combo at load.
UI_PANELS = _panels_mode()

def _discover_public_ip():
    configured = _env_value("RTWT_PUBLIC_IP")
    if configured:
        return configured
    if not _env_flag("RTWT_DISCOVER_PUBLIC_IP"):
        return ""
    try:
        with urllib.request.urlopen("http://icanhazip.com", timeout=1.5) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        return ""

# Serve static/ at /static/ and inject app_streamer.js as a <script type="module">
STATIC_DIR = Path(__file__).parent / "static"
APP_STREAMER_JS = STATIC_DIR / "app_streamer.js"
APP_STREAMER_VERSION = hashlib.sha256(APP_STREAMER_JS.read_bytes()).hexdigest()[:12]

state.kit_stream_config = {
    "signalingServer": _env_value("RTWT_SIGNALING_SERVER"),
    "signalingPort": _env_value("RTWT_SIGNALING_PORT"),
    "mediaServer": _env_value("RTWT_MEDIA_SERVER"),
    "forceWSS": _env_value("RTWT_FORCE_WSS"),
    "publicIp": _discover_public_ip(),
}

class _KitModule:
    serve = {"static": str(STATIC_DIR)}
    # Cache-bust the app bridge. Browsers otherwise can reuse a stale
    # app_streamer.js across Helm redeploys of the same NodePort origin.
    module_scripts = [f"/static/app_streamer.js?v={APP_STREAMER_VERSION}"]
    scripts = []
    styles = []
    vue_use = []

server.enable_module(_KitModule)

CAMERAS = sorted(
    STATIC_DIR.glob("Camera*.png"),
    key=lambda p: int(re.search(r'\d+', p.stem).group())
)

# Keys bridged between trame and Kit (JS reads this — no hardcoding in app_streamer.js)
state.kit_bridge_keys = [
    'vizMode', 'vizField', 'sliceDirection', 'sliderValue',
    'spoiler', 'rims', 'mirrors', 'velocity', 'animatedStreaks',
    'comparisonResultSet',
]
state.kit_signals = []     # populated automatically by @on_kit_signal registrations below
state.kit_read_keys = ['cmapVelocity', 'cmapPressure']  # Kit→trame only, never sent back
state.cmapVelocity = {}
state.cmapPressure = {}

# Static UI state (updated by Kit signals, not reset)
state.cmap_velocity_css = "linear-gradient(to right, blue, cyan, green, yellow, red)"
state.cmap_velocity_min = 0.0
state.cmap_velocity_max = 180.0
state.cmap_pressure_css = "linear-gradient(to right, blue, cyan, green, yellow, red)"
state.cmap_pressure_min = 0.0
state.cmap_pressure_max = 0.0
state.notification_active = False
state.notification_message = ""
state.kit_ready = False
state.kit_status = "Connecting to the simulation…"
state.cache_state    = "idle"   # "idle" | "caching" | "cached"
state.cache_progress = 0
state.cache_total    = 0

# Comparison view. `comparison_active` swaps the main settings panel for the
# comparison panel via v-show. `comparison_result_set` tracks the selected
# segment (UI highlight); `comparisonResultSet` is the bridged AppState control
# that the binding engine maps to the inference resultSetOverride — entering
# Compare defaults to "surrogate"; exiting sets "off" (live combo). In
# compare-only mode the comparison panel is active from the first frame.
state.ui_panels = UI_PANELS                # "both" | "explore" | "compare" (read by app_streamer.js)
state.comparison_active = (UI_PANELS == "compare")
state.comparison_result_set = "surrogate"  # "ground_truth" | "surrogate" | "diff"
state.comparisonResultSet = "off"          # bridged AppState control (off until Compare is entered)

# Available-options lists, populated by Kit via get_available_options on
# connect (see app_streamer.js). velocity_options is always a list — Kit
# reports its full supported set plus any offline-cache narrowing. For the
# variant toggles, None means "no restriction, show all values".
state.velocity_options = []
state.spoiler_options  = None
state.mirrors_options  = None
state.rims_options     = None
state.precaching_available = True

# Index into velocity_options. The slider binds to this (step=1) so the thumb
# snaps naturally to valid positions; tick labels display the actual velocities.
# Kept in sync with `velocity` both ways.
state.velocity_index = 0
_suppress_velocity_resync = False

@state.change('velocity_index')
def _apply_velocity_index(velocity_index, velocity_options, **_):
    global _suppress_velocity_resync
    if not velocity_options or not (0 <= velocity_index < len(velocity_options)):
        return
    target = float(velocity_options[velocity_index])
    if state.velocity != target:
        _suppress_velocity_resync = True
        try:
            state.velocity = target
        finally:
            _suppress_velocity_resync = False

@state.change('velocity', 'velocity_options')
def _resync_velocity_index(velocity, velocity_options, **_):
    if _suppress_velocity_resync or not velocity_options:
        return
    if velocity in velocity_options:
        idx = velocity_options.index(velocity)
    else:
        idx = min(range(len(velocity_options)), key=lambda i: abs(velocity_options[i] - velocity))
        state.velocity = float(velocity_options[idx])
    if state.velocity_index != idx:
        state.velocity_index = idx

# -----------------------------------------------------------------------------
# Kit Signal Dispatch
# -----------------------------------------------------------------------------
_kit_signal_handlers = {}

def on_kit_signal(signal_name):
    """Decorator to register a Python handler for a Kit signal.
    JS forwards all Kit signals to the 'on_kit_signal' trame trigger;
    this dispatcher routes them to the appropriate handler.
    """
    def decorator(fn):
        _kit_signal_handlers[signal_name] = fn
        state.kit_signals = list(_kit_signal_handlers.keys())
        return fn
    return decorator

@ctrl.trigger('on_kit_signal')
def _dispatch_kit_signal(name, data):
    handler = _kit_signal_handlers.get(name)
    if handler:
        handler(data)

@on_kit_signal('cache_state_signal')
def _handle_cache_state(data):
    with state:
        state.cache_state    = data.get('state',    'idle')
        state.cache_progress = data.get('progress', 0)
        state.cache_total    = data.get('total',    0)


# The available-options (velocity_options / spoiler_options / mirrors_options /
# rims_options / precaching_available) are applied to trame state directly from
# app_streamer.js via window.trame.state.set(), reusing the same apply path get_state
# uses. A trame trigger round-trip does not reliably populate them; setting state
# directly does.


# -----------------------------------------------------------------------------
# Colormap state — computed from kit_read_keys cmapVelocity / cmapPressure
# -----------------------------------------------------------------------------
def _cmap_to_css(cmap):
    """Convert a {x, rgba, domain} colormap dict to a CSS linear-gradient string."""
    xs   = cmap.get('x',    [])
    rgba = cmap.get('rgba', [])  # flat [r,g,b,a, r,g,b,a, ...]  values in [0,1]
    stops = [
        f"rgb({round(rgba[i*4]*255)},{round(rgba[i*4+1]*255)},{round(rgba[i*4+2]*255)}) {xs[i]*100:.1f}%"
        for i in range(len(xs))
    ]
    return f"linear-gradient(to right, {', '.join(stops)})"

@state.change('cmapVelocity')
def _on_cmap_velocity(cmapVelocity, **_):
    if not cmapVelocity:
        return
    domain = cmapVelocity.get('domain', [0, 1])
    with state:
        state.cmap_velocity_css = _cmap_to_css(cmapVelocity)
        state.cmap_velocity_min = round(domain[0] * 10) / 10
        state.cmap_velocity_max = round(domain[1] * 10) / 10

@state.change('cmapPressure')
def _on_cmap_pressure(cmapPressure, **_):
    if not cmapPressure:
        return
    domain = cmapPressure.get('domain', [0, 1])
    with state:
        state.cmap_pressure_css = _cmap_to_css(cmapPressure)
        state.cmap_pressure_min = round(domain[0] * 10) / 10
        state.cmap_pressure_max = round(domain[1] * 10) / 10

def reset_state():
    state.vizMode = "Streamlines"
    state.vizField = "VelocityMagnitude"
    state.sliceDirection = "X"
    state.sliderValue = 0
    state.animatedStreaks = False
    state.playAnimation = False
    state.spoiler = "On"
    state.rims = "Standard"
    state.mirrors = "On"
    state.velocity = 25.0

reset_state()

def ui_set(key, value):
    return f"window.RTWTControls?.set({key!r}, {value!r})"

def ui_reset():
    return "window.RTWTControls?.reset()"

# ── Comparison view click handlers ───────────────────────────────────────────
# Each helper returns a single JS click expression that calls a window.RTWTComparison
# method. Those methods flip the trame flag/state so the panel re-renders and drive
# window.RTWTControls.set — the same debounced set_state bridge the Explore panel uses
# — so a result-set switch rides the same clean operator pass a viz change does.

def comparison_enter():
    # Snapshot Explore's state, pin the fixed baked combo, and show the AI surrogate.
    return "window.RTWTComparison.enterView()"

def comparison_exit():
    # Restore Explore's full state + clear the override (live combo), then show the main panel.
    return "window.RTWTComparison.exitView()"

def comparison_set_result(result_set):
    # Select ground_truth / surrogate / diff. Diff supports Volume/Slice only, so
    # selectResultSet coerces a Flow/Streamlines vizMode to Volume in the same state
    # patch; the binding engine then maps the current {vizMode}_{vizField} to the
    # matching delta variant.
    return f"window.RTWTComparison.selectResultSet({result_set!r})"

def comparison_set_viz(key, value):
    # Viz change inside the comparison panel — a plain bridge set_state, identical
    # to Explore's path (RTWTControls.set).
    return f"window.RTWTComparison.setViz({key!r}, {value!r})"

# -----------------------------------------------------------------------------
# UI Definition
# -----------------------------------------------------------------------------
with SinglePageLayout(server) as layout:
    layout.toolbar.hide()
    layout.footer.hide()
    layout.content.style = "padding: 0; margin: 0;"
    layout.root.theme = "dark"

    with layout.content:
        with html.Div(style="position: relative; width: 100vw; height: 100vh; background-color: #1a1a1a; overflow: hidden;"):

            # ── Kit streaming viewport ──────────────────────────────────────
            html.Video(
                id="remote-video",
                style="position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain;",
                autoplay=True,
                muted=True,
                playsinline=True,
                tabindex="-1",
            )
            html.Audio(id="remote-audio", muted=True, style="display: none;")

            # Keep controls hidden until Kit has supplied state and supported options.
            # A cold renderer can spend several minutes compiling shaders.
            with html.Div(
                v_if="!kit_ready",
                role="status",
                aria_live="polite",
                classes="text-center pa-6 rounded-lg",
                style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(30, 30, 30, 0.9);",
            ):
                vuetify.VProgressCircular(indeterminate=True, color="green", classes="mb-4")
                html.Div("{{ kit_status }}", classes="text-h6 mb-2")
                html.Div("The first launch can take several minutes while shaders compile.")

            # ── Notification banner (top center) ────────────────────────────
            vuetify.VSnackbar(
                v_model=("notification_active",),
                location="top center",
                timeout=-1,
                color="surface",
                elevation=4,
                rounded="pill",
                # Lite cache hits complete too quickly for a useful banner. Keep
                # notification_active unchanged for control locking and hide only
                # the snackbar presentation while offline options are enforced.
                style=("precaching_available === false ? 'visibility: hidden;' : null",),
                children=[html.Div("{{ notification_message }}", classes="text-center w-100 text-green-darken-2 font-weight-bold")],
            )

            # =========================================================
            # LEFT PANEL: Camera Viewpoints
            # =========================================================
            with vuetify.VCard(
                v_show="kit_ready",
                style="position: absolute; top: 50%; transform: translateY(-50%); left: 20px; width: 120px; background-color: rgba(30, 30, 30, 0.85); backdrop-filter: blur(5px);"
            ):
                vuetify.VCardTitle("VIEWS", classes="text-center font-weight-bold pt-4 text-subtitle-2")
                with vuetify.VCardText(classes="px-2 pb-2"):
                    with vuetify.VRow(dense=True):
                        for pov in CAMERAS:
                            html.Div(
                                style="width: 100%; height: 80px; overflow: hidden; border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; margin-bottom: 4px; cursor: pointer;",
                                click=f"window.KitStreamer?.send('set_view', {{ name: '{pov.stem}' }})",
                                children=[
                                    vuetify.VImg(
                                        src=f"/static/{pov.name}",
                                        cover=True,
                                        height="80",
                                    )
                                ]
                            )
                    vuetify.VDivider(classes="mb-2 mt-1")
                    vuetify.VBtn(
                        "ORBIT",
                        block=True,
                        variant="outlined",
                        prepend_icon="mdi-rotate-orbit",
                        color="grey-lighten-1",
                        size="small",
                        click="window.KitStreamer?.send('set_view', { name: 'FullOrbit_Camera' })",
                    )

            # =========================================================
            # RIGHT PANEL: Settings
            # =========================================================
            with html.Div(v_show="kit_ready", style="position: absolute; top: 20px; right: 20px; bottom: 20px; width: 380px; overflow-y: auto; padding-right: 4px;"):

                # ── Mode tabs: Explore / Compare ────────────────────────────
                # Two-tab control at the top of the right panel; the active tab
                # is driven by comparison_active. Selecting Compare snapshots
                # Explore's state and flips comparison_active so the main
                # "Explore" cards hide (v_show) and the comparison panel appears;
                # selecting Explore exits comparison and restores them. Both tabs
                # are always visible. VBtnToggle is used (mandatory, single-select)
                # and styled to read as tabs in the dark theme.
                if UI_PANELS == "both":
                    with vuetify.VBtnToggle(
                        model_value=("comparison_active ? 1 : 0",),
                        mandatory=True,
                        divided=True,
                        density="comfortable",
                        classes="mb-2 d-flex",
                        style="width: 100%; background-color: rgba(30, 30, 30, 0.85); backdrop-filter: blur(5px);",
                    ):
                        vuetify.VBtn(
                            "Explore",
                            value=0,
                            variant="flat",
                            prepend_icon="mdi-tune-variant",
                            color=("!comparison_active ? 'green-darken-2' : 'transparent'",),
                            classes=("'flex-grow-1' + (!comparison_active ? ' font-weight-bold' : '')",),
                            disabled=("notification_active || cache_state === 'caching'",),
                            click=comparison_exit(),
                        )
                        vuetify.VBtn(
                            "Compare",
                            value=1,
                            variant="flat",
                            prepend_icon="mdi-compare",
                            color=("comparison_active ? 'green-darken-2' : 'transparent'",),
                            classes=("'flex-grow-1' + (comparison_active ? ' font-weight-bold' : '')",),
                            disabled=("notification_active || cache_state === 'caching'",),
                            click=comparison_enter(),
                        )

                if UI_PANELS in ("both", "explore"):
                    with vuetify.VCard(
                        v_show="!comparison_active",
                        style="background-color: rgba(30, 30, 30, 0.85); backdrop-filter: blur(5px);",
                    ):
                        vuetify.VCardTitle("SETTINGS", classes="text-center font-weight-bold pt-4")
                        with vuetify.VCardText():

                            # ── Velocity ───────────────────────────────────────
                            # Index slider (step=1) whose ticks are labeled with
                            # the velocities Kit reports via get_available_options.
                            # The thumb snaps naturally; labels convey the real
                            # value. Hidden until Kit has populated the list.
                            html.Div(
                                "Velocity: {{ velocity }} m/s",
                                v_if="velocity_options && velocity_options.length",
                                classes="text-caption text-center mb-1",
                            )
                            vuetify.VSlider(
                                v_if="velocity_options && velocity_options.length",
                                v_model=("velocity_index", 0),
                                min=0,
                                max=("velocity_options.length - 1",),
                                step=1,
                                # Vuetify3 ticks accepts Record<number, string>:
                                # key = tick position (the index we bind to), value = label.
                                ticks=("Object.fromEntries(velocity_options.map((v, i) => [i, String(v)]))",),
                                show_ticks="always",
                                tick_size=4,
                                hide_details=True,
                                color="grey-lighten-1",
                                disabled=("notification_active || cache_state === 'caching'",),
                            )

                            # ── Spoiler ────────────────────────────────────────
                            html.Div("Spoiler", classes="text-caption text-center mt-3 mb-1")
                            with vuetify.VRow(dense=True, classes="mb-3"):
                                for val in ["On", "Off"]:
                                    with vuetify.VCol():
                                        vuetify.VBtn(
                                            val,
                                            block=True,
                                            variant="outlined",
                                            color=(f"spoiler === '{val}' ? 'green-darken-2' : 'default'",),
                                            classes=(f"spoiler === '{val}' ? 'font-weight-bold' : ''",),
                                            disabled=(f"notification_active || cache_state === 'caching' || (spoiler_options && !spoiler_options.includes('{val}'))",),
                                            click=ui_set("spoiler", val),
                                        )

                            # ── Mirrors ────────────────────────────────────────
                            html.Div("Mirrors", classes="text-caption text-center mb-1")
                            with vuetify.VRow(dense=True, classes="mb-3"):
                                for val in ["On", "Off"]:
                                    with vuetify.VCol():
                                        vuetify.VBtn(
                                            val,
                                            block=True,
                                            variant="outlined",
                                            color=(f"mirrors === '{val}' ? 'green-darken-2' : 'default'",),
                                            classes=(f"mirrors === '{val}' ? 'font-weight-bold' : ''",),
                                            disabled=(f"notification_active || cache_state === 'caching' || (mirrors_options && !mirrors_options.includes('{val}'))",),
                                            click=ui_set("mirrors", val),
                                        )

                            # ── Rims ───────────────────────────────────────────
                            html.Div("Rims", classes="text-caption text-center mb-1")
                            with vuetify.VRow(dense=True, classes="mb-3"):
                                for val, img in [("Standard", "StandardRim.png"), ("Aero", "AeroRim.png")]:
                                    with vuetify.VCol():
                                        with html.Div(
                                            style=(f"(notification_active || cache_state === 'caching' || (rims_options && !rims_options.includes('{val}'))) ? 'border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; cursor: default; overflow: hidden; opacity: 0.5; pointer-events: none;' : rims === '{val}' ? 'border: 2px solid #388e3c; border-radius: 4px; cursor: pointer; overflow: hidden;' : 'border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; cursor: pointer; overflow: hidden;'",),
                                            click=ui_set("rims", val),
                                        ):
                                            vuetify.VImg(src=f"/static/{img}", cover=True, height="96")

                    vuetify.VDivider(classes="my-2", style="opacity: 0;", v_show="!comparison_active")

                    with vuetify.VCard(
                        v_show="!comparison_active",
                        style="background-color: rgba(30, 30, 30, 0.85); backdrop-filter: blur(5px);",
                    ):
                        vuetify.VCardTitle("VISUALIZATION TECHNIQUES", classes="text-center font-weight-bold pt-4")
                        with vuetify.VCardText():
                            with vuetify.VRow(dense=True):
                                for tech in ["Flow", "Streamlines", "Volume", "Slice"]:
                                    with vuetify.VCol(cols="6"):
                                        vuetify.VBtn(
                                            tech,
                                            block=True,
                                            variant="outlined",
                                            color=(f"vizMode == '{tech}' ? 'green-darken-2' : 'default'",),
                                            classes=(f"'mb-2' + (vizMode == '{tech}' ? ' font-weight-bold' : '')",),
                                            disabled=("notification_active || cache_state === 'caching'",),
                                            click=ui_set("vizMode", tech)
                                        )

                        vuetify.VDivider(classes="mx-4 my-2", v_show="vizMode !== 'Flow'")

                        with vuetify.VCardText(classes="text-center", v_show="vizMode !== 'Flow'"):
                            html.Div("ACTIVE VIZ:", classes="text-caption text-grey")
                            html.Div(
                                "{{ vizMode + (vizMode === 'Volume' || vizMode === 'Slice' ? ' / ' + vizField : '') }}",
                                classes="text-h6 font-weight-bold text-uppercase",
                            )
                            with html.Div(v_show="(vizMode === 'Streamlines' && !animatedStreaks) || ((vizMode === 'Volume' || vizMode === 'Slice') && vizField === 'VelocityMagnitude')"):
                                html.Div(style=("{ height: '15px', width: '100%', background: cmap_velocity_css, borderRadius: '4px', marginTop: '10px' }",))
                                with html.Div(style="display: flex; justify-content: space-between; font-size: 0.7rem; margin-top: 4px;"):
                                    html.Span("{{ cmap_velocity_min }}")
                                    html.Span("{{ cmap_velocity_max }}")

                            with html.Div(v_show="(vizMode === 'Volume' || vizMode === 'Slice') && vizField === 'Pressure'"):
                                html.Div(style=("{ height: '15px', width: '100%', background: cmap_pressure_css, borderRadius: '4px', marginTop: '10px' }",))
                                with html.Div(style="display: flex; justify-content: space-between; font-size: 0.7rem; margin-top: 4px;"):
                                    html.Span("{{ cmap_pressure_min }}")
                                    html.Span("{{ cmap_pressure_max }}")

                        vuetify.VDivider(classes="mx-4 my-2")

                        vuetify.VCardTitle("VISUALIZATION ADJUSTMENT", classes="text-center font-weight-bold text-subtitle-2 pb-0")
                        with vuetify.VCardText(classes="pt-2 pb-4"):

                            # ── Field selector (Volume / Slice only) ───────────
                            with html.Div(v_show="vizMode === 'Volume' || vizMode === 'Slice'"):
                                html.Div("Field", classes="text-caption text-center mb-1")
                                with vuetify.VRow(dense=True, classes="mb-3"):
                                    for val, label in [("VelocityMagnitude", "Velocity Mag."), ("Pressure", "Pressure")]:
                                        with vuetify.VCol():
                                            vuetify.VBtn(
                                                label,
                                                block=True,
                                                variant="outlined",
                                                color=(f"vizField === '{val}' ? 'green-darken-2' : 'default'",),
                                                classes=(f"vizField === '{val}' ? 'font-weight-bold' : ''",),
                                                disabled=("notification_active || cache_state === 'caching'",),
                                                click=ui_set("vizField", val),
                                            )

                            with html.Div(v_show="vizMode === 'Flow' || vizMode === 'Streamlines'"):
                                html.Div("Position", classes="text-caption text-center mb-1")
                                vuetify.VSlider(
                                    v_model=("sliderValue", 0),
                                    min=-100, max=100, step=1,
                                    hide_details=True,
                                    color="grey-lighten-1",
                                    disabled=("notification_active || cache_state === 'caching'",),
                                )

                            with html.Div(v_show="vizMode === 'Streamlines'", classes="mt-3"):
                                vuetify.VSwitch(
                                    v_model=("animatedStreaks", False),
                                    label="Animated Streaks",
                                    color="green-darken-2",
                                    hide_details=True,
                                    density="compact",
                                    disabled=("notification_active || cache_state === 'caching'",),
                                )

                            with html.Div(v_show="vizMode === 'Slice'"):
                                html.Div("Slice Direction", classes="text-caption text-center mt-3 mb-1")
                                with vuetify.VRow(dense=True, classes="mb-2"):
                                    for direction in ["X", "Y", "Z"]:
                                        with vuetify.VCol(cols="4"):
                                            vuetify.VBtn(
                                                direction,
                                                block=True,
                                                variant="outlined",
                                                color=(f"sliceDirection === '{direction}' ? 'green-darken-2' : 'default'",),
                                                classes=(f"sliceDirection === '{direction}' ? 'font-weight-bold' : ''",),
                                                disabled=("notification_active || cache_state === 'caching'",),
                                                click=ui_set("sliceDirection", direction)
                                            )
                                html.Div("Position", classes="text-caption text-center mt-3 mb-1")
                                vuetify.VSlider(
                                    v_model=("sliderValue", 0),
                                    min=-100, max=100, step=1,
                                    hide_details=True,
                                    color="grey-lighten-1",
                                    disabled=("notification_active || cache_state === 'caching'",),
                                )

                        vuetify.VDivider(classes="mx-4 my-2")
                        with vuetify.VCardText(classes="pb-4"):
                            vuetify.VBtn(
                                "Reset",
                                block=True,
                                variant="outlined",
                                prepend_icon="mdi-restore",
                                color="grey-lighten-1",
                                disabled=("notification_active || cache_state === 'caching'",),
                                click=ui_reset(),
                            )

                    vuetify.VDivider(classes="my-2", style="opacity: 0;", v_show="precaching_available && !comparison_active")

                    with vuetify.VCard(
                        v_show="precaching_available && !comparison_active",
                        style="background-color: rgba(30, 30, 30, 0.85); backdrop-filter: blur(5px);",
                    ):
                        vuetify.VCardTitle("CACHE", classes="text-center font-weight-bold pt-4")
                        with vuetify.VCardText():

                            # Idle state: single "BUILD & USE CACHE" button
                            vuetify.VBtn(
                                "BUILD & USE CACHE",
                                v_show="cache_state === 'idle'",
                                block=True,
                                variant="outlined",
                                prepend_icon="mdi-cached",
                                color="grey-lighten-1",
                                click="window.KitStreamer?.send('start_cache', {})",
                            )

                            # Caching state: disabled progress button + linear progress bar
                            with html.Div(v_show="cache_state === 'caching'"):
                                vuetify.VBtn(
                                    "{{ 'Caching ' + cache_progress + ' / ' + cache_total + '...' }}",
                                    block=True,
                                    variant="outlined",
                                    color="green-darken-2",
                                    size="small",
                                    disabled=True,
                                )
                                vuetify.VProgressLinear(
                                    model_value=("cache_progress / cache_total * 100", 0),
                                    color="green-darken-2",
                                    height=3,
                                    classes="mt-1",
                                )

                            # Cached state: chip + clear button
                            with html.Div(v_show="cache_state === 'cached'"):
                                with vuetify.VRow(dense=True, classes="align-center"):
                                    with vuetify.VCol():
                                        vuetify.VChip(
                                            "{{ cache_total + ' STATES CACHED' }}",
                                            prepend_icon="mdi-check-circle",
                                            color="green-darken-2",
                                        )
                                    with vuetify.VCol(cols="auto"):
                                        vuetify.VBtn(
                                            "CLEAR",
                                            variant="outlined",
                                            size="small",
                                            color="grey-lighten-1",
                                            click="window.KitStreamer?.send('stop_cache', {})",
                                        )

                if UI_PANELS in ("both", "compare"):
                    # =====================================================
                    # COMPARISON PANEL
                    # Shown in place of the main cards while comparison_active.
                    # The main panel above is hidden (v_show), not destroyed, so
                    # exiting Compare restores it intact.
                    # =====================================================
                    with vuetify.VCard(
                        v_show="comparison_active",
                        style="background-color: rgba(30, 30, 30, 0.85); backdrop-filter: blur(5px);",
                    ):
                        # ── Header + back/exit affordance ───────────────────
                        with vuetify.VCardTitle(classes="d-flex align-center pt-3 pb-2"):
                            if UI_PANELS == "both":
                                vuetify.VBtn(
                                    icon="mdi-arrow-left",
                                    variant="text",
                                    size="small",
                                    density="comfortable",
                                    click=comparison_exit(),
                                )
                            html.Span("COMPARISON", classes="font-weight-bold text-subtitle-1 ml-1")

                        vuetify.VDivider(classes="mx-4")

                        with vuetify.VCardText():

                            # ── Result-set selector (segmented control) ─────
                            html.Div("Result Set", classes="text-caption text-center mb-1")
                            with vuetify.VRow(dense=True, classes="mb-1"):
                                for rset, label in [
                                    ("ground_truth", "Solver*"),
                                    ("surrogate", "AI Surrogate"),
                                    ("diff", "Diff"),
                                ]:
                                    with vuetify.VCol():
                                        vuetify.VBtn(
                                            label,
                                            block=True,
                                            variant="outlined",
                                            size="small",
                                            color=(f"comparison_result_set === '{rset}' ? 'green-darken-2' : 'default'",),
                                            classes=(f"comparison_result_set === '{rset}' ? 'font-weight-bold' : ''",),
                                            disabled=("notification_active",),
                                            click=comparison_set_result(rset),
                                        )
                            html.Div(
                                "* emulated reference (mock ground truth)",
                                classes="text-caption text-grey text-center mt-1",
                                style="font-size: 0.7rem;",
                            )

                        vuetify.VDivider(classes="mx-4 my-2")

                        # ── Visualization selector ──────────────────────────
                        # GT/surrogate: all four modes. Diff: Volume + Slice only.
                        vuetify.VCardTitle(
                            "VISUALIZATION",
                            classes="text-center font-weight-bold text-subtitle-2 pb-0",
                        )
                        with vuetify.VCardText():
                            with vuetify.VRow(dense=True):
                                for tech in ["Flow", "Streamlines", "Volume", "Slice"]:
                                    # Hide Flow/Streamlines while Diff is active.
                                    v_show = (
                                        "true"
                                        if tech in ("Volume", "Slice")
                                        else "comparison_result_set !== 'diff'"
                                    )
                                    with vuetify.VCol(cols="6"):
                                        vuetify.VBtn(
                                            tech,
                                            v_show=(v_show,),
                                            block=True,
                                            variant="outlined",
                                            color=(f"vizMode == '{tech}' ? 'green-darken-2' : 'default'",),
                                            classes=(f"'mb-2' + (vizMode == '{tech}' ? ' font-weight-bold' : '')",),
                                            disabled=("notification_active",),
                                            click=comparison_set_viz("vizMode", tech),
                                        )

                            # ── Field selector (Volume / Slice only) ────────
                            with html.Div(v_show="vizMode === 'Volume' || vizMode === 'Slice'"):
                                html.Div("Field", classes="text-caption text-center mt-2 mb-1")
                                with vuetify.VRow(dense=True, classes="mb-2"):
                                    for val, label in [("VelocityMagnitude", "Velocity Mag."), ("Pressure", "Pressure")]:
                                        with vuetify.VCol():
                                            vuetify.VBtn(
                                                label,
                                                block=True,
                                                variant="outlined",
                                                color=(f"vizField === '{val}' ? 'green-darken-2' : 'default'",),
                                                classes=(f"vizField === '{val}' ? 'font-weight-bold' : ''",),
                                                disabled=("notification_active",),
                                                click=comparison_set_viz("vizField", val),
                                            )

                            # ── Slice direction (Slice only) ────────────────
                            with html.Div(v_show="vizMode === 'Slice'"):
                                html.Div("Slice Direction", classes="text-caption text-center mt-2 mb-1")
                                with vuetify.VRow(dense=True, classes="mb-1"):
                                    for direction in ["X", "Y", "Z"]:
                                        with vuetify.VCol(cols="4"):
                                            vuetify.VBtn(
                                                direction,
                                                block=True,
                                                variant="outlined",
                                                color=(f"sliceDirection === '{direction}' ? 'green-darken-2' : 'default'",),
                                                classes=(f"sliceDirection === '{direction}' ? 'font-weight-bold' : ''",),
                                                disabled=("notification_active",),
                                                click=comparison_set_viz("sliceDirection", direction),
                                            )

                            # ── Position (Flow / Streamlines / Slice) ───────
                            # Mirrors the main panel's sliderValue Position slider
                            # (same bounds/step/label), driven through the bridge.
                            # @end (not @input) fires once on release, not on every
                            # drag tick.
                            with html.Div(v_show="vizMode === 'Flow' || vizMode === 'Streamlines' || vizMode === 'Slice'"):
                                html.Div("Position", classes="text-caption text-center mt-3 mb-1")
                                vuetify.VSlider(
                                    v_model=("sliderValue", 0),
                                    min=-100, max=100, step=1,
                                    hide_details=True,
                                    color="grey-lighten-1",
                                    disabled=("notification_active",),
                                    # Pushes sliderValue through the bridge set_state on release. A single
                                    # JS call string — NOT a tuple, which Vue treats as a prop and crashes the panel.
                                    end="window.RTWTComparison.setPosition('sliderValue')",
                                )

# -----------------------------------------------------------------------------
# Start the server
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173, help="Port to listen on")
    args, _ = parser.parse_known_args()
    # Kubernetes expects the web process to stay alive even when no browser is
    # connected. Trame defaults to auto-shutdown after an idle timeout.
    server.start(port=args.port, host="0.0.0.0", timeout=0)
