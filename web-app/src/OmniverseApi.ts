import { AppStreamer, StreamType } from '@nvidia/omniverse-webrtc-streaming-library';

export interface TurnConfig {
    urls: string;
    username: string;
    credential: string;
}

export interface OmniverseStreamConfig {
    source: "local",
    videoElementId: string,
    audioElementId: string,
    messageElementId: string,
    urlLocation: {
        search: string
    },
    turn?: TurnConfig,
    forceWSS?: boolean,
}


export interface OmniverseStreamMessage {
    event_type: string,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    payload: Record<string, any>,
}

export type StreamHandlerCallback = (message: OmniverseStreamMessage) => void

export enum OmniverseStreamStatus {
    waiting,
    connecting,
    connected,
    error
}


export class OmniverseAPI {
    static requestId: number = 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    requestResponses: Record<number, Record<any, any>> = {};
    signalHandlers: Record<string, StreamHandlerCallback> = {};

    public constructor(
        config: OmniverseStreamConfig,
        onStart: StreamHandlerCallback | null = null,
        onUpdate: StreamHandlerCallback | null = null,
        onCustom: StreamHandlerCallback | null = null,
        onStop: StreamHandlerCallback | null = null,
        onTerminate: StreamHandlerCallback | null = null,
    ) {

        const params = new URLSearchParams(config.urlLocation.search);

        const server = params.get("server") ?? window.location.hostname;
        const width = Number(params.get("width") ?? 1920);
        const height = Number(params.get("height") ?? 1080);
        const fps = Number(params.get("fps") ?? 60);

        const signalingPort = Number(params.get("signalingPort") ?? 49100);
        const mediaPortParam = params.get("mediaPort");
        const mediaPort = mediaPortParam != null ? Number(mediaPortParam) : undefined;
        const forceWSS = config.forceWSS ?? false;

        // When a TURN relay is configured, monkey-patch RTCPeerConnection so
        // every connection the NVIDIA streaming library creates includes the
        // relay server. This forces all media through the TURN-TLS tunnel,
        // bypassing the UDP ingress limitation on OpenShift Routes.
        if (config.turn?.urls) {
            const turnServer: RTCIceServer = {
                urls: config.turn.urls,
                username: config.turn.username,
                credential: config.turn.credential,
            };
            const NativeRTCPC = window.RTCPeerConnection;
            const Patched = function (this: RTCPeerConnection, rtcConfig?: RTCConfiguration) {
                const patched: RTCConfiguration = { ...(rtcConfig || {}) };
                patched.iceServers = [...(patched.iceServers || []), turnServer];
                patched.iceTransportPolicy = "relay";
                return new NativeRTCPC(patched);
            } as unknown as typeof RTCPeerConnection;
            Patched.prototype = NativeRTCPC.prototype;
            Object.setPrototypeOf(Patched, NativeRTCPC);
            window.RTCPeerConnection = Patched;
            console.info("[OmniverseAPI] TURN relay injected:", config.turn.urls);
        }

        const streamConfig = {
            videoElementID: config.videoElementId,
            audioElementID: config.audioElementId,
            signalingServer: server,
            signalingPort,
            ...(config.turn?.urls ? {} : { mediaServer: server }),
            ...(mediaPort != null ? { mediaPort } : {}),
            ...(forceWSS ? { forceWSS: true } : {}),
            auotLaunch: true,
            cursor: 'free' as const,
            mic: false,
            width,
            height,
            fps,
            authenticate: false,
            maxReconnects: 20,
            nativeTouchEvents: true,
            localizeTextInput: true,

            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onStart: (msg: any) => { onStart?.(msg); },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onUpdate: (msg: any) => { onUpdate?.(msg); },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onCustomEvent: (msg: any) => {
                console.log(msg);
                const event_type = msg.event_type;

                if (event_type === "inference_complete_signal") {
                    this.signalHandlers[event_type]?.(msg.payload.signal);
                }

                const isResponse = 'id' in msg.payload;
                if (isResponse) {
                    const id: number = msg.payload['id'];
                    this.requestResponses[id] = msg;
                    onCustom?.(msg);
                } else {
                    const event_type = msg.event_type;
                    if (event_type in this.signalHandlers) {
                        const signalMsg = msg.payload.signal;
                        this.signalHandlers[event_type](signalMsg);
                    } else {
                        console.debug(`Unhandled signal "${event_type.replace("_signal", "")}"`);
                    }
                }
            },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onStop: (msg: any) => { onStop?.(msg); },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onTerminate: (msg: any) => {onTerminate?.(msg); },
        };

        const streamProps = {
            streamSource: StreamType.DIRECT,
            streamConfig
        };

        AppStreamer.connect(streamProps)
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            .then((result: any) => {
                console.info(result);
            })
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            .catch((error: any) => {
                console.error(error);
            });
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    async request(event_type: string, payload?: any, intervalMs: number = 1, timeoutMs: number = 5000): Promise<OmniverseStreamMessage> {
        const id = OmniverseAPI.requestId++;
        payload = payload ?? {};
        const message: OmniverseStreamMessage = {
            event_type: `${event_type}_request`,
            payload: { ...payload, id },
        };
        const messageString = JSON.stringify(message);
        AppStreamer.sendMessage(messageString);
        return new Promise<OmniverseStreamMessage>((resolve, reject) => {
            // eslint-disable-next-line prefer-const, @typescript-eslint/no-explicit-any
            let timeout: any;
            const checkInterval = setInterval(() => {
                if (id in this.requestResponses) {
                    const entireResponse = this.requestResponses[id];
                    delete this.requestResponses[id];
                    clearInterval(checkInterval);
                    clearTimeout(timeout);
                    const payload = entireResponse["payload"];
                    if ("response" in payload) {
                        const response = payload["response"];
                        resolve(response);
                    } else if ("error" in payload) {
                        const error = payload["error"];
                        reject(new Error(error));
                    } else {
                        reject(new Error(`Unexpected response ${entireResponse}`));
                    }
                }
            }, intervalMs);

            timeout = setTimeout(() => {
                clearInterval(checkInterval);
                reject(new Error('Timeout: Response not received within 5000ms'));
            }, timeoutMs);
        });
    }

    public onInferenceComplete(callback: StreamHandlerCallback) {
        this.signal("inference_complete", callback);
      }

    async signal(event_type: string, callback: StreamHandlerCallback) {
        this.signalHandlers[`${event_type}_signal`] = callback;
    }
}
