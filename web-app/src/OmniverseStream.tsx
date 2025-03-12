import "./App.css";
import {
  defaultAudioElementId,
  defaultMessageElementId,
  defaultVideoElementId,
} from "./OmniverseApiContext";

function OmniverseStream() {
  return (
    <>
      <div id={"video-group"}>
        <video
          id={defaultVideoElementId}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "fill",
            padding: 0,
            margin: 0,
          }}
          tabIndex={-1}
          playsInline
          muted
          autoPlay
        />
        <audio id={defaultAudioElementId} muted></audio>
      </div>
      <h3 style={{ position: "absolute", left: 0, top: 0, visibility: "hidden", width: "0", height: "0"}} id={defaultMessageElementId} />
    </>
  );
}

export default OmniverseStream;
