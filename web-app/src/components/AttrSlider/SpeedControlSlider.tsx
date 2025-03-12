import React from "react";
import { Slider } from "@mui/material";

interface SpeedControlSlider {
value?: number;
min?: number;
max?: number;
step?: number;
marks?: { value: number; label: string }[];
color?: string;
onChange?: (event: Event, value: number | number[]) => void; 
onChangeCommitted?: (event: React.SyntheticEvent | Event, value: number | number[]) => void;
sx?: object;  
}

export const SpeedControlSlider: React.FC<SpeedControlSlider> = ({
value = 25,
min = 0,
max = 100,
step = 0.1,
marks = [
{ value: 0, label: '0' },
{ value: 25, label: '25' },
{ value: 50, label: '50' },
{ value: 75, label: '75' },
{ value: 100, label: '100' },
],
color = '#76b900', 
onChange,  
onChangeCommitted,
sx = {},   
}): JSX.Element => {
return (
<Slider
    aria-labelledby="discrete-slider"
    step={step}
    marks={marks}
    min={min}
    max={max}
    value={value}
    onChange={onChange}  
    onChangeCommitted={onChangeCommitted}
    sx={{
    color: color,
    width: '98%',
    '& .MuiSlider-thumb': {
        height: 12,
        width: 12,
        backgroundColor: color,
        border: '2px solid currentColor',
    },
    '& .MuiSlider-track': {
        height: 2,
    },
    '& .MuiSlider-rail': {
        height: 2,
        opacity: 1,
        backgroundColor: '#bfbfbf',
    },
    '& .MuiSlider-markLabel': {
        fontSize: '12px',
        color: '#ffffff',
        transform: 'translateY(-7px)',
    },
    ...sx,  
    }}
/>
);
};

export default SpeedControlSlider;
