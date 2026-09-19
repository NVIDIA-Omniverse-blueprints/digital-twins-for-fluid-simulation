/**
 * kit-streamer — thin wrapper around the NVIDIA Omniverse WebRTC streaming library.
 *
 * Exposes window.KitStreamer with three public methods:
 *   init(kitServer, { onConnected, onDisconnected }) — connect to a Kit streaming server
 *   send(eventType, payload)          — send a request and await the response
 *   onSignal(eventType, handler)      — register a handler for Kit→client push events
 *
 * Built as an IIFE by Vite; output lives in trame-app/static/kit-streamer.iife.js.
 */

import { AppStreamer, StreamType } from '@nvidia/omniverse-webrtc-streaming-library';

let connected = false;

function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function isLocalHostname(hostname = window.location.hostname) {
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
}

function parseBoolean(value) {
    if (typeof value === 'boolean') return value;
    if (value == null || value === '') return null;

    switch (String(value).trim().toLowerCase()) {
        case '1':
        case 'true':
        case 'yes':
        case 'on':
            return true;
        case '0':
        case 'false':
        case 'no':
        case 'off':
            return false;
        default:
            return null;
    }
}

function parsePort(value) {
    if (value == null || value === '' || value === 'auto') return null;
    const port = Number(value);
    return Number.isInteger(port) && port > 0 ? port : null;
}

function getPagePort() {
    const pagePort = parsePort(window.location.port);
    if (pagePort) return pagePort;
    return window.location.protocol === 'https:' ? 443 : 80;
}

function getQueryValue(params, ...names) {
    for (const name of names) {
        const value = params.get(name);
        if (value != null && value !== '') return value;
    }
    return '';
}

function resolveStreamConfig(kitServer, options = {}) {
    const params = new URLSearchParams(window.location.search);
    const trameConfig = window.trame?.state?.state?.kit_stream_config ?? {};
    const configuredServer = getQueryValue(params, 'server', 'signalingServer')
        || options.signalingServer
        || trameConfig.signalingServer;
    const signalingServer = kitServer
        || configuredServer
        || (isLocalHostname() ? '127.0.0.1' : window.location.hostname);

    const configuredPort = getQueryValue(params, 'signalingPort')
        || options.signalingPort
        || trameConfig.signalingPort;
    const signalingPort = parsePort(configuredPort)
        || (configuredPort === 'auto-proxy' ? getPagePort() : null)
        || (window.location.protocol === 'https:' && !isLocalHostname() ? 443 : 49100);

    const configuredForceWSS = getQueryValue(params, 'forceWSS')
        || options.forceWSS
        || trameConfig.forceWSS;
    const forceWSS = parseBoolean(configuredForceWSS)
        ?? (window.location.protocol === 'https:' && !isLocalHostname());

    const configuredMediaServer = getQueryValue(params, 'mediaServer')
        || options.mediaServer
        || trameConfig.mediaServer;
    const publicIp = getQueryValue(params, 'publicIp') || trameConfig.publicIp;
    let mediaServer = configuredMediaServer;
    if (!mediaServer || mediaServer === 'auto' || mediaServer === 'auto-public') {
        mediaServer = window.location.protocol === 'https:' && !isLocalHostname() && publicIp
            ? publicIp
            : signalingServer;
    }

    return { signalingServer, signalingPort, mediaServer, forceWSS };
}

/**
 * Connect to a Kit streaming server and mount the video/audio streams onto the
 * DOM elements with IDs "remote-video" and "remote-audio".
 *
 * @param {string|null} kitServer - Hostname or IP of the Kit server.
 *   Defaults to window.location.hostname when null/undefined.
 * @param {{ onConnected?: () => void, onDisconnected?: () => void, signalingPort?: number|string, mediaServer?: string, forceWSS?: boolean|string }} [options]
 *   onConnected — called once the stream is up and the initial resize has been sent.
 */
function init(kitServer, { onConnected, onDisconnected, ...options } = {}) {
    const disconnect = () => {
        connected = false;
        for (const { resolve, timer } of _pending.values()) {
            clearTimeout(timer);
            resolve(null);
        }
        _pending.clear();
        onDisconnected?.();
    };
    const stream = resolveStreamConfig(kitServer, options);
    // Kit treats the dimensions passed at connect time as the maximum render resolution,
    // so we use the full screen size here. Subsequent resize() calls can go smaller but
    // not larger than this initial value. Width must be divisible by 4, height by 2
    // (WebRTC encoder alignment requirement).
    const width = Math.floor(screen.width / 4) * 4;
    const height = Math.floor(screen.height / 2) * 2;

    AppStreamer.connect({
        streamSource: StreamType.DIRECT,
        streamConfig: {
            videoElementID: 'remote-video',
            audioElementID: 'remote-audio',
            signalingServer: stream.signalingServer,
            signalingPort: stream.signalingPort,
            mediaServer: stream.mediaServer,
            forceWSS: stream.forceWSS,
            autoLaunch: true,
            cursor: 'free',
            mic: false,
            width,
            height,
            fps: 60,
            authenticate: false,
            maxReconnects: 20,
            nativeTouchEvents: true,
            localizeTextInput: true,
            onStart: (msg) => {
                console.info('KitStreamer: stream started', msg);
                if (msg?.action === 'start' && msg?.status === 'success') {
                    connected = true;
                    console.log('[KitStreamer] initial resize', window.innerWidth, 'x', window.innerHeight);
                    AppStreamer.resize(window.innerWidth, window.innerHeight);
                    onConnected?.();
                }
            },
            onUpdate: (msg) => { console.debug('KitStreamer: update', msg); },
            // Custom events carry both request responses and one-way signals from Kit.
            onCustomEvent: (msg) => { console.debug('KitStreamer: custom event', msg); _onResponse(msg); _dispatchSignal(msg); },
            onStop: disconnect,
            onTerminate: disconnect,
        },
    }).catch(error => {
        console.error(error);
        disconnect();
    });

    // Keep the remote viewport in sync with the browser window.
    window.addEventListener('resize', debounce(() => {
        if (connected) {
            console.log('[KitStreamer] resize', window.innerWidth, 'x', window.innerHeight);
            AppStreamer.resize(window.innerWidth, window.innerHeight);
        }
    }, 300));
}

// --- Request/response channel -------------------------------------------------
// Kit uses a correlation id to match responses to requests. Each send() call
// stashes a Promise resolver in _pending keyed by id; _onResponse() retrieves
// and fulfills it when the matching response arrives via onCustomEvent.

let _requestId = 0;
const _pending = new Map();

/**
 * Send a request to Kit and return a Promise that resolves with the response payload.
 * Resolves with null when disconnected or timed out. Retires the request in
 * either case so polling through a long startup cannot accumulate resolvers.
 *
 * The message sent over the wire has the shape:
 *   { event_type: "<eventType>_request", payload: { ...payload, id } }
 *
 * Kit is expected to reply with:
 *   { event_type: "<eventType>_response", payload: { id, response: <result> } }
 *
 * @param {string} eventType
 * @param {object} [payload={}]
 * @param {number} [timeoutMs=2000]
 * @returns {Promise<any>}
 */
function send(eventType, payload = {}, timeoutMs = 2000) {
    if (!connected) return Promise.resolve(null);
    const id = _requestId++;
    const msg = JSON.stringify({
        event_type: `${eventType}_request`,
        payload: { ...payload, id },
    });
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            _pending.delete(id);
            resolve(null);
        }, timeoutMs);
        _pending.set(id, { resolve, timer });
        try {
            AppStreamer.sendMessage(msg);
        } catch (error) {
            clearTimeout(timer);
            _pending.delete(id);
            reject(error);
        }
    });
}

/** @param {object} msg - Raw message from onCustomEvent. */
function _onResponse(msg) {
    // Kit 110's messaging envelope carries the correlation id at the top level
    // (msg.id); older builds nested it under payload.id. Accept both — `??` (not
    // `||`) so that id 0, the very first request, is preserved.
    const id = msg?.id ?? msg?.payload?.id;
    const pending = _pending.get(id);
    if (pending) {
        _pending.delete(id);
        clearTimeout(pending.timer);
        // null is a meaningful busy/rejected response, not a missing envelope.
        const payload = msg?.payload;
        pending.resolve(payload && Object.hasOwn(payload, 'response') ? payload.response : payload);
    }
}

// --- Signal channel -----------------------------------------------------------
// One-way push events from Kit to the client (no request id, no reply expected).

const _signalHandlers = new Map();

/**
 * Register a handler for a Kit→client push event (signal).
 * Only one handler per eventType is kept; registering again replaces the previous one.
 *
 * @param {string} eventType - The event_type string sent by Kit.
 * @param {(payload: object) => void} handler
 */
function onSignal(eventType, handler) {
    _signalHandlers.set(eventType, handler);
}

/** @param {object} msg - Raw message from onCustomEvent. */
function _dispatchSignal(msg) {
    const handler = _signalHandlers.get(msg?.event_type);
    if (handler) handler(msg?.payload ?? {});
}

window.KitStreamer = { init, send, _onResponse, onSignal };
