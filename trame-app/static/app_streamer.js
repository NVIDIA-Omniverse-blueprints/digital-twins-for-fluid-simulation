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

// Explore and Compare keep independent state. Compare shows one fixed, pre-baked combo (the cached
// result sets were baked for it); Explore drives the live/variable combo. Entering Compare snapshots
// Explore's full state and pins the fixed combo (so the velocity-driven colormap matches the cached
// data); exiting restores Explore's full state. Compare retains its own last viz across visits.
const FIXED_COMBO = { velocity: 25, spoiler: 'On', rims: 'Standard', mirrors: 'On' };  // the baked combo
const COMPARE_VIZ_KEYS = ['vizMode', 'vizField', 'sliceDirection', 'sliderValue'];
let _exploreSnapshot = null;   // full Explore bridge state, restored on exit
let _compareVizSnapshot = null;  // Compare's own viz, restored on re-entry
function _snapshotViz() {
    const s = window.trame.state.state;
    return Object.fromEntries(COMPARE_VIZ_KEYS.map(k => [k, s[k]]));
}
function _snapshotAll() {
    const s = window.trame.state.state;
    return Object.fromEntries(getBridgeKeys().map(k => [k, s[k]]));
}

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

// ── Comparison view ──────────────────────────────────────────────────────────
// Comparison view actions. Everything is driven through window.RTWTControls.set — the SAME debounced
// set_state bridge the Explore panel uses. The `comparisonResultSet` AppState control is mapped on the
// Kit side (manifest callback → inference resultSetOverride) so result-set switching rides the same
// clean operator pass as a viz-mode change. No bespoke requests and no stage poking. app.py inline
// @click/@end handlers call ONLY these single-call methods, because Vue cannot compile multi-statement
// inline JS.
window.RTWTComparison = {
    enterView() {
        console.log('[RTWTComparison] enterView');
        // Only "both" has an Explore panel to snapshot and restore on exit; "compare" has none.
        if ((window.trame.state.state.ui_panels ?? 'both') === 'both') {
            _exploreSnapshot = _snapshotAll();
        }
        window.trame.state.set('comparison_active', true);
        window.trame.state.set('comparison_result_set', 'surrogate');
        // One patch → one set_state → one clean operator pass: pin the fixed baked combo (so the
        // colormap matches the cached data), restore Compare's last viz, and show the AI surrogate.
        const patch = { ...FIXED_COMBO, comparisonResultSet: 'surrogate' };
        if (_compareVizSnapshot) Object.assign(patch, _compareVizSnapshot);
        applyLocalStatePatch(patch);
    },
    exitView() {
        // Compare-only / explore-only have no Explore panel to return to — exit is a no-op.
        if ((window.trame.state.state.ui_panels ?? 'both') !== 'both') return;
        console.log('[RTWTComparison] exitView');
        _compareVizSnapshot = _snapshotViz();          // remember Compare's viz for the next enter
        window.trame.state.set('comparison_active', false);
        // Restore Explore's full state (its combo + viz) and clear the override → live combo returns.
        applyLocalStatePatch({ ...(_exploreSnapshot || {}), comparisonResultSet: 'off' });
    },
    // resultSet in {'ground_truth', 'surrogate', 'diff'}
    selectResultSet(resultSet) {
        console.log('[RTWTComparison] selectResultSet', resultSet);
        window.trame.state.set('comparison_result_set', resultSet);          // UI highlight
        if (resultSet === 'diff') {
            // Diff is Volume/Slice only (signed scalar deltas). Coerce a path mode to Volume in the
            // SAME patch so one set_state drives both — the binding engine picks the *Delta variant.
            const m = window.trame.state.state.vizMode;
            const patch = { comparisonResultSet: 'diff' };
            if (m !== 'Volume' && m !== 'Slice') patch.vizMode = 'Volume';
            applyLocalStatePatch(patch);
        } else {
            window.RTWTControls.set('comparisonResultSet', resultSet);       // drive the render
        }
    },
    // A viz change inside the comparison panel — identical to Explore's path.
    setViz(key, value) {
        console.log('[RTWTComparison] setViz', key, value);
        window.RTWTControls.set(key, value);
    },
    // Position slider: read the v_model'd value from live state, then set via the bridge.
    setPosition(key) {
        window.RTWTControls.set(key, window.trame.state.state[key]);
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
        const isActive = !!active;
        if (isActive) {
            // Populate the content before opening the snackbar so a fast signal
            // cannot render an active notification with an empty message.
            window.trame.state.set('notification_message', message || '');
            window.trame.state.set('notification_active', true);
        } else {
            // Vuetify keeps the snackbar mounted during its leave transition.
            // Retain the message until the next notification so that shell is
            // never visible with its content already cleared.
            window.trame.state.set('notification_active', false);
        }
        if (isActive && kind === 'transient') {
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
 * Fetches Kit's available-options payload and applies it directly to trame
 * state (velocity_options / spoiler_options / mirrors_options / rims_options /
 * precaching_available).
 *
 * Called from pullStateFromKit once Kit's Python handlers are known to be
 * responding; retries with backoff so a single dropped/slow response doesn't
 * leave the lite UI unrestricted (these options gate the rims/mirrors grey-out).
 */
async function pullAvailableOptionsFromKit(attempt = 0) {
    const result = await sendWithTimeout('get_available_options', {}).catch(() => null);
    if (!result) {
        if (attempt < 20) {
            setTimeout(() => pullAvailableOptionsFromKit(attempt + 1), 500);
            return;
        }
        console.warn('[app_streamer] get_available_options returned no data after retries');
        return;
    }
    // Apply directly to trame state — the same path applyKitState/state_sync_signal use.
    // Crucially, call dirty() after set() for ARRAY values: trame/Vue does not reliably detect a
    // change to an array/object reference without it (applyKitState does the same for colormap
    // dicts). Setting state directly is required here — a Python @ctrl.trigger round-trip does not
    // reliably populate these options.
    const opts = result.options || {};
    const setOpt = (key, val) => {
        window.trame.state.set(key, val);
        if (val && typeof val === 'object') window.trame.state.dirty(key);
    };
    setOpt('velocity_options', opts.velocity || []);
    setOpt('spoiler_options', opts.spoiler ?? null);
    setOpt('mirrors_options', opts.mirrors ?? null);
    setOpt('rims_options', opts.rims ?? null);
    window.trame.state.set('precaching_available', result.precaching_available !== false);
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
        // Compare-only: no Explore tab exists to enter Compare from, so enter it once the initial
        // state is synced — pins the fixed combo and shows the default result set.
        if ((window.trame.state.state.ui_panels ?? 'both') === 'compare') {
            window.RTWTComparison.enterView();
        }
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
