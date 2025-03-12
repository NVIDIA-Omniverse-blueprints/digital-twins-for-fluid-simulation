import { Box, Typography } from "@mui/material";
import React from "react";
import velocityGradient from "../../img/velocity.png";
import pressureGradient from "../../img/pressure.png";

interface GradientBarProps {
  sliderValue: number; 
  selectedAttr: string;
  min_val: number; 
  max_val: number; 
  interval?: number; 
}

export const GradientBar: React.FC<GradientBarProps> = ({
  min_val,
  max_val,
  interval = 10, 
  selectedAttr
}) => {
  
  const getBackgroundImage = () => {
    switch (selectedAttr) {
      case 'Velocity Magnitude':
        return `url(${velocityGradient})`;
      case 'Pressure':
        return `url(${pressureGradient})`;
      default:
        return 'none';
    }
  };

  // generate whole numbers underneath the gradient
  const generateNumbers = (min: number, max: number, interval: number) => {
    const numbers = [];
    for (let i = min; i <= max; i += interval) {
      numbers.push(Math.round(i)); 
    }
    return numbers;
  };

  const numbers = generateNumbers(min_val, max_val, interval);


  return (
    <Box
      sx={{
        position: "relative",
        width: "100%",
        height: "50%",
        background: getBackgroundImage(),
        backgroundSize: 'cover', 
        backgroundPosition: 'center',
      }}
    >
      {/* Thin white line */}
      <Box
        sx={{
          width: "100%",
          height: "1px",
          backgroundColor: "#ffffff", 
          marginTop: "0.5rem",
        }}
      />

      {/* Numbers underneath the gradient */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between", 
          alignItems: "center",
          width: "100%", 
          overflow: "hidden", 
          padding: "1%", 
          boxSizing: "border-box",
        }}
      >
        {numbers.map((num, index) => (
            <Box
            key={index}
            sx={{
              flexBasis: `${100 / numbers.length}%`, 
              textAlign: "center",
            }}
          >
          <Typography
            key={index}
            sx={{
              color: "#ffffff",
              fontSize: "10px",
              whiteSpace: "nowrap",
            }}
          >
            {num}
          </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

export default GradientBar;
