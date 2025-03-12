import React from 'react';
import { Switch, FormControlLabel, RadioGroup, Radio } from '@mui/material';
import "./variantsmenu.css";

import rim1Model from '../../img/StandardRim.png';
import rim2Model from '../../img/AeroRim.png';
import { useOmniverseApi } from '../../OmniverseApiContext';


interface VariantsMenuProps {
    selectedRim: string;
    setSelectedRim: (value: string) => void;
    mirrorsOn: boolean;
    setMirrorsOn: (value: boolean) => void;
    spoilersOn: boolean;
    setSpoilersOn: (value: boolean) => void;
    rideHeight: string;
    setRideHeight: (value: string) => void;
    selectedModel: string | null;

}

const VariantsMenu: React.FC<VariantsMenuProps> = ({
    selectedRim,
    setSelectedRim,
    mirrorsOn,
    setMirrorsOn,
    spoilersOn,
    setSpoilersOn,
    rideHeight,
    setRideHeight,
    selectedModel
  }) => {
    const isLiftedDisabled = selectedModel === 'Model 1' || selectedModel === 'Model 4';
    const isLoweredDisabled = selectedModel === 'Model 5';
    const shouldResetRideHeight = (isLiftedDisabled && rideHeight === 'lifted') || (isLoweredDisabled && rideHeight === 'lowered');
    if (shouldResetRideHeight) {
        setRideHeight('standard');
    }

    const {api} = useOmniverseApi();

return (
<div className='variants-menu'>
    {/* Rims Menu */}
    <div className='rims-menu'>
    <div className="rims">
    <img
        src={rim1Model}
        alt="Rim 1"
        className={`rims-image ${selectedRim === 'rim1' ? 'selected' : ''}`}
        onClick={async () => {
            setSelectedRim('rim1');
            await api?.request("set_rim_variant", {inference_id: 0});
        }
        }
    />
    <img
        src={rim2Model}
        alt="Rim 2"
        className={`rims-image ${selectedRim === 'rim2' ? 'selected' : ''}`}
        onClick={async () => {
            setSelectedRim('rim2');
            await api?.request("set_rim_variant", {inference_id: 1});
        }
        }
    />
    
    </div>
    <div className='rims-text'>Rims
    </div>
    </div>

    {/* Mirrors and Spoilers Toggle Menu */}
    <div className="toggles-menu">
    
        <FormControlLabel
        control={<Switch checked={mirrorsOn} onChange={async (e) => {
            setMirrorsOn(e.target.checked);
            const inference_id = e.target.checked ? 0 : 1;
            await api?.request("set_mirror_variant", {inference_id});
        }
        } />}
        label="Mirrors"
        sx={{
            width: 50,
            height: 30,
            padding: 0,
            '& .MuiSwitch-switchBase': {
                padding: 1.3,
                '&.Mui-checked': {
                transform: 'translateX(20px)',
                },
            },
            '& .MuiFormControlLabel-label': {
                fontSize: '12px', 
            },
            '& .MuiSwitch-switchBase.Mui-checked': {
            color: '#76b900',
            },
            '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
            backgroundColor: '#76b900',
            },
            '& .MuiSwitch-track': {
                width: '30px',
                height: '10px',
            backgroundColor: '#ccc',
            },
            '& .MuiSwitch-thumb': {
                width: 12,
                height:12,
            },
        }}
        />
    
    
        <FormControlLabel
        control={<Switch checked={spoilersOn} onChange={async (e) => {
            setSpoilersOn(e.target.checked);
            const inference_id = e.target.checked ? 1 : 0;
            await api?.request("set_spoiler_variant", {inference_id});
        }
        } />}
        label="Spoilers"
        sx={{
            width: 50,
            height: 30,
            padding: 0,
            '& .MuiSwitch-switchBase': {
                padding: 1.3,
                '&.Mui-checked': {
                transform: 'translateX(20px)',
                },
            },
            '& .MuiFormControlLabel-label': {
                fontSize: '12px', 
            },
            '& .MuiSwitch-switchBase.Mui-checked': {
            color: '#76b900',
            },
            '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
            backgroundColor: '#76b900',
            },
            '& .MuiSwitch-track': {
                width: '30px',
                height: '10px',
            backgroundColor: '#ccc',
            },
            '& .MuiSwitch-thumb': {
                width: 12,
                height:12,
            },
        }}
        />
    
    </div>

    {/* Ride Height Menu */}
    <div className="ride-height-menu">
    
    <RadioGroup
        aria-labelledby="ride-height-radio-group"
        value={rideHeight}
        onChange={async (e) => {
            setRideHeight(e.target.value);
            const inference_id = (() => {
                switch (e.target.value) {
                    case "standard":
                        return 0;
                    case "lowered":
                        return 1;
                    case "lifted":
                        return 2;
                    default:
                        return 2;
                }
            })();
            await api?.request("set_ride_height_variant", {inference_id});
        }
        }
        sx={{
            marginLeft: '20px',
            marginTop: '-4px',
        }}
    >
        <FormControlLabel
        value="lowered"
        control={<Radio />}
        label="Lowered"
        disabled={isLoweredDisabled}

        sx={{
            '& .MuiSvgIcon-root': {
                fontSize: 13,
                marginBottom: '-4px' 
            },
            '& .MuiFormControlLabel-label': {
                fontSize: '12px', 
            },
            
            '& .MuiRadio-root.Mui-checked': { color: '#76b900' },
            '& .MuiRadio-root': { color: '#ccc' },
        }}
        />
        <FormControlLabel
        value="standard"
        control={<Radio />}
        label="Standard"
        
        sx={{
            '& .MuiSvgIcon-root': {
                fontSize: 13,
                marginBottom: '-4px'  
            },
            '& .MuiFormControlLabel-label': {
                fontSize: '12px', 
            },
            '& .MuiRadio-root.Mui-checked': { color: '#76b900' },
            '& .MuiRadio-root': { color: '#ccc' },
        }}
        />
        <FormControlLabel
        value="lifted"
        control={<Radio />}
        label="Lifted"
        disabled={isLiftedDisabled}
        sx={{
            '& .MuiSvgIcon-root': {
                fontSize: 13,
                marginBottom: '-4px'  
            },
            '& .MuiFormControlLabel-label': {
                fontSize: '12px', 
            },
            '& .MuiRadio-root.Mui-checked': { color: '#76b900' },
            '& .MuiRadio-root': { color: '#ccc' },
        }}
        />
    </RadioGroup>
    <p className='text'>Ride Height</p>
    </div>
</div>
);
};

export default VariantsMenu;
