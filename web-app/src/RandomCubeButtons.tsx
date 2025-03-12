import { useState } from "react";
import { useOmniverseApi } from "./OmniverseApiContext";

function RandomCubeButtons() {
  const {api} = useOmniverseApi();
  const [count, setCount] = useState(0);
  const onClickCreate = async () => {
    const prim_path = `/World/Cube${count}`;
    setCount(count + 1);
    const x = 500.0 * (Math.random() - 0.5);
    const y = 500.0 * (Math.random() - 0.5);
    const z = 500.0 * (Math.random() - 0.5);
    await api?.request("command_execute", {
      name: "CreateMeshPrimWithDefaultXform",
      prim_type: "Cube",
      prim_path,
    });
    await api?.request("command_execute", {
      name: "TransformPrimSRT",
      path: prim_path,
      new_translation: [x, y, z],
    });
  };
  const onClickUndo = async () => {
    await api?.request("command_undo");
  };
  return (
    <>
      <button onClick={onClickCreate}>Create Cube</button>
      <button onClick={onClickUndo}>Undo</button>
    </>
  );
}

export default RandomCubeButtons;
