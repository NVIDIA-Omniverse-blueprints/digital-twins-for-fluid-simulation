import "./arronw.css"

interface Props {
  className: string;
  onClick?: () => void;
  isOpen: boolean;
  isHidden: boolean;
}

export const Arronw = ({ className, onClick, isOpen }: Props): JSX.Element => {
  return (
    <button
      className={`arronw-button ${className}`}
      onClick={onClick}
      

    >
      {isOpen ? '<' : '>'}  
    </button>
  );
};
