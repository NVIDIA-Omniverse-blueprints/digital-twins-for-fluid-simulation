import React, { forwardRef } from "react";
import "./style.css";

interface Props {
  text: string;
  onClick: () => void;
  className: string;
  style?: React.CSSProperties;
  onMouseEnter?: () => void; 
  onMouseLeave?: () => void; 
}

const MainButton = forwardRef<HTMLButtonElement, Props>(
  ({ text, onClick, className, style, onMouseEnter, onMouseLeave }, ref) => {
    return (
      <div className="main-button">
        <button
          ref={ref}
          onClick={onClick}
          className={`button ${className}`}
          style={style}
          onMouseEnter={onMouseEnter} 
          onMouseLeave={onMouseLeave} 
        >
          <div className="slice">{text}</div>
        </button>
      </div>
    );
  }
);

export default MainButton;