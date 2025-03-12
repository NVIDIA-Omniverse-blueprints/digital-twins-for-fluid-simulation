import React from 'react';
import Draggable, { DraggableData, DraggableEvent } from 'react-draggable';
import './volumetracemenu.css';
import carIcon from '../../img/frontSilh.png';
import { useOmniverseApi } from '../../OmniverseApiContext';

interface VolumeTraceMenuProps {
  position: { x: number; y: number };
  setPosition: React.Dispatch<React.SetStateAction<{ x: number; y: number }>>;
}

const VolumeTraceMenu: React.FC<VolumeTraceMenuProps> = ({ position, setPosition }) => {
  const { api } = useOmniverseApi();
  const draggableRef = React.useRef<HTMLDivElement>(null);

  const normalize = (v: number, min: number, max: number) => {
    return -1.0 * (2.0 * (v - min) / (max - min) - 1.0);
  };

  const handleDrag = (_e: DraggableEvent, data: DraggableData) => {
    setPosition({ x: data.x, y: data.y });
    
    const fake_y_bound_min = -220;
    const fake_y_bound_max = 50;
    let x = -normalize(data.x, 0, 120);
    let y = normalize(data.y, fake_y_bound_min, fake_y_bound_max);
    const x_scale = 0.5;
    const y_scale = 1.0;
    x *= x_scale;
    y *= y_scale;
    api?.request("set_smokeprobes_pos", { pct: [x, -1.0, y] });
  };

  const xPosition = `${1.25 * position.x}%`;

  return (
    <div className="slider-menu">
      <div className="image-container">
        <img src={carIcon} alt="car with sliders" className="image" />
        <Draggable
          axis={'both'}
          bounds={{ left: 0, right: 120, top: 0, bottom: 40 }}
          position={position}
          onDrag={handleDrag}
          nodeRef={draggableRef}
        >
          <div className="green-dots" ref={draggableRef}>
            {/* Green dots */}
            <div className="green-dot-1" style={{ left: xPosition, top: `${-50 - position.y}%` }} />
            <div className="green-dot-2" style={{ left: xPosition, top: `${25 - position.y}%` }} />
            <div className="green-dot-3" style={{ left: xPosition, top: `${100 - position.y}%` }} />
            <div className="green-dot-4" style={{ left: xPosition, top: `${175 - position.y}%` }} />
            <div className="green-dot-5" style={{ left: xPosition, top: `${250 - position.y}%` }} />
          </div>
        </Draggable>
      </div>
    </div>
  );
};

export default VolumeTraceMenu;