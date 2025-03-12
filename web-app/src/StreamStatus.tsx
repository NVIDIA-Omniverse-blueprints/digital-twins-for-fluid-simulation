import { useOmniverseApi } from "./OmniverseApiContext";
import { OmniverseStreamStatus } from "./OmniverseApi";

function StreamStatus() {
  const {status} = useOmniverseApi();
  let statusText = "";
  switch (status) {
    case OmniverseStreamStatus.waiting: {
        statusText = "🟠 Waiting...";
        break;
    }
    case OmniverseStreamStatus.connecting: {
        statusText = "🟡 Connecting..";
        break;
    }
    case OmniverseStreamStatus.connected: {
        statusText = "🟢 Connected";
        break;
    }
    case OmniverseStreamStatus.error: {
        statusText = "🔴 Error";
        break;
    }
  }
  return (
    <>
    {statusText}
    </>
  );
}

export default StreamStatus;
