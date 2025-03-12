import { useState, useEffect } from "react";
import { useOmniverseApi } from "./OmniverseApiContext";

interface Props {
  showStatus: boolean;
  setShowInferenceStatus: (visible: boolean) => void;
}

const InferenceStatusComponent: React.FC<Props> = ({
  showStatus,
  setShowInferenceStatus,
}) => {
  const { api } = useOmniverseApi();
  const [message, setMessage] = useState("Waiting for Inference");

  useEffect(() => {
    const handleInferenceComplete = (message: any) => {
      //console.log("Received inference complete:", message);

      
      if (!showStatus) setShowInferenceStatus(true); // Ensure global visibility is true

      if(String(message) === "inference_start")
      {
        setMessage("Waiting for Inference");
        setShowInferenceStatus(true)

      }
      else
      {
        //console.log("Setting Timeout")
        setMessage("Inference has completed successfully!");

        setTimeout(() => {
          setShowInferenceStatus(false)
          // setMessage("Waiting for Inference");
          }, 5000)
      }     
      

      //setShowInferenceStatus(true);
      // Additional actions such as refreshing UI or data

    
    };

    api?.onInferenceComplete(handleInferenceComplete); // Listen for the event

    // Cleanup after unmount
    return () => {
      api?.signal("inference_complete", () => {});
    };
  }, [api, setShowInferenceStatus]);

  if(!showStatus)
  {
    //console.log("Show Status is false")
    return null; //render nothing when hidden
  }
  return <div>{message}</div>;
};

export default InferenceStatusComponent;