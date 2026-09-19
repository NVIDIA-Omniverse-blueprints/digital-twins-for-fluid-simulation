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
    // app.py versions this module URL; keep the transport bundle on that version too.
    s.src = '/static/kit-streamer.iife.js' + new URL(import.meta.url).search;
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
});

/**
 * KitStreamer owns timeout cleanup, including retiring late response handlers.
 *
 * @param {string} eventType - Kit event name.
 * @param {object} payload   - Payload forwarded to Kit.
 * @param {number} ms        - Timeout in milliseconds (default 2000).
 * @returns {Promise<*>} Kit's response, or null on timeout.
 */
function sendWithTimeout(eventType, payload = {}, ms = 2000) {
    return window.KitStreamer.send(eventType, payload, ms);
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
let _kitReady = false;
let _bridgeSending = false;
let _connectionGeneration = 0;
let _initialSyncTimer = null;
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
    _bridgeSendTimer = setTimeout(sendBridgeStateToKit, delayMs);
}

async function sendBridgeStateToKit() {
    // Never send frontend defaults before Kit has supplied its initial state.
    // One request at a time also coalesces slider/button changes while Kit is busy.
    if (!_kitConnected || !_kitReady || _bridgeSending) return;
    const { keys, state } = currentBridgeState();
    if (!bridgeStateChanged(keys, state)) return;

    const sentState = { ...state };
    const generation = _connectionGeneration;
    _bridgeSending = true;
    let accepted = false;
    try {
        accepted = await sendWithTimeout('set_state', { state: sentState }) === true;
    } catch (error) {
        console.warn('[app_streamer] set_state failed, will retry:', error);
    }
    if (generation !== _connectionGeneration) return;
    _bridgeSending = false;
    // A busy Kit handler returns null. A timeout can also mean Kit applied the
    // write but its reply was lost, so the previous baseline is no longer safe.
    _bridgePrev = accepted ? sentState : {};
    const latest = currentBridgeState();
    if (bridgeStateChanged(latest.keys, latest.state)) {
        scheduleBridgeSend(accepted ? 0 : 500);
    }
}

function applyLocalStatePatch(patch) {
    if (!_kitReady) return;
    _applyingLocalPatch = true;
    try {
        for (const [key, value] of Object.entries(patch)) {
            window.trame.state.set(key, value);
            if (value && typeof value === 'object') window.trame.state.dirty(key);
        }
    } finally {
        _applyingLocalPatch = false;
    }
    scheduleBridgeSend(0);
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
        // A server update must not overwrite a newer local selection awaiting ack.
        const state = window.trame.state.state;
        const keys = getBridgeKeys().filter(key => !_bridgeSending && state[key] === _bridgePrev[key]);
        _syncingFromKit = true;
        try {
            applyKitState(data, [...keys, ...getReadKeys()]);
            for (const key of keys) _bridgePrev[key] = state[key];
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
 * Applied together with the initial state before enabling controls.
 */
function applyAvailableOptions(result) {
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
 * Polls for the lifetime of the connection, with backoff capped at five seconds.
 * Cold renderer startup can take several minutes; exhausting a short retry
 * budget would leave the velocity slider and Lite restrictions unset forever.
 *
 * Called once per connection inside onConnected.
 */
async function pullStateFromKit(generation, attempt = 0) {
    const isCurrent = () => _kitConnected && generation === _connectionGeneration;
    if (!isCurrent()) return;
    const kitState = await sendWithTimeout('get_state', {}).catch(() => null);
    if (!isCurrent()) return;
    const hasState = kitState && getBridgeKeys().some(key => Object.hasOwn(kitState, key));
    const options = hasState
        ? await sendWithTimeout('get_available_options', {}).catch(() => null)
        : null;
    if (!isCurrent()) return;
    if (!hasState || !Array.isArray(options?.options?.velocity) || !options.options.velocity.length) {
        _initialSyncTimer = setTimeout(
            () => pullStateFromKit(generation, attempt + 1),
            Math.min(500 * 2 ** Math.min(attempt, 4), 5000),
        );
        return;
    }
    console.log('[app_streamer] synced initial state from Kit:', kitState);
    _syncingFromKit = true;
    try {
        applyKitState(kitState, [...getBridgeKeys(), ...getReadKeys()]);
        applyAvailableOptions(options);
        _bridgePrev = currentBridgeState().state;
        _kitReady = true;
        window.trame.state.set('kit_ready', true);
    } finally {
        _syncingFromKit = false;
    }
    // Compare-only has no Explore tab to enter Compare from.
    if ((window.trame.state.state.ui_panels ?? 'both') === 'compare') {
        window.RTWTComparison.enterView();
    }
}

function resetConnection(connected) {
    _connectionGeneration++;
    _kitConnected = connected;
    _kitReady = false;
    _bridgeSending = false;
    _bridgePrev = {};
    clearTimeout(_initialSyncTimer);
    clearTimeout(_bridgeSendTimer);
    window.trame.state.set('kit_ready', false);
    window.trame.state.set('kit_status', connected ? 'Loading the simulation…' : 'Connecting to the simulation…');
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
            resetConnection(true);
            registerKitSignals();
            pullStateFromKit(_connectionGeneration);
        },
        onDisconnected: () => resetConnection(false),
    });

    window.trame.state.addListener(() => {
        if (!_kitReady || _syncingFromKit || _applyingLocalPatch) return;
        scheduleBridgeSend(0);
    });
}

// Module scripts are deferred — DOM is ready, call init directly
init();
