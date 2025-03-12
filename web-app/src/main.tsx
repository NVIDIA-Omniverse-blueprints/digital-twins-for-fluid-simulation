import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import { OmniverseApiProvider } from "./OmniverseApiContext";
import App from "./App.tsx";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <OmniverseApiProvider>
      <App />
    </OmniverseApiProvider>
  </React.StrictMode>
);
