export const config = {
  root_prim_path: "/World/Car",
  initial_car_index_to_show: 0,
  cars: [   
    {
      id: "concept",
      description: "Concept",
      image_url: "/cone.usd.png",
      usd_prim_path: "/World/AllVehicles/HeroVehicles/Concept_Car",
      cgns_idx: 4,
      variant_prim_path: "/World/AllVehicles/HeroVehicles",
      variant_set_name: "Variant_Set",
      variant_value: "ConceptCar",
      variants: [
      ],
    },
  ],
  cameras: [
      "Camera",
      "Camera_01",
      "Camera_02",
      "Camera_03",
      "Camera_04",
      "Camera_05",
      "Camera_06",
      "Camera_07",
      "CameraPOV_01",
      "CameraPOV_02",
      "CameraPOV_03",
      "CameraPOV_04",
      "CameraPOV_05",
      "CameraPOV_06",
      "CameraPOV_07",
      "CameraPOV_08",
      "CameraPOV_09",
  ],
  visibility: [
    {
      id: "ON",
      description: "Visibility ON",
      image_url: "/visON.png",
    },
    {
      id: "OFF",
      description: "Visibility OFF",
      image_url: "/visOFF.png",
    },
  ],
};
