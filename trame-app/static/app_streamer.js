// Page identity — set now and watch for trame resetting it
const _TITLE = 'Real Time Wind Tunnel Digital Twin';
document.title = _TITLE;
new MutationObserver(() => {
    if (document.title !== _TITLE) document.title = _TITLE;
}).observe(document.querySelector('title'), { childList: true });

const _favicon = document.createElement('link');
_favicon.rel = 'icon';
_favicon.href = '/static/favicon.svg';
document.head.appendChild(_favicon);

// Load the AppStreamer IIFE bundle (sets window.KitStreamer)
await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/static/kit-streamer.iife.js';
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
});

/**
 * Wraps KitStreamer.send() with a timeout so callers receive null instead of
 * hanging indefinitely when Kit hasn't responded within `ms` milliseconds.
 *
 * @param {string} eventType - Kit event name.
 * @param {object} payload   - Payload forwarded to Kit.
 * @param {number} ms        - Timeout in milliseconds (default 2000).
 * @returns {Promise<*>} Kit's response, or null on timeout.
 */
function sendWithTimeout(eventType, payload = {}, ms = 2000) {
    return Promise.race([
        window.KitStreamer.send(eventType, payload),
        new Promise(resolve => setTimeout(() => resolve(null), ms)),
    ]);
}

/**
 * Returns the bidirectional bridge keys (trame ↔ Kit).
 * Declared in app.py as `state.kit_bridge_keys`.
 *
 * @returns {string[]}
 */
function getBridgeKeys() {
    return window.trame.state.state.kit_bridge_keys ?? [];
}

/**
 * Returns the read-only keys synced Kit → trame only (never sent back to Kit).
 * Declared in app.py as `state.kit_read_keys`.
 *
 * @returns {string[]}
 */
function getReadKeys() {
    return window.trame.state.state.kit_read_keys ?? [];
}

/**
 * Apply a Kit state dict to trame for the given keys.
 * For object values (e.g. cmapVelocity, cmapPressure), dirty() is called
 * explicitly after set() to guarantee Python's @state.change fires even when
 * the dict content compares equal to the previous value.
 *
 * @param {object} data - Kit state dict.
 * @param {string[]} keys - Keys to apply.
 */
function applyKitState(data, keys) {
    for (const key of keys) {
        const val = data[key];
        if (val == null) continue;
        window.trame.state.set(key, val);
        if (typeof val === 'object') window.trame.state.dirty(key);
    }
}

// Guard that prevents the trame→Kit listener from echoing state back to Kit
// while a Kit→trame sync is in progress.
let _syncingFromKit = false;
let _applyingLocalPatch = false;
let _kitConnected = false;
let _pendingBridgeSend = false;
let _bridgeSendTimer = null;
let _bridgePrev = {};

function currentBridgeState() {
    const keys = getBridgeKeys();
    const ts = window.trame.state.state;
    return {
        keys,
        state: Object.fromEntries(keys.map(k => [k, ts[k]])),
    };
}

function bridgeStateChanged(keys, state) {
    return keys.some(k => state[k] !== _bridgePrev[k]);
}

function scheduleBridgeSend(delayMs = 500) {
    clearTimeout(_bridgeSendTimer);
    _bridgeSendTimer = setTimeout(
        () => sendBridgeStateToKit({ force: _pendingBridgeSend }),
        delayMs,
    );
}

function sendBridgeStateToKit({ force = false } = {}) {
    const { keys, state } = currentBridgeState();
    if (!force && !bridgeStateChanged(keys, state)) {
        return;
    }

    if (!_kitConnected || !window.KitStreamer?.send) {
        _pendingBridgeSend = true;
        scheduleBridgeSend();
        return;
    }

    const sentState = { ...state };
    _pendingBridgeSend = false;

    try {
        let settled = false;
        Promise.resolve(window.KitStreamer.send('set_state', { state: sentState }))
            .then(() => {
                settled = true;
                _bridgePrev = sentState;
            })
            .catch((error) => {
                settled = true;
                console.warn('[app_streamer] set_state failed, will retry:', error);
                _pendingBridgeSend = true;
                scheduleBridgeSend();
            });
        setTimeout(() => {
            if (settled) return;
            console.warn('[app_streamer] set_state timed out, will retry');
            _pendingBridgeSend = true;
            scheduleBridgeSend();
        }, 2500);
    } catch (error) {
        console.warn('[app_streamer] set_state threw, will retry:', error);
        _pendingBridgeSend = true;
        scheduleBridgeSend();
    }
}

function applyLocalStatePatch(patch) {
    _applyingLocalPatch = true;
    try {
        for (const [key, value] of Object.entries(patch)) {
            window.trame.state.set(key, value);
            if (value && typeof value === 'object') window.trame.state.dirty(key);
        }
    } finally {
        _applyingLocalPatch = false;
    }
    sendBridgeStateToKit();
}

function resetControlState() {
    const velocity = 25.0;
    const velocityOptions = window.trame.state.state.velocity_options ?? [];
    const velocityIndex = velocityOptions.indexOf(velocity);

    applyLocalStatePatch({
        vizMode: 'Streamlines',
        vizField: 'VelocityMagnitude',
        sliceDirection: 'X',
        sliderValue: 0,
        animatedStreaks: false,
        spoiler: 'On',
        rims: 'Standard',
        mirrors: 'On',
        velocity,
        velocity_index: velocityIndex >= 0 ? velocityIndex : 0,
    });
}

window.RTWTControls = {
    set(key, value) {
        applyLocalStatePatch({ [key]: value });
    },
    reset() {
        resetControlState();
    },
};

/**
 * Subscribes to Kit signals. Two signals are handled directly here as
 * generic conventions:
 *
 *   state_sync_signal — Kit pushes corrected bridge-key values back to trame
 *                       (e.g. after an async operation clamps or overrides
 *                       a requested state). Applied with _syncingFromKit guard
 *                       to avoid echoing back.
 *
 *   notification_signal — Kit pushes { active, message, kind } to show/hide
 *                         the trame notification banner. Transient notifications
 *                         (kind === 'transient') auto-dismiss after 2 s.
 *
 * All other signals are forwarded to the Python-side `on_kit_signal` trame
 * trigger, where app-specific handlers are registered with @on_kit_signal.
 *
 * Called once per connection inside onConnected.
 */
function registerKitSignals() {
    window.KitStreamer.onSignal('state_sync_signal', (data) => {
        _syncingFromKit = true;
        try {
            applyKitState(data, [...getBridgeKeys(), ...getReadKeys()]);
        } finally {
            _syncingFromKit = false;
        }
    });

    let _notifTimer = null;
    window.KitStreamer.onSignal('notification_signal', ({ active, message, kind }) => {
        clearTimeout(_notifTimer);
        window.trame.state.set('notification_active',  !!active);
        window.trame.state.set('notification_message', message || '');
        if (active && kind === 'transient') {
            _notifTimer = setTimeout(
                () => window.trame.state.set('notification_active', false), 2000);
        }
    });

    const signals = window.trame.state.state.kit_signals ?? [];
    for (const name of signals) {
        window.KitStreamer.onSignal(name, (data) => {
            _syncingFromKit = true;
            window.trame.trigger('on_kit_signal', [name, data])
                .finally(() => { _syncingFromKit = false; });
        });
    }
}

/**
 * Fetches Kit's available-options payload and forwards it verbatim to the
 * `apply_available_options` trame trigger. Interpretation lives on the
 * Python side — this function is transport only.
 *
 * Called from pullStateFromKit once Kit's Python handlers are known to be
 * responding, so no retry loop is needed here.
 */
async function pullAvailableOptionsFromKit() {
    const result = await sendWithTimeout('get_available_options', {}).catch(() => null);
    if (!result) {
        console.warn('[app_streamer] get_available_options returned no data');
        return;
    }
    console.log('[app_streamer] forwarding available options to trame:', result);
    window.trame.trigger('apply_available_options', [result]);
}

/**
 * Fetches Kit's current state (Kit → trame) and applies it to the bridge keys.
 * Retries with 500 ms backoff until Kit's Python handlers respond with a
 * non-empty state dict, up to 20 attempts.
 *
 * Called once per connection inside onConnected.
 */
function pullStateFromKit() {
    const trySync = async (attempt = 0) => {
        const kitState = await sendWithTimeout('get_state', {}).catch(() => null);
        if (!kitState || typeof kitState !== 'object' || Object.keys(kitState).length === 0) {
            if (attempt < 20) setTimeout(() => trySync(attempt + 1), 500);
            else console.warn('[app_streamer] get_state never returned data after 20 attempts');
            return;
        }
        console.log('[app_streamer] synced initial state from Kit:', kitState);
        _syncingFromKit = true;
        try {
            applyKitState(kitState, [...getBridgeKeys(), ...getReadKeys()]);
        } finally {
            _syncingFromKit = false;
        }
        if (!_pendingBridgeSend) {
            _bridgePrev = currentBridgeState().state;
        }
        pullAvailableOptionsFromKit();
    };
    trySync();
}

/**
 * Entry point. Connects to KitStreamer, registers Kit signal forwarders and
 * performs the initial state pull on connection. Also installs a trame state
 * listener (trame → Kit) that forwards diffs of the bridge keys to Kit's
 * set_state on every change.
 */
async function init() {
    const params = new URLSearchParams(location.search);
    const kitServer = params.get('server') || params.get('signalingServer') || null;
    console.log('[app_streamer] connecting to Kit at', kitServer ?? 'auto');
    window.KitStreamer.init(kitServer, {
        onConnected: () => {
            _kitConnected = true;
            registerKitSignals();
            pullStateFromKit();
            if (_pendingBridgeSend) {
                sendBridgeStateToKit({ force: true });
            }
        },
    });

    window.trame.state.addListener(() => {
        if (_syncingFromKit || _applyingLocalPatch) return;
        sendBridgeStateToKit();
    });
}

// Module scripts are deferred — DOM is ready, call init directly
init();
