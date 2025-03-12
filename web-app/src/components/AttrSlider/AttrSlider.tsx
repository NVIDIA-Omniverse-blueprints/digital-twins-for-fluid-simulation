import React, { useState } from "react";
import { Slider } from "@mui/material";

interface AttrSliderProps {
  defaultValue?: [number, number];
  onChange?: (min_scal: number, max_scal: number) => void; 
  color?: string;
  sx?: object;
}

export const AttrSlider: React.FC<AttrSliderProps> = ({
  defaultValue = [0, .80],
  onChange,
  color = "#76b900",
  sx = {},
}) => {
  const [sliderValue, setSliderValue] = useState<[number, number]>(defaultValue);

  const handleSliderChange = (_event: Event, newValue: number | number[]) => {
    const value = newValue as [number, number];
    setSliderValue(value);
    const [min_scal, max_scal] = value;

    if (onChange) {
      onChange(min_scal, max_scal); 
    }
  };

  return (
    <Slider
      value={sliderValue}
      min={0}
      max={1}
      step={0.01} 
      onChange={handleSliderChange}
      
      sx={{
        color: color,
        width: "100%",
        "& .MuiSlider-thumb": {
          height: 10,
          width: 10,
          backgroundColor: color,
          border: "2px solid currentColor",
        },
        "& .MuiSlider-track": {
          height: 2,
        },
        "& .MuiSlider-rail": {
          height: 2,
          opacity: 1,
          backgroundColor: "#bfbfbf",
        },
        ...sx,
      }}
    />
  );
};

export default AttrSlider;
