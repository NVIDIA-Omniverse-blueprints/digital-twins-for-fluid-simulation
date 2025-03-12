import React, { useState, useRef } from 'react';
import './vehiclemenu.css';
import carConceptImg from '../../img/ConceptCar.png';
import { useOmniverseApi } from '../../OmniverseApiContext';

interface VehicleMenuProps {
    onModelSelect: (model: string) => void;
  }

  const VehicleMenu: React.FC<VehicleMenuProps> = ({ onModelSelect }) => {
    const [visibleMenu, setVisibleMenu] = useState<string | null>(null);

    const imageRefs = useRef<HTMLDivElement[]>([]);

    const { api } = useOmniverseApi();

    const handleClick = async (view: string, _index: number, cgns_idx: number) => {
        const response = await api?.request("select_car", {
            cgns_idx,
        });
        if (!response) {
            console.error(`"[request][select_car] failed for prim_path ${cgns_idx}`);
        }

        setVisibleMenu(visibleMenu === view ? null : view);
        onModelSelect(view);
    };
    

    return (
        <div className="vehicle-menu">
            {/* Model 5 */}
            <div ref={el => { if (el) imageRefs.current[3] = el }} className="vehicle-images">
                <button onClick={() => handleClick('Model 5', 3, 500)} className="view-button">
                    <img src={carConceptImg} alt="Model 5" />
                </button>
            </div>
        </div>
    );
};

export default VehicleMenu;
