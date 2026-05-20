# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.
import asyncio
from logging import getLogger
from . import ovapi
from . import notification
from pxr import Sdf, Usd
from omni.usd import get_context
from omni.kit.viewport.utility import get_active_viewport
import omni.kit.commands
import omni.kit.app
import omni.kit.livestream.messaging as messaging
import carb
import carb.events
import carb.eventdispatcher
from omni.cae.viz import listener
from . import utils

logger = getLogger(__name__)
ns = "omni:rtwt:service"

app = ovapi.OmniverseAPI()

_APP_STATE_PRIM = "/World/AppState"
_INFERENCE_PRIM = "/World/Inference"
# Lazily built from the schema registry: full_attr_name -> short_key (last namespace component)
_APP_STATE_ATTRS: dict[str, str] = {}


def _get_app_state_attrs() -> dict[str, str]:
    """Return a mapping of full attribute name -> short key for all AppState API schemas.

    Built once on first call from Usd.SchemaRegistry so it stays in sync with the
    schema definitions regardless of namespace changes.
    """
    if not _APP_STATE_ATTRS:
        registry = Usd.SchemaRegistry()
        for api in ("RtwtInferenceAppStateAPI", "RtwtVizAppStateAPI"):
            defn = registry.FindAppliedAPIPrimDefinition(api)
            if defn:
                for prop_name in defn.GetPropertyNames():
                    if not defn.GetAttributeDefinition(prop_name):
                        # Skip properties that aren't attributes, e.g. relationships.
                        continue
                    _APP_STATE_ATTRS[prop_name] = prop_name.rsplit(":", 1)[-1]
            else:
                logger.warning("_get_app_state_attrs: schema not found: %s", api)
    return _APP_STATE_ATTRS

_CACHE_STATE_SIGNAL = "cache_state_signal"
_EVT_SYNC_END = "omni.cae.viz@sync_end"

# Maps vizField values to their colormap prim paths in the stage.
_COLORMAP_PRIMS = {
    "VelocityMagnitude": "/World/Colormaps/VelocityColormap",
    "Pressure":          "/World/Colormaps/PressureColormap",
}

messaging.register_event_type_to_send(_CACHE_STATE_SIGNAL)


def _app_state_prim():
    stage = get_context().get_stage()
    prim  = stage.GetPrimAtPath(_APP_STATE_PRIM) if stage else None
    return prim if (prim and prim.IsValid()) else None


def _send_cache_signal(state: str, progress: int, total: int) -> None:
    stream = omni.kit.app.get_app().get_message_bus_event_stream()
    sig_type = carb.events.type_from_string(_CACHE_STATE_SIGNAL)
    stream.dispatch(sig_type, payload={"state": state, "progress": progress, "total": total})
    stream.pump()


# Authoritative list of wind speeds the blueprint supports. Kept here so the
# pre-cache walk and the UI's velocity slider agree on the value set.
_SUPPORTED_VELOCITIES: list[float] = [float(v) for v in range(25, 101, 25)]


def _all_cache_states() -> list[dict]:
    """Return all 32 pre-cache state combinations (velocity × car config)."""
    combos = []
    for velocity in _SUPPORTED_VELOCITIES:
        for spoiler in ("On", "Off"):
            for rims in ("Standard", "Aero"):
                for mirrors in ("On", "Off"):
                    combos.append({
                        "velocity": velocity,
                        "spoiler": spoiler,
                        "rims": rims,
                        "mirrors": mirrors,
                    })
    return combos


async def _wait_for_sync(timeout: float = 15.0) -> bool:
    """Await the next sync_end event, signalling all operators have finished."""
    done = asyncio.Event()

    dispatcher = carb.eventdispatcher.get_eventdispatcher()
    sub = dispatcher.observe_event(
        order=0,
        event_name=_EVT_SYNC_END,
        on_event=lambda _: done.set(),
        observer_name="rtwt.precache.wait",
    )
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning("_wait_for_sync: TIMEOUT waiting for sync_end")
        return False
    finally:
        del sub


def _get_colormap(stage, viz_field: str) -> dict | None:
    """Read colormap stops and domain from the stage for the given vizField."""
    prim_path = _COLORMAP_PRIMS.get(viz_field)
    if not prim_path:
        return None
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return None
    rgba   = prim.GetAttribute("rgbaPoints").Get()
    x      = prim.GetAttribute("xPoints").Get()
    domain = prim.GetAttribute("domain").Get()
    if rgba is None or x is None:
        return None
    return {
        "rgba":   [v for c in rgba for v in (float(c[0]), float(c[1]), float(c[2]), float(c[3]))],
        "x":      [float(v) for v in x],
        "domain": [float(domain[0]), float(domain[1])] if domain is not None else None,
    }


def discard_modifications_omniverse(prim_path: str):
    context = get_context()
    stage = context.get_stage()
    edit_layer = stage.GetEditTarget().GetLayer()
    omni.kit.commands.execute('RemovePrimSpec',
        layer_identifier=edit_layer.identifier,
        prim_spec_path=prim_path
    )


@app.signal
def inference_complete(message: str):
    logger.warning("Received 'inference_complete_signal' with message: %s", message)
    return message


@app.request
@ovapi.exclusive
async def set_view(name: str) -> bool:
    logger.info(f"Setting view to '{name}'")
    stage = get_context().get_stage()
    if not stage:
        return False

    app_prim = _app_state_prim()
    if name == "FullOrbit_Camera":
        viewport = get_active_viewport()
        viewport.camera_path = "/World/Cameras/FullOrbit_Camera"
        if app_prim:
            play_attr = app_prim.GetAttribute("omni:rtwt:app_state:playAnimation")
            if play_attr:
                play_attr.Set(not play_attr.Get())
    else:
        if app_prim:
            play_attr = app_prim.GetAttribute("omni:rtwt:app_state:playAnimation")
            if play_attr:
                play_attr.Set(False)

    rt_stage = utils.get_rt_stage(stage)
    for path in rt_stage.GetPrimsWithTypeName("Camera"):
        if Sdf.Path(str(path)).name == name:
            viewport = get_active_viewport()
            if viewport:
                camera_sdf_path = Sdf.Path(str(path))

                # Step away from the target camera before discarding its overrides.
                # If we're already on it, move to the default persp camera first so
                # Kit doesn't hold a reference to the prim while we remove its spec.
                if viewport.camera_path == camera_sdf_path:
                    viewport.camera_path = Sdf.Path("/OmniverseKit_Persp")

                # Remove any session-layer overrides on the camera prim so we get
                # the pristine transform/settings defined in the stage (not whatever
                # accumulated from a previous interactive orbit/pan).
                discard_modifications_omniverse(str(path))

                # Now activate the clean camera prim in the viewport.
                viewport.camera_path = camera_sdf_path

                # Unlock the camera so Kit won't prevent the app from driving it,
                # and hint the center-of-interest so orbit feels natural.
                camera = stage.GetPrimAtPath(str(path))
                camera.CreateAttribute("omni:kit:cameraLock", Sdf.ValueTypeNames.Bool).Set(False)
                camera.CreateAttribute("omni:kit:centerOfInterest", Sdf.ValueTypeNames.Double3).Set((0, 0, -946.8))

                logger.info(f"Switched viewport camera to {path}")
                return True
            break

    logger.warning(f"Camera '{name}' not found in stage")
    return False


@app.request
def get_available_options(**_) -> dict:
    """Tell the web UI which inference input options it may expose.

    Always returns a `velocity` list — the set of wind speeds the backend
    supports — so the UI does not have to hardcode it. When offline_mode=true
    and generate_if_missing=false, narrows `velocity` (and adds the variant
    axes) to values for which a cache entry exists. Otherwise returns the full
    supported set with enforced=false. precaching_available is false iff
    enforced, since start_cache requires Triton to be reachable.
    """
    from omni.rtwt.inference.inference import scan_offline_cache_options
    scan = scan_offline_cache_options() or {"enforced": False}
    enforced = bool(scan.get("enforced"))
    options = dict(scan.get("options") or {})
    if not enforced or "velocity" not in options:
        options["velocity"] = list(_SUPPORTED_VELOCITIES)
    return {
        "enforced": enforced,
        "options": options,
        "precaching_available": not enforced,
    }


@app.request
def get_state(**_) -> dict:
    prim = _app_state_prim()
    if not prim:
        return {}
    attrs = _get_app_state_attrs()
    state = {short: prim.GetAttribute(full).Get() for full, short in attrs.items()}
    if stage := get_context().get_stage():
        for field, key in (("VelocityMagnitude", "cmapVelocity"), ("Pressure", "cmapPressure")):
            if cmap := _get_colormap(stage, field):
                state[key] = cmap
    return state


@app.request
@ovapi.exclusive
@listener.exclusive_with_sync
async def set_state(state: dict) -> bool:
    prim = _app_state_prim()
    if not prim:
        logger.error("AppState prim not found at %s", _APP_STATE_PRIM)
        return False
    short_to_full = {short: full for full, short in _get_app_state_attrs().items()}
    with Sdf.ChangeBlock():
        for key, value in state.items():
            full = short_to_full.get(key)
            if full:
                prim.GetAttribute(full).Set(value)
            else:
                logger.warning("Unknown AppState attribute: %s", key)
    return True


@app.request
@ovapi.exclusive
async def start_cache(**_) -> bool:
    """Enable cache and pre-warm all 32 state combinations.

    Sets useCache=True on the Inference prim, then iterates through every
    velocity × car-config combination, running inference silently (preCaching=True
    suppresses notifications and skips writing results to the prim). vizMode is
    forced to Empty during the loop so no expensive visualization re-renders occur.
    After all states are cached (or if cancelled via stop_cache) the original
    AppState is restored and preCaching is cleared.
    """
    stage = get_context().get_stage()
    if not stage:
        return False
    app_prim = _app_state_prim()
    inf_prim = stage.GetPrimAtPath(_INFERENCE_PRIM)
    if not app_prim or not inf_prim or not inf_prim.IsValid():
        logger.error("start_cache: required prims not found")
        return False

    # Enable cache read-through and silent pre-caching mode.
    inf_prim.CreateAttribute("omni:rtwt:inference_cache:useCache",   Sdf.ValueTypeNames.Bool).Set(True)
    inf_prim.CreateAttribute("omni:rtwt:inference_cache:preCaching", Sdf.ValueTypeNames.Bool).Set(True)
    notification.set_caching(True)

    attrs = _get_app_state_attrs()  # full -> short
    short_to_full = {short: full for full, short in attrs.items()}

    # Save the current AppState so we can restore it when done.
    orig = {short: app_prim.GetAttribute(full).Get() for full, short in attrs.items()}

    # Force vizMode to Empty while caching to skip expensive viz re-renders.
    app_prim.GetAttribute(short_to_full["vizMode"]).Set("Empty")

    combos = _all_cache_states()
    total = len(combos)
    try:
        for i, combo in enumerate(combos):
            _send_cache_signal("caching", i, total)

            with Sdf.ChangeBlock():
                for key, value in combo.items():
                    app_prim.GetAttribute(short_to_full[key]).Set(value)

            await _wait_for_sync()
    finally:
        # Always restore original state and clear pre-caching mode.
        with Sdf.ChangeBlock():
            for short, value in orig.items():
                app_prim.GetAttribute(short_to_full[short]).Set(value)
        inf_prim.CreateAttribute("omni:rtwt:inference_cache:preCaching", Sdf.ValueTypeNames.Bool).Set(False)
        notification.set_caching(False)

    _send_cache_signal("cached", total, total)
    return True


@app.request
def stop_cache(**_) -> bool:
    """Disable cache read-through and reset the cache UI to idle."""
    stage = get_context().get_stage()
    if not stage:
        return False
    inf_prim = stage.GetPrimAtPath(_INFERENCE_PRIM)
    if inf_prim and inf_prim.IsValid():
        inf_prim.CreateAttribute("omni:rtwt:inference_cache:useCache", Sdf.ValueTypeNames.Bool).Set(False)
    _send_cache_signal("idle", 0, 0)
    return True
