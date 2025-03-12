import React, { useState } from 'react';
import "./App.css";
import OmniverseStream from "./OmniverseStream";
import MainButton from "./components/MainButton/MainButton";
import { motion } from "framer-motion";
import { Arronw } from './icons/Arronw';
import { IoIosRefreshCircle } from "react-icons/io";
import Speedometer from './components/Speedometer/Speedometer';
import AttrSlider from './components/AttrSlider/AttrSlider';
import VelocitySlider from './components/AttrSlider/VelocitySlider';
import AttrDropDown from './components/AttributeDropDown/AttrDropDown';
import GradientBar from './components/GradientBar/GradientBar';
import SpeedControlSlider from './components/AttrSlider/SpeedControlSlider';

import ViewMenu from './Menus/View/ViewMenu';
import CurveTraceMenu from './Menus/CurveTrace/CurveTraceMenu';
import VolumeTraceMenu from './Menus/VolumeTrace/VolumeTraceMenu';
import VariantsMenu from './Menus/Vehicles/VariantsMenu';
import SliceMenu from "./Menus/Slice/SliceMenu";
import { useOmniverseApi } from './OmniverseApiContext';
import InferenceStatusComponent from './InferenceStatus';



function App() {
  const [isBtnBarOpen, setIsBtnBarOpen] = useState(true); 
  const [isVariantsOpen, setIsVariantsOpen] = useState(true);
  const [isHidden, setIsHidden] = useState(true);
  const [, setIsViewMenuVisible] = useState(false);
  const [, setIsVehicleMenuVisible] = useState(false);
  const [, setIsCurveTraceVisible] = useState(false);
  const [, setIsVolumeTraceVisible] = useState(false);
  const [, setIsVolumeVisible] = useState(false);
  const [, setIsSliceVisible] = useState(false);
  const [isSliceActive, setIsSliceActive] = useState(false);
  const [showInferenceStatus, setShowInferenceStatus] = useState(false);
  

  // state for slice menu
  const [activeSection, setActiveSection] = useState<string>('X');
  const [xPosition, setXPosition] = useState({ x: 75, y: 0 });
  const [yPosition, setYPosition] = useState({ x: 260, y: -45 });
  const [zPosition, setZPosition] = useState({ x: 122, y: 0 });
  
  //state for variants menu
  const [selectedRim, setSelectedRim] = useState<string>('rim1');
  const [mirrorsOn, setMirrorsOn] = useState<boolean>(true);
  const [spoilersOn, setSpoilersOn] = useState<boolean>(false);
  const [rideHeight, setRideHeight] = useState<string>('standard');

  //state for volume trace menu
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 60, y: 30 }); // Position for VolumeTraceMenu

  //state for curve trace menu
  const [curveTracePosition, setCurveTracePosition] = useState<{ x: number; y: number }>({ x: 50, y: 50 });
  const [curveTraceRadius, setCurveTraceRadius] = useState<number>(0.5);

  
  const [activeButton, setActiveButton] = useState<string | null>(null);
  const [selectedAttr, setSelectedAttr] = useState<string>("Velocity Magnitude");
  const [selectedModel] = useState<string>("Model 5");

  const [speed, setSpeed] = useState(75);
  const { api } = useOmniverseApi();

  const [hoveredButton, setHoveredButton] = useState<string | null>(null);

  const toggleBtnBar = () => {
    setIsBtnBarOpen(!isBtnBarOpen); // Toggle only btn-bar arrow
  };

  const toggleVariants = () => {
    setIsVariantsOpen(!isVariantsOpen);
    setIsHidden(!isHidden); // Toggle only variants-hide arrow
  };


  const handleMouseEnter = (button: string) => {
    setHoveredButton(button);
  };

  const handleMouseLeave = (button: string) => {
    if (hoveredButton === button) {
      setHoveredButton(null);
    }
  };


  const handleSpeedChange = async (_event: React.ChangeEvent<object>, value: number) => {
    setSpeed(value);
    // TODO: Disable sending wind speed updates during wind spped changes to avoid performance issues
    // making requests to the inference service
    // await api?.request("set_wind_speed", {speed: value, point_scale: 0.1});
  };

  const handleSpeedCommitted = async (_event: React.ChangeEvent<object>, value: number) => {
    setSpeed(value);
    await api?.request("set_wind_speed", { speed: value, point_scale: 1.0 });
  };

  const [velocityMinScal, setVelocityMinScal] = useState(0);
  const [velocityMaxScal, setVelocityMaxScal] = useState(1);


  const [attrMinScal, setAttrMinScal] = useState(0);
  const [attrMaxScal, setAttrMaxScal] = useState(1);

  // Calculate min_val and max_val for VelocitySlider
  const velocityMinVal = velocityMinScal * 145;
  const velocityMaxVal = velocityMaxScal * 145;

  // Calculate min_val and max_val for AttrSlider
  const attrMinVal = -2000 * (1 - attrMinScal);
  const attrMaxVal = 1000 * (1 - attrMaxScal);


  const hideAllMenus = () => {
    setIsVehicleMenuVisible(false);
    setIsCurveTraceVisible(false);
    setIsVolumeTraceVisible(false);
    setIsVolumeVisible(false);
    setIsSliceVisible(false);
    setIsViewMenuVisible(false);
  }



  const handleClick = async (view: string) => {
    hideAllMenus();
    console.log(`${view} clicked`);
    setActiveButton(activeButton === view ? null : view);

    if (view !== 'Slice') {
      setIsSliceActive(false);
    }
    
    if (view === 'Curve Trace') {
      setHoveredButton(view);
      const response = await api?.request("set_rendering_mode", {
        mode: 1,
      });
      if (!response) {
        console.error("Error setting rendering mode");
      }
    }

    if (view === 'Volume Trace') {
      setHoveredButton(view);
      const response = await api?.request("set_rendering_mode", {
        mode: 0,
      });
      if (!response) {
        console.error("Error setting rendering mode");
      }
    }

    if (view === 'Volume') {
      setHoveredButton(null);
      const response = await api?.request("set_rendering_mode", {
        mode: 2,
      });
      if (!response) {
        console.error("Error setting rendering mode");
      }
    }

    if (view === 'Slice') {
      setHoveredButton(view);
      setIsSliceActive(!isSliceActive);
      const response = await api?.request("set_rendering_mode", {
        mode: 3,
      });
      if (!response) {
        console.error("Error setting rendering mode");
      }
    }else {
      setActiveButton(activeButton === view ? null : view);
    }

    if (view === 'Reset') {
      reset_app();

      setTimeout(() => {
        setActiveButton(null);
      }, 150);
    }
  }

  const getButtonStyle = (button: string) => {
    const isActive = button === "Slice" ? isSliceActive : activeButton === button;
    return {
      backgroundColor: isActive ? "#76b900" : "#2a2c30",
      borderColor: isActive ? "#76b900" : "#2a2c30",
      color: "#2a2c30",
      transition: "background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease",
    };
  };



  const reset_app = () => {
    console.log("Reseting app")
    const init = async () => {
      await api?.request("reset");
    };
    init().catch(console.error);
  };

  return (
    <>
  <div id="stream-container">
        <div id="inference-status-container" style={{ display: showInferenceStatus ? "block" : "none" }}>
        <InferenceStatusComponent
          showStatus={showInferenceStatus}
          setShowInferenceStatus={setShowInferenceStatus}
        />
        </div>

        {true && <div id="overlay-ui">
          <div id="btn-bar">
            <div className='arrow-btn'>
              <Arronw
                className="arronw-instance"
                onClick={toggleBtnBar} 
                isHidden={!isBtnBarOpen}
                isOpen={isBtnBarOpen}
              />
            </div>
            <motion.aside
              initial={{ opacity: 1 }}
              animate={{ opacity: isBtnBarOpen ? 1 : 0 }}
              transition={{ duration: 0.3 }}
            >
              {isBtnBarOpen && (
                <div className='frame-wrapper'>
                  <div className='frame-4'>
                    <div className='main-button-container' >
                      <MainButton
                        className="main-button"
                        text="View"
                        onClick={() => handleClick('View')}
                        onMouseEnter={() => handleMouseEnter("View")}
                        />
                      {hoveredButton === 'View' &&
                        <div className="view-menu-container"                   
                        
                        onMouseLeave={() => handleMouseLeave("View")}
                        >
                          <ViewMenu />
                        </div>
                      }
                    </div>                    
                  </div>
                  <div className="frame-4">
                    <div className='main-button-container'>
                      <MainButton
                        className="main-button"
                        text="Curve Trace"
                        onClick={() => handleClick('Curve Trace')}
                        style={getButtonStyle('Curve Trace')}
                        onMouseEnter={
                          activeButton !== 'Volume Trace' && activeButton !== 'Volume' && activeButton !== 'Slice'
                            ? () => handleMouseEnter("Curve Trace")
                            : undefined
                        }
                        />                    
                      {hoveredButton === 'Curve Trace' &&
                        <div className="curve-trace-menu-container"                         
                        
                        >
                          <CurveTraceMenu
                            position={curveTracePosition}
                            setPosition={setCurveTracePosition}
                            sphereRadius={curveTraceRadius}
                            setSphereRadius={setCurveTraceRadius}
                          />
                        </div>
                      }
                    </div>
                    <div className='main-button-container'>
                      <MainButton
                        className="main-button"
                        text="Volume Trace"
                        onClick={() => handleClick('Volume Trace')}
                        style={getButtonStyle('Volume Trace')}
                        onMouseEnter={
                          activeButton !== 'Curve Trace' && activeButton !== 'Volume' && activeButton !== 'Slice'
                            ? () => handleMouseEnter("Volume Trace")
                            : undefined
                        }
                        />                     
                        {hoveredButton === 'Volume Trace' &&
                        <div className="volume-trace-menu-container" 
                        
                        >
                          <VolumeTraceMenu
                            position={position}
                            setPosition={setPosition}
                          />
                        </div>
                      }
                    </div>
                    <div className='main-button-container'>
                      <MainButton
                        className="main-button"
                        text="Volume"
                        onClick={() => handleClick('Volume')}
                        style={getButtonStyle('Volume')}
                        />                    
                        </div>
                    <div className='main-button-container'>
                      <MainButton
                        className="main-button"
                        text="Slice"
                        onClick={() => handleClick('Slice')}
                        style={getButtonStyle('Slice')}
                        onMouseEnter={
                          activeButton !== 'Curve Trace' && activeButton !== 'Volume' && activeButton !== 'Volume Trace'
                            ? () => handleMouseEnter("Slice")
                            : undefined
                        }
                        />                      
                        {hoveredButton === 'Slice' &&
                        <div className="slice-menu-container"                         
                        
                        >
                          <SliceMenu
                            activeSection={activeSection}
                            setActiveSection={setActiveSection}
                            xPosition={xPosition}
                            setXPosition={setXPosition}
                            yPosition={yPosition}
                            setYPosition={setYPosition}
                            zPosition={zPosition}
                            setZPosition={setZPosition}
                          />
                        </div>
                      }
                    </div>

                  </div>

                </div>
              )}
            </motion.aside>

          </div>

          <div className='side-button-container'>
              <button
                className="reset-button"
                onClick={() => handleClick('Reset')}
                ><IoIosRefreshCircle />
                </button>
            </div>

          {true &&

            <div id='bottom-contents'>
              <div className="speedometer">
                <Speedometer id="speedometer" value={speed} title="Speed" />
              </div>
              <div className="bottom-attributes">
                <p className="speed-text">Speed Control</p>
                <div className="top-slider">
                  <SpeedControlSlider
                    value={speed}
                    onChange={handleSpeedChange}
                    onChangeCommitted={handleSpeedCommitted}
                    min={0}
                    max={100}
                    step={1}
                    marks={[
                      { value: 0, label: '0' },
                      { value: 25, label: '25' },
                      { value: 50, label: '50' },
                      { value: 75, label: '75' },
                      { value: 100, label: '100' },
                    ]}
                  />
                </div>

                <div className="drop-down">
                  <AttrDropDown
                    onAttrChange={setSelectedAttr}
                  />
                </div>
                <div className="gradient-container">
                  {selectedAttr === "Velocity Magnitude" ? (
                    <>
                      <VelocitySlider
                        onChange={async (min_scal, max_scal) => {
                          setVelocityMinScal(min_scal);
                          setVelocityMaxScal(max_scal);
                          await api?.request("set_gradient_scale", { min_val: velocityMinVal, max_val: velocityMaxVal });
                        }}
                      />
                      <GradientBar
                        sliderValue={velocityMaxScal}
                        selectedAttr={selectedAttr}
                        min_val={velocityMinVal}
                        max_val={velocityMaxVal}
                        interval={20}
                      />
                    </>
                  ) : (
                    <>
                      <AttrSlider
                        onChange={async (min_scal, max_scal) => {
                          setAttrMinScal(min_scal);
                          setAttrMaxScal(max_scal);
                          await api?.request("set_gradient_scale", { min_val: attrMinVal, max_val: attrMaxVal });
                        }}
                      />
                      <GradientBar
                        sliderValue={attrMaxScal}
                        selectedAttr={selectedAttr}
                        min_val={attrMinVal}
                        max_val={attrMaxVal}
                        interval={300}
                      />
                    </>
                  )}
                </div>

              </div>
            </div>}
            <div className="variants-hide">
              <Arronw
              className="arronw-instance"
              onClick={toggleVariants} 
              isHidden={!isVariantsOpen}
              isOpen={isVariantsOpen}
              />
            </div>
          <div className="variants-menu">

            <motion.aside
              initial={{ opacity: 1 }}
              animate={{ opacity: isVariantsOpen ? 1 : 0 }}
              transition={{ duration: 0.3 }}
            >
              {isVariantsOpen && (
                <div className="variants-options">
                  <VariantsMenu 
                    selectedModel={selectedModel}
                    selectedRim={selectedRim}
                    setSelectedRim={setSelectedRim}
                    mirrorsOn={mirrorsOn}
                    setMirrorsOn={setMirrorsOn}
                    spoilersOn={spoilersOn}
                    setSpoilersOn={setSpoilersOn}
                    rideHeight={rideHeight}
                    setRideHeight={setRideHeight}
                  />
                </div>
              )}
            </motion.aside>

          </div>
        </div>}
        <div id="stream-container-stream">
          <OmniverseStream />
        </div>
      </div>
    </>
  );
}

export default App;
