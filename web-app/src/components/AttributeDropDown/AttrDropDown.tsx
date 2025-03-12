import React, { useState } from "react";
import { Select, MenuItem, FormControl, SelectChangeEvent } from "@mui/material";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown"; 
import { useOmniverseApi } from "../../OmniverseApiContext";

interface AttrDropDownProps {
    onAttrChange: (value: string) => void; 
}

const AttrDropDown: React.FC<AttrDropDownProps> = ({ onAttrChange }): JSX.Element => {
    const [value, setValue] = useState<string>("Velocity Magnitude");

const {api} = useOmniverseApi();

const handleChange = async (event: SelectChangeEvent<string>) => {
    const newValue = event.target.value as string;
    setValue(newValue);
    onAttrChange(newValue); 
    const attribute = newValue == "Velocity Magnitude" ? 0 : 1;
    await api?.request("set_visualization_attribute_state", {attribute});
};

return (
    <FormControl fullWidth >
    <Select
        value={value}
        onChange={handleChange}
        displayEmpty
        IconComponent={ArrowDropDownIcon}
        inputProps={{
            MenuProps: {
                MenuListProps: {
                    style: {
                        backgroundColor: '#1b1c1e', 
                        color: 'white',
                        
                    },
                },
            }
        }}     
        sx={{ 
            color: "white", 
            bgcolor: "#2a2c30", 
            borderRadius: 1,
            fontFamily:'Inter, system-ui, Avenir, Helvetica, Arial, sans-serif',
            fontSize: "12px",
            height: "20px",
            width: "110%",
            marginLeft: "-12px",
            marginBottom: "8px",
            '& .MuiSelect-icon': {
                color: 'white', 
            },
            '& .MuiOutlinedInput-notchedOutline': { 
                borderColor: "#2a2c30", 
            },
            '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: "#2a2c30", 
            },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                borderColor: "#2a2c30", 
            }
        }}
    >
        <MenuItem value="Velocity Magnitude">Velocity Magnitude</MenuItem>
        <MenuItem value="Pressure">Pressure</MenuItem>
    </Select>
    </FormControl>
);
};

export default AttrDropDown;