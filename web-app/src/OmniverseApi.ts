import { AppStreamer } from '@nvidia/omniverse-webrtc-streaming-library';

export interface OmniverseStreamConfig {
    source: "local",
    videoElementId: string,
    audioElementId: string,
    messageElementId: string,
    urlLocation: {
        search: string
    }
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
        onISSOUpdate: StreamHandlerCallback | null = null,
    ) {
        AppStreamer.setup({
            streamConfig: config,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onStart: (msg: any) => {
                onStart?.(msg);
            },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onUpdate: (msg: any) => {
                onUpdate?.(msg);
            },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onCustomEvent: (msg: any) => {

                console.log((msg));
                const event_type = msg.event_type;

                // Handle custom 'inference complete' events
                if (event_type === "inference_complete_signal") {
                    this.signalHandlers[event_type]?.(msg.payload.signal);
                }

                const isResponse = 'id' in msg.payload;
                if (isResponse) {
                    const id: number = msg.payload['id'];
                    this.requestResponses[id] = msg
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
            onStop: (msg: any) => {
                onStop?.(msg);
            },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onTerminate: (msg: any) => {
                onTerminate?.(msg);
            },
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            onISSOUpdate: (msg: any) => {
                onISSOUpdate?.(msg);
            },
            nativeTouchEvents: true,
            authenticate: false,
            doReconnect: true,

        })
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
