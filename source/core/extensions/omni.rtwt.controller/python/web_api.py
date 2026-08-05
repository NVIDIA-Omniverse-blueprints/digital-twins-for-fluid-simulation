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
import itertools
from logging import getLogger
from . import ovapi
from . import notification
from . import control_registry
from pxr import Sdf
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

_DEFAULT_APP_STATE_PRIM = "/World/AppState"
_DEFAULT_INFERENCE_PRIM = "/World/Inference"


def _get_app_state_attrs() -> dict[str, str]:
    """Return the workflow's unambiguous full attribute name -> web short-key mapping.

    Only manifest-declared controls are part of the public state contract.  Schema attributes that
    are not controls must not leak into get_state/set_state, and short-key uniqueness is enforced
    by :class:`ControlRegistry`.
    """
    registry = control_registry.get_workflow_registry()
    return registry.full_to_short() if registry else {}


def _workflow_prim_path(name: str, default: str) -> str:
    registry = control_registry.get_workflow_registry()
    return str(getattr(registry.manifest, name)) if registry else default


def _app_state_prim_path() -> str:
    return _workflow_prim_path("app_state_prim", _DEFAULT_APP_STATE_PRIM)


def _inference_prim_path() -> str:
    return _workflow_prim_path("inference_prim", _DEFAULT_INFERENCE_PRIM)


_CACHE_STATE_SIGNAL = "cache_state_signal"
_EVT_SYNC_END = "omni.cae.viz@sync_end"


def _workflow_readouts():
    """The configured workflow's readout specs (empty when no workflow is loaded)."""
    reg = control_registry.get_workflow_registry()
    return reg.manifest.readouts if reg else ()


def _colormap_prims() -> dict:
    """field -> colormap prim path, derived from the manifest's colormap readouts.

    Empty when no workflow is loaded.
    """
    return {
        r.field: f"/World/Colormaps/{r.domain_source}"
        for r in _workflow_readouts()
        if r.type == "colormap" and r.field and r.domain_source
    }


def _supported_velocities() -> list:
    """Wind speeds the backend supports, from the velocity control's cache_values.

    Empty when there is no workflow / no velocity control.
    """
    reg = control_registry.get_workflow_registry()
    if reg:
        for c in reg.controls():
            if c.short_key == "velocity":
                vals = c.spec.cache_values or c.spec.values
                if vals:
                    return [float(v) for v in vals]
    return []


messaging.register_event_type_to_send(_CACHE_STATE_SIGNAL)


def _app_state_prim(stage=None):
    stage = stage or get_context().get_stage()
    prim = stage.GetPrimAtPath(_app_state_prim_path()) if stage else None
    return prim if (prim and prim.IsValid()) else None


def _inference_prim(stage):
    prim = stage.GetPrimAtPath(_inference_prim_path()) if stage else None
    return prim if (prim and prim.IsValid()) else None


def _control_attribute(prim, control_id: str):
    """Resolve a manifest control id to its authored app-state attribute."""
    registry = control_registry.get_workflow_registry()
    control = registry.get(control_id) if registry else None
    if not control or not control.schema_attr:
        return None
    return prim.GetAttribute(control.schema_attr)


def _send_cache_signal(state: str, progress: int, total: int) -> None:
    # Kit 110's messaging extension forwards outbound events only via the carb
    # eventdispatcher, which queue_event() feeds; the legacy message-bus dispatch
    # does not reach it (see ovapi.OmniverseAPI.request).
    omni.kit.app.queue_event(_CACHE_STATE_SIGNAL, {"state": state, "progress": progress, "total": total})


def _all_cache_states() -> list[dict]:
    """All pre-cache state combinations: the Cartesian product of every inference-role control's
    cache_values, keyed by short key.

    Control order follows manifest order, which fixes the enumeration order of the product.
    """
    reg = control_registry.get_workflow_registry()
    if reg is None:
        return []
    axes = [(c.short_key, list(c.spec.cache_values)) for c in reg.inference_controls() if c.spec.cache_values]
    if not axes:
        return []
    keys = [k for k, _ in axes]
    return [dict(zip(keys, combo)) for combo in itertools.product(*(v for _, v in axes))]


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
    prim_path = _colormap_prims().get(viz_field)
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

    app_prim = _app_state_prim(stage)
    if name == "FullOrbit_Camera":
        viewport = get_active_viewport()
        viewport.camera_path = "/World/Cameras/FullOrbit_Camera"
        if app_prim:
            play_attr = _control_attribute(app_prim, "playAnimation")
            if play_attr:
                play_attr.Set(not play_attr.Get())
    else:
        if app_prim:
            play_attr = _control_attribute(app_prim, "playAnimation")
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
        options["velocity"] = _supported_velocities()
    return {
        "enforced": enforced,
        "options": options,
        "precaching_available": not enforced,
    }


def _enforced_cache_options() -> dict:
    """When the offline cache is enforced (lite), return {short_key: {str value, ...}} of the
    cache-backed values per restricted axis. Empty when unrestricted (standard, or
    generate-on-miss) so the guard fails open."""
    from omni.rtwt.inference.inference import scan_offline_cache_options

    scan = scan_offline_cache_options() or {}
    if not scan.get("enforced"):
        return {}
    return {key: {str(v) for v in values} for key, values in (scan.get("options") or {}).items()}


def _value_allowed(value, allowed: set) -> bool:
    """Membership test tolerant of int/float spelling (e.g. 50 vs 50.0)."""
    if str(value) in allowed:
        return True
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return False
    return any(abs(fv - float(a)) < 1e-9 for a in allowed if _is_number(a))


def _is_number(s) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _compose_control_manifest(registry, stage) -> dict:
    """Compose the control-manifest wire shape from a registry + stage (the testable core of
    ``get_control_manifest``)."""
    from omni.rtwt.inference.inference import scan_offline_cache_options

    knobs = []
    if registry:
        for c in registry.controls():
            spec = c.spec
            knob = {
                "key": c.short_key,
                "label": spec.label,
                "group": spec.group,
                "role": spec.role,
                "widget": spec.widget,
                "unit": spec.unit,
                "visibleWhen": spec.visible_when or None,
            }
            if spec.bounds:
                knob["values"] = dict(spec.bounds)
            elif spec.values:
                knob["values"] = list(spec.values)
            elif c.allowed_tokens:
                knob["values"] = list(c.allowed_tokens)
            if spec.images:
                knob["images"] = dict(spec.images)
            knobs.append(knob)

    readouts = []
    for r in (registry.manifest.readouts if registry else ()):
        entry = {"key": r.key, "type": r.type, "label": r.label}
        if r.type == "colormap":
            entry["domainSource"] = r.domain_source
            entry["payload"] = _get_colormap(stage, r.field) if stage else None
        readouts.append(entry)

    views = []
    seen = set()
    for v in (registry.manifest.views if registry else ()):
        views.append({"name": v.name, "thumbnail": v.thumbnail or None, "onSelect": v.on_select or None})
        seen.add(v.name)
    if stage:
        for path in utils.get_rt_stage(stage).GetPrimsWithTypeName("Camera"):
            cam = Sdf.Path(str(path)).name
            if cam not in seen:
                views.append({"name": cam, "thumbnail": None, "onSelect": None})
                seen.add(cam)

    enforced = bool((scan_offline_cache_options() or {}).get("enforced"))
    return {"knobs": knobs, "readouts": readouts, "views": views, "features": {"precaching": not enforced}}


@app.request
def get_control_manifest(**_) -> dict:
    """The generic **control contract**: the configured workflow's controls (knobs), readouts, and
    views in one response — the functional surface a UI consumes.

    A use-case ships its own UI; presentation is legitimately custom. That UI consumes this manifest
    plus get_state / set_state and the Kit->client signals over the use-case-agnostic
    app_streamer.js transport, mapping each knob's ``widget`` / ``values`` to its own controls. The
    contract carries no specialization vocabulary — exercised for a non-aero workflow in
    tests/test_control_manifest.py."""
    return _compose_control_manifest(control_registry.get_workflow_registry(), get_context().get_stage())


@app.request
def get_state(**_) -> dict:
    prim = _app_state_prim()
    if not prim:
        return {}
    attrs = _get_app_state_attrs()
    state = {}
    for full, short in attrs.items():
        attr = prim.GetAttribute(full)
        if attr:
            state[short] = attr.Get()
    if stage := get_context().get_stage():
        for r in _workflow_readouts():
            if r.type == "colormap":
                if cmap := _get_colormap(stage, r.field):
                    state[r.key] = cmap
    return state


@app.request
@ovapi.exclusive
@listener.exclusive_with_sync
async def set_state(state: dict) -> bool:
    prim = _app_state_prim()
    if not prim:
        logger.error("AppState prim not found at workflow path %s", _app_state_prim_path())
        return False
    short_to_full = {short: full for full, short in _get_app_state_attrs().items()}
    # When the offline cache is enforced (lite), refuse inference-axis values outside the cached
    # set so the surrogate state never leaves what the shipped cache can serve — otherwise the
    # geometry would change but the result would freeze on a cache miss. The frontend greys these
    # out; this is the server-side guarantee. Only axes present in the cache sidecars are
    # restricted, so visualization controls (vizMode, etc.) are unaffected.
    allowed = _enforced_cache_options()
    with Sdf.ChangeBlock():
        for key, value in state.items():
            full = short_to_full.get(key)
            if not full:
                logger.warning("Unknown AppState attribute: %s", key)
                continue
            if key in allowed and not _value_allowed(value, allowed[key]):
                logger.warning(
                    "Ignoring %s=%r: not in the offline cache (lite restricts %s to %s)",
                    key, value, key, sorted(allowed[key]),
                )
                continue
            prim.GetAttribute(full).Set(value)
    return True


@app.request
@ovapi.exclusive
async def start_cache(**_) -> bool:
    """Enable cache and pre-warm every inference-input combination.

    Sets useCache=True on the Inference prim, then iterates the Cartesian product of the
    inference-role controls' cache_values, running inference silently (preCaching=True
    suppresses notifications and skips writing results to the prim). vizMode is
    forced to Empty during the loop so no expensive visualization re-renders occur.
    After all states are cached (or if cancelled via stop_cache) the original
    AppState is restored and preCaching is cleared.
    """
    stage = get_context().get_stage()
    if not stage:
        return False
    app_prim = _app_state_prim(stage)
    inf_prim = _inference_prim(stage)
    if not app_prim or not inf_prim:
        logger.error(
            "start_cache: required workflow prims not found (app_state_prim=%s, inference_prim=%s)",
            _app_state_prim_path(),
            _inference_prim_path(),
        )
        return False

    # Enable cache read-through and silent pre-caching mode.
    inf_prim.CreateAttribute("omni:rtwt:inference_cache:useCache",   Sdf.ValueTypeNames.Bool).Set(True)
    inf_prim.CreateAttribute("omni:rtwt:inference_cache:preCaching", Sdf.ValueTypeNames.Bool).Set(True)
    notification.set_caching(True)

    attrs = _get_app_state_attrs()  # full -> short
    short_to_full = {short: full for full, short in attrs.items()}

    # Save the current AppState so we can restore it when done.
    orig = {}
    for full, short in attrs.items():
        attr = app_prim.GetAttribute(full)
        if attr:
            orig[short] = attr.Get()

    # Force vizMode to Empty while caching to skip expensive viz re-renders when this workflow
    # declares that control.  Pre-caching itself is generic and does not require one.
    if viz_mode_attr := short_to_full.get("vizMode"):
        app_prim.GetAttribute(viz_mode_attr).Set("Empty")

    combos = _all_cache_states()
    total = len(combos)
    try:
        for i, combo in enumerate(combos):
            _send_cache_signal("caching", i, total)

            with Sdf.ChangeBlock():
                for key, value in combo.items():
                    full = short_to_full.get(key)
                    if not full:
                        raise RuntimeError(
                            f"cache control '{key}' has no schema_attr mapping; validate the "
                            "workflow manifest before pre-caching"
                        )
                    app_prim.GetAttribute(full).Set(value)

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
    inf_prim = _inference_prim(stage)
    if inf_prim:
        inf_prim.CreateAttribute("omni:rtwt:inference_cache:useCache", Sdf.ValueTypeNames.Bool).Set(False)
    _send_cache_signal("idle", 0, 0)
    return True
