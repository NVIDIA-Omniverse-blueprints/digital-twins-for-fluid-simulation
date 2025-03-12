import { useEffect } from "react";
import App from "./App";
import "./App.css";

import { OmniverseStreamStatus } from "./OmniverseApi";
import { useOmniverseApi } from "./OmniverseApiContext";


const TOP_LEVEL_VEHICLE_PRIM = "/World/AllVehicles/HeroVehicles";
const VEHICLE_VARIANT_SET_NAME = "Variant_Set";

function DelayedApp() {
    const { api, status } = useOmniverseApi();
    
    
    useEffect(() => {
        const init = async () => {
          await api?.request("set_rendering_mode", { mode: 0});
          await api?.request("select_car", {
            car_idx: 0,
            prim_path: TOP_LEVEL_VEHICLE_PRIM,
            variant_set_name: VEHICLE_VARIANT_SET_NAME,
            variant_value: "Concept",
          });
          await api?.request("set_camera_view", {
            prim_path: `/World/windTunnelEnv/cameras/CameraPOV_01`,
          });
        };
        init().catch(console.error);
      }, []);

    return (
        <>
            {status == OmniverseStreamStatus.connected && (
                <App />
            )}
        </>
    );
}

export default DelayedApp;
