// GlobalState.js
import { createContext, useContext, useEffect, useRef, useState } from "react";
import {
  OmniverseStreamConfig,
  OmniverseAPI,
  StreamHandlerCallback,
  OmniverseStreamStatus,
} from "./OmniverseApi";

export const defaultVideoElementId = "remote-video";
export const defaultAudioElementId = "remote-audio";
export const defaultMessageElementId = "message-display";

const defaultOnStreamStart = (message: unknown) => {
  console.debug(`start: ${JSON.stringify(message)}`);
};
const defaultOnStreamUpdate = (message: unknown) => {
  console.debug(`update: ${JSON.stringify(message)}`);
};
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const defaultOnStreamCustomEvent = (_message: unknown) => {
  // console.debug(message);
};

function createOmniverseApi(
  videoElementId: string,
  audioElementId: string,
  messageElementId: string,
  onStreamStart: StreamHandlerCallback,
  onStreamUpdate: StreamHandlerCallback,
  onStreamCustomEvent: StreamHandlerCallback,
  onInferenceComplete?: StreamHandlerCallback 
): OmniverseAPI {
  const queryParams = new URLSearchParams(window.location.search);
  const queryParamOrDefault = (name: string, defaultVal: unknown) => {
    if (!queryParams.has(name)) {
      queryParams.set(name, defaultVal as string);
      window.location.search = queryParams.toString();
    }
    return queryParams.get(name);
  };
  const server = queryParamOrDefault("server", window.location.hostname);
  const width = queryParamOrDefault("width", 1920);
  const height = queryParamOrDefault("height", 1080);
  const fps = queryParamOrDefault("fps", 60);
  const url = `server=${server}&resolution=${width}:${height}&fps=${fps}&mic=0&cursor=free&autolaunch=true`;
  console.log(`Omniverse Stream URL: ${url}`);
  const streamConfig: OmniverseStreamConfig = {
    source: "local",
    videoElementId,
    audioElementId,
    messageElementId,
    urlLocation: { search: url },
  };
  const api = new OmniverseAPI(
    streamConfig,
    onStreamStart,
    onStreamUpdate,
    onStreamCustomEvent
  );

  // Register 'inference complete' callback
  if (onInferenceComplete) {
    api.onInferenceComplete(onInferenceComplete);
  }

  return api;
}

export interface IOmniverseApiContext {
  api?: OmniverseAPI;
  status: OmniverseStreamStatus;
}

const OmniverseApiContext = createContext<IOmniverseApiContext | undefined>(
  undefined
);


export const OmniverseApiProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const apiInitialized = useRef(false);
  const [api, setApi] = useState<OmniverseAPI | undefined>(undefined);
  const [status, setStatus] = useState(OmniverseStreamStatus.waiting);

  const onInferenceComplete = (msg: unknown) => {
    console.debug("Inference complete:", msg);
    // Perform additional custom behavior if needed
    alert("Inference has been completed!"); // Example action
  };

  const handleStreamStatusChange = (msg: unknown) => {
      const message = msg as { action: string; status: string };
      if (message.action != "start") {
        return;
      }
      switch (message.status) {
        case "inProgress": {
          setStatus(OmniverseStreamStatus.connecting);
          break;
        }
        case "error": {
          setStatus(OmniverseStreamStatus.error);
          break;
        }
        case "success": {
          setStatus(OmniverseStreamStatus.connected);
          break;
        }
        default:
          break;
      }
    };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const onStreamStart = (msg: unknown) => {
    defaultOnStreamStart(msg);
    handleStreamStatusChange(msg);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const onStreamUpdate = (msg: unknown) => {
    defaultOnStreamUpdate(msg);
    handleStreamStatusChange(msg);
  };
  useEffect(() => {
    if (apiInitialized.current) {
      return;
    }
    apiInitialized.current = true;
    const api = createOmniverseApi(
      defaultVideoElementId,
      defaultAudioElementId,
      defaultMessageElementId,
      onStreamStart,
      onStreamUpdate,
      defaultOnStreamCustomEvent,
      onInferenceComplete
    );
    setApi(api);
  }, [apiInitialized, onStreamStart, onStreamUpdate]);
  return (
    <OmniverseApiContext.Provider value={{ api, status }}>
      {children}
    </OmniverseApiContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useOmniverseApi = () => {
  const context = useContext(OmniverseApiContext);
  if (context === undefined) {
    throw new Error("useOmniverseApi must be within OmniverseApiProvider");
  }
  return context;
};


