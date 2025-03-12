import React, { useRef } from 'react';
import Draggable, { DraggableData, DraggableEvent } from 'react-draggable';
import './curvetracemenu.css';
import carIcon from '../../img/frontSilh.png';
import { useOmniverseApi } from '../../OmniverseApiContext';
import { OmniverseAPI } from '../../OmniverseApi';
import { Slider } from '@mui/material';

interface CurveTraceMenuProps {
  position: { x: number; y: number };
  setPosition: React.Dispatch<React.SetStateAction<{ x: number; y: number }>>;
  sphereRadius: number;
  setSphereRadius: React.Dispatch<React.SetStateAction<number>>;
}

function throttle(fn: Function, delay: number): Function {
  let lastCallTime: number | null = null;
  return function (...args: unknown[]) {
    const now = Date.now();
    if (lastCallTime === null || now - lastCallTime >= delay) {
      fn(...args);
      lastCallTime = now;
    }
  };
}

const set_streamline_pos = (api: OmniverseAPI | undefined, x: number, y: number, z: number) => {
  api?.request("set_streamlines_pos", { pct: [x, y, z] });
};

const set_streamline_radius = (api: OmniverseAPI | undefined, pct: number) => {
  api?.request("set_streamlines_radius", { pct });
};

const set_streamline_pos_throttled = throttle(set_streamline_pos, 60);
const set_streamline_radius_throttled = throttle(set_streamline_radius, 60);

const CurveTraceMenu: React.FC<CurveTraceMenuProps> = ({ position, setPosition, sphereRadius, setSphereRadius }) => {
  const { api } = useOmniverseApi();
  const draggableRef = useRef<HTMLDivElement>(null);

  const normalize = (v: number, min: number, max: number) => {
    return -1.0 * (2.0 * (v - min) / (max - min) - 1.0);
  };

  const updateStreamlinePosition = (_e: DraggableEvent, data: DraggableData, throttle: boolean) => {
    setPosition({ x: data.x, y: data.y });
    // Hard coded bounds because react-dragable works in pixel units of the box model
    // and we need to normalize (x,y) to [-1, 1]x[-1, 1] for the backend api
    let x = normalize(data.x, -18, 138);
    let y = normalize(data.y, 10, 86);
    const x_scale = 0.5;
    const y_scale = 0.5;
    x *= x_scale;
    y *= y_scale;
    y -= 0.25;
    if (throttle) {
      set_streamline_pos_throttled(api, -1.0, x, y);
    } else {
      set_streamline_pos(api, -1.0, x, y);
    }
  };

  const updateStreamlineRadius = (_event: React.SyntheticEvent | Event, value: number | number[], throttle: boolean) => {
    const pct = typeof value === 'number' ? value : value[0];
    setSphereRadius(pct);
    if (throttle) {
      set_streamline_radius_throttled(api, pct);
    } else {
      set_streamline_radius(api, pct);
    }
  };

  return (
    <div className="slider-menu">
      <div className="image-container">
        <img src={carIcon} alt="car with sliders" className="image" />

        {/* Green dot */}
        <Draggable
          axis="both"
          bounds="parent"
          position={position}
          onDrag={(e, v) => updateStreamlinePosition(e, v, true)}
          onStop={(e, v) => updateStreamlinePosition(e, v, false)}
          nodeRef={draggableRef}
        >
          <div className="green-dot" ref={draggableRef} />
        </Draggable>
      </div>

      <div className="sliders-container">
        <div className="slider">
          <Slider
            value={sphereRadius}
            size="small"
            min={0.0}
            max={1.0}
            step={0.1}
            onChange={(e, v) => updateStreamlineRadius(e, v, true)}
            onChangeCommitted={(e, v) => updateStreamlineRadius(e, v, false)}
            sx={{
              color: '#76b900',
              width: '200px',
              '& .MuiSlider-thumb': {
                width: 18,
                height: 18,
              },
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default CurveTraceMenu;