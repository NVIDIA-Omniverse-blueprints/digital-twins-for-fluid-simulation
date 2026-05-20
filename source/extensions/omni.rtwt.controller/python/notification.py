import logging

import carb
import carb.eventdispatcher
import carb.events
import omni.kit.app
import omni.kit.livestream.messaging as messaging
from omni.usd import get_context

logger = logging.getLogger(__name__)

_EVT_OPERATOR_BEGIN = "omni.cae.viz@operator_begin"
_EVT_OPERATOR_END = "omni.cae.viz@operator_end"
_NOTIFICATION_SIGNAL = "notification_signal"

# Prim paths currently mid-inference (set non-empty = inferencing active)
_active_inference_prims: set[str] = set()

# Subscriptions must be retained or they are immediately deleted
_begin_sub = None
_end_sub = None
_notification_signal_type = None
_stream = None

# When True, suppress inference start/end notifications (used during pre-caching)
_caching: bool = False


def set_caching(active: bool) -> None:
    global _caching
    _caching = active


def _has_inference_api(prim_path: str) -> bool:
    stage = get_context().get_stage()
    if not stage:
        return False
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return False
    return any("RtwtInferenceAPI" in str(s) for s in prim.GetAppliedSchemas())


def _send_notification(active: bool, message: str = "", kind: str = "persistent") -> None:
    if _stream is None or _notification_signal_type is None:
        return
    _stream.dispatch(
        _notification_signal_type,
        payload={"active": active, "message": message, "kind": kind},
    )
    _stream.pump()


def _on_operator_begin(e: carb.eventdispatcher.Event) -> None:
    if _caching:
        return
    prim_path = e.payload.get("prim_path", "")
    if not prim_path or not _has_inference_api(prim_path):
        return
    was_empty = len(_active_inference_prims) == 0
    _active_inference_prims.add(prim_path)
    if was_empty:
        logger.debug("Inference started on %s — sending notification begin", prim_path)
        _send_notification(active=True, message="Inferencing ...")


def _on_operator_end(e: carb.eventdispatcher.Event) -> None:
    if _caching:
        return
    prim_path = e.payload.get("prim_path", "")
    if prim_path not in _active_inference_prims:
        return
    _active_inference_prims.discard(prim_path)
    if len(_active_inference_prims) == 0:
        logger.debug("Inference ended on %s — sending notification end", prim_path)
        _send_notification(active=False)


def setup() -> None:
    global _begin_sub, _end_sub, _notification_signal_type, _stream

    messaging.register_event_type_to_send(_NOTIFICATION_SIGNAL)

    app = omni.kit.app.get_app()
    _stream = app.get_message_bus_event_stream()
    _notification_signal_type = carb.events.type_from_string(_NOTIFICATION_SIGNAL)

    dispatcher = carb.eventdispatcher.get_eventdispatcher()
    _begin_sub = dispatcher.observe_event(
        order=0,
        event_name=_EVT_OPERATOR_BEGIN,
        on_event=_on_operator_begin,
        observer_name="rtwt.notification.operator_begin",
    )
    _end_sub = dispatcher.observe_event(
        order=0,
        event_name=_EVT_OPERATOR_END,
        on_event=_on_operator_end,
        observer_name="rtwt.notification.operator_end",
    )
    logger.info("Notification system ready")


def teardown() -> None:
    global _begin_sub, _end_sub, _stream, _notification_signal_type

    _begin_sub = None
    _end_sub = None

    _active_inference_prims.clear()
    _stream = None
    _notification_signal_type = None
