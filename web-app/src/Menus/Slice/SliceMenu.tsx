import React, { useRef } from 'react';
import Draggable from 'react-draggable';
import './slicemenu.css';
import frontView from '../../img/frontSilh.png';
import sideView from '../../img/sideSilh.png';
import { useOmniverseApi } from '../../OmniverseApiContext';

type SliceMenuProps = {
  activeSection: string;
  setActiveSection: (section: string) => void;
  xPosition: { x: number; y: number };
  setXPosition: (position: { x: number; y: number }) => void;
  yPosition: { x: number; y: number };
  setYPosition: (position: { x: number; y: number }) => void;
  zPosition: { x: number; y: number };
  setZPosition: (position: { x: number; y: number }) => void;
};

const SliceMenu: React.FC<SliceMenuProps> = ({
  activeSection,
  setActiveSection,
  xPosition,
  setXPosition,
  yPosition,
  setYPosition,
  zPosition,
  setZPosition
}) => {
  const { api } = useOmniverseApi();
  const draggableRef = useRef<HTMLDivElement>(null);

  const handleSectionClick = async (section: string) => {
    setActiveSection(section);
    await api?.request("set_slice_state", { state: section });
  };

  const handleDragXStop = (_event: any, data: any) => {
    const bounds = [0.0, 180.0];
    const pct = 2.0 * (data.x - bounds[0]) / (bounds[1] - bounds[0]) - 1.0;
    api?.request("set_slice_pos", { pct });
    setXPosition({ x: data.x, y: xPosition.y });
  };

  const handleDragYStop = (_event: any, data: any) => {
    const bounds = [-15.0, -80.0];
    const pct = 2.0 * (data.y - bounds[0]) / (bounds[1] - bounds[0]) - 1.0;
    api?.request("set_slice_pos", { pct });
    setYPosition({ x: yPosition.x, y: data.y });
  };

  const handleDragZStop = (_event: any, data: any) => {
    const bounds = [0.0, 244.0];
    const pct = 2.0 * (data.x - bounds[0]) / (bounds[1] - bounds[0]) - 1.0;
    api?.request("set_slice_pos", { pct });
    setZPosition({ x: data.x, y: zPosition.y });
  };

  return (
    <div className="main-menu">
      <div className="top-section">
        <div className="section-buttons">
          {['X', 'Y', 'Z'].map((section) => (
            <button
              key={section}
              className={activeSection === section ? 'active-btn' : ''}
              onClick={() => handleSectionClick(section)}
            >
              {section}
            </button>
          ))}
        </div>

        <div className="image-section">
          <div className="image-container">
            <img src={frontView} alt="Front View" className={activeSection === 'X' ? 'highlight' : 'dimmed'} />
            {activeSection === 'X' && (
              <Draggable
                axis="x"
                nodeRef={draggableRef}
                position={xPosition}
                onDrag={handleDragXStop}
              >
                <div className="vertical-bar" ref={draggableRef}></div>
              </Draggable>
            )}
          </div>

          <div className="side-image-container">
            <img src={sideView} alt="Side View" className={activeSection === 'Y' || activeSection === 'Z' ? 'highlight' : 'dimmed'} />
            {activeSection === 'Y' && (
              <Draggable
                axis="y"
                nodeRef={draggableRef}
                position={yPosition}
                onDrag={handleDragYStop}
              >
                <div className="horizontal-bar" ref={draggableRef}></div>
              </Draggable>
            )}
            {activeSection === 'Z' && (
              <Draggable
                axis="x"
                nodeRef={draggableRef}
                position={zPosition}
                onDrag={handleDragZStop}
              >
                <div className="vertical-bar" ref={draggableRef}></div>
              </Draggable>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SliceMenu;