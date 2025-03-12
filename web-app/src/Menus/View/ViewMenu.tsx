import React from 'react';
import './viewmenu.css'; 
import { useOmniverseApi } from '../../OmniverseApiContext';

import cam01 from '../../img/cam01.png';
import cam02 from '../../img/cam02.png';
import cam03 from '../../img/cam03.png';
import cam04 from '../../img/cam04.png';
import cam05 from '../../img/cam05.png';
import cam06 from '../../img/cam06.png';
import cam07 from '../../img/cam07.png';

const ViewMenu: React.FC = () => {

  const {api} = useOmniverseApi();

  const handleClick = async (camera_prim_path: string) => {
    const response = await api?.request("set_interactive_camera", {
      camera_prim_path,
    });
    if (!response) {
      console.error(`"[request][set_camera_view] failed for prim_path ${camera_prim_path}`);
    }
  };

  return (
    <div className="view-menu">

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam01')} className="view-button">
          <img src={cam01}/>
          </button>
        </div>

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam02')} className="view-button">
          <img src={cam02}/>
          </button>
        </div>

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam03')} className="view-button">
          <img src={cam03}/>
          </button>
        </div>

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam04')} className="view-button">
          <img src={cam04}/>
          </button>
        </div>  

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam05')} className="view-button">
          <img src={cam05}/>
          </button>
        </div>  

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam06')} className="view-button">
          <img src={cam06}/>
          </button>
        </div>  

        <div className="view-images">
        <button onClick={() => handleClick('/World/InteractiveCams/demoCam07')} className="view-button">
          <img src={cam07}/>
          </button>
        </div>  
    </div>
  );
};

export default ViewMenu;