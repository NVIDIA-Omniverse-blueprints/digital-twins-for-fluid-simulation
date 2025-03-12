import React from "react";
import { Chart } from "react-google-charts";

const styles = {
  dial: {
    width: `auto`,
    height: `auto`,
    color: "#000",
    padding: "2px"
  },
  title: {
    fontSize: "1em",
    color: "#000"
  }
};

interface SpeedometerProps {
  id: string;
  value: number;
  title: string;
}

const Speedometer: React.FC<SpeedometerProps> = ({value, title }) => {
  const roundedValue = Math.round(value);
  return (
    <div style={styles.dial}>
      <Chart
        height={160}
        chartType="Gauge"
        loader={<div></div>}
        data={[
          ["Label", "Value"],
          [title, roundedValue]
        ]}
        options={{
          greenFrom: 25,
          greenTo: 50,
          yellowFrom: 0,
          yellowTo: 25,
          minorTicks: 5,
          min: 0,
          max: 100,
          greenColor: '#59A700',
          yellowColor: '#76b900',
        }}
      />
    </div>
  );
};

export default Speedometer;
