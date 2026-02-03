# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

from logging import getLogger

import omni.kit.commands
from omni.cae.material_library import get_cae_materials
from omni.usd import get_context
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt, UsdVol
from omni.cae.schema import cae
from .delegate import InferenceDataDelegate
import numpy as np

logger = getLogger(__name__)


class CreateRTWTService(omni.kit.commands.Command):
    def __init__(self, prim_path: str):
        self._prim_path = Sdf.Path(prim_path)

    def do(self):
        stage = get_context().get_stage()
        if not stage:
            logger.error("No USD stage found")
            return False

        if stage.GetPrimAtPath(self._prim_path):
            logger.warning(f"Using existing 'RTWTService' prim {self._prim_path}")
            return True

        prim = stage.DefinePrim(self._prim_path, "RTWTService")
        prim.ApplyAPI("RtwtServiceAPI")

        logger.info(f"Created RTWTService prim at {self._prim_path}")
        return True


class CreateTriton(omni.kit.commands.Command):
    INPUT_PRIM_NAME = "Input"
    RESULT_PRIM_NAME = "Result"

    def __init__(self, prim_path: str):
        self._prim_path = Sdf.Path(prim_path)

    def do(self):
        stage = get_context().get_stage()
        if not stage:
            logger.error("No USD stage found")
            return False

        if stage.GetPrimAtPath(self._prim_path):
            logger.warning(f"Using existing 'Inference' prim {self._prim_path}")
            return True

        triton_prim = stage.DefinePrim(self._prim_path, "Triton")
        triton_prim.ApplyAPI("RtwtTritonAPI")

        # Add prim for input dataset
        input_dataset = cae.DataSet.Define(stage, triton_prim.GetPath().AppendChild(self.INPUT_PRIM_NAME))
        cae.MeshAPI.Apply(input_dataset.GetPrim())
        mesh = cae.MeshAPI(input_dataset.GetPrim())
        for field in ["points", "faceVertexIndices", "faceVertexCounts"]:
            array = cae.FieldArray.Define(stage, mesh.GetPath().AppendChild(field))
            array.GetPrim().CreateAttribute(InferenceDataDelegate.FIELD_NAME_ATTR, Sdf.ValueTypeNames.Token).Set(field)
            array.GetPrim().CreateAttribute(InferenceDataDelegate.KEY_ATTR, Sdf.ValueTypeNames.Token).Set("input")
            array.GetPrim().CreateAttribute(InferenceDataDelegate.TAG_ATTR, Sdf.ValueTypeNames.Token).Set("")
        mesh.CreatePointsRel().SetTargets({input_dataset.GetPath().AppendChild("points")})
        mesh.CreateFaceVertexIndicesRel().SetTargets({input_dataset.GetPath().AppendChild("faceVertexIndices")})
        mesh.CreateFaceVertexCountsRel().SetTargets({input_dataset.GetPath().AppendChild("faceVertexCounts")})

        # Add prim for result dataset
        result_dataset = cae.DataSet.Define(stage, triton_prim.GetPath().AppendChild(self.RESULT_PRIM_NAME))
        cae.PointCloudAPI.Apply(result_dataset.GetPrim())
        pcAPI = cae.PointCloudAPI(result_dataset.GetPrim())

        for field in ["velocity", "pressure", "coordinates", "turbulent_kinetic_energy", "turbulent_viscosity"]:
            array = cae.FieldArray.Define(stage, result_dataset.GetPath().AppendChild(field))
            array.CreateFieldAssociationAttr().Set(cae.Tokens.vertex)
            array.GetPrim().CreateAttribute(InferenceDataDelegate.FIELD_NAME_ATTR, Sdf.ValueTypeNames.Token).Set(field)
            array.GetPrim().CreateAttribute(InferenceDataDelegate.KEY_ATTR, Sdf.ValueTypeNames.Token).Set("result")
            array.GetPrim().CreateAttribute(InferenceDataDelegate.TAG_ATTR, Sdf.ValueTypeNames.Token).Set("")
            if field == "coordinates":
                pcAPI.CreateCoordinatesRel().SetTargets({array.GetPath()})
            else:
                result_dataset.GetPrim().CreateRelationship(f'field:{field}').SetTargets({array.GetPath()})

        logger.info(f"Created Triton prim at {self._prim_path}")
        return True

    def undo(self):
        stage = get_context().get_stage()
        if not stage:
            logger.error("No USD stage found")
            return False

        prim = stage.GetPrimAtPath(self._prim_path)
        if prim:
            stage.RemovePrim(self._prim_path)
            logger.info(f"Removed Triton config prim at {self._prim_path}")
            return True
        else:
            logger.warning(f"No prim found at {self._prim_path} to remove")
            return False


class CreateRTWTVisualization(omni.kit.commands.Command):
    def __init__(self, prim_path: str, dataset_path: str, stl_path: str):
        self._prim_path = Sdf.Path(prim_path)
        self._dataset_path = Sdf.Path(dataset_path)
        self._stl_path = Sdf.Path(stl_path)

    def _generate_unit_sphere_mesh_with_uv(self, resolution: float):
        """
        Generates a unit sphere mesh with texture coordinates (UV).

        Args:
        - resolution: int, the number of divisions along latitude and longitude.

        Returns:
        - vertices: np.ndarray, shape (n, 3), the coordinates of the points on the surface.
        - faces: np.ndarray, shape (m, 3), the indices of the vertices forming triangular faces.
        - uv: np.ndarray, shape (n, 2), the UV texture coordinates for each vertex.
        """
        # Create a grid in spherical coordinates
        theta = np.linspace(0, np.pi, resolution)  # latitude (0 to pi)
        phi = np.linspace(0, 2 * np.pi, resolution)  # longitude (0 to 2*pi)

        # Create a meshgrid for spherical coordinates
        theta, phi = np.meshgrid(theta, phi)

        # Convert spherical coordinates to Cartesian coordinates
        x = np.sin(theta) * np.cos(phi)
        y = np.sin(theta) * np.sin(phi)
        z = np.cos(theta)

        # Stack the coordinates into a single array of vertices
        vertices = np.vstack([x.ravel(), y.ravel(), z.ravel()]).T

        # Generate texture coordinates (UV mapping)
        u = phi / (2 * np.pi)  # Normalize phi to range 0 to 1
        v = theta / np.pi  # Normalize theta to range 0 to 1
        uv = np.vstack([u.ravel(), v.ravel()]).T

        # Create faces by connecting the vertices in the grid
        faces = []
        for i in range(resolution - 1):
            for j in range(resolution - 1):
                # Vertices of each quad
                v1 = i * resolution + j
                v2 = v1 + 1
                v3 = v1 + resolution
                v4 = v3 + 1

                # Two triangles per quad
                faces.append([v1, v2, v4])
                faces.append([v1, v4, v3])

        faces = np.array(faces)
        normals = vertices / np.linalg.norm(vertices, axis=1, keepdims=True)
        return vertices, faces.flatten(), uv, normals

    def create_seeds(self, stage: Usd.Stage, path: Sdf.Path):
        coords, faces, st, normals = self._generate_unit_sphere_mesh_with_uv(12)
        glyph = UsdGeom.Mesh.Define(stage, path)
        glyph.CreateExtentAttr().Set([(-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)])
        glyph.CreatePointsAttr().Set(Vt.Vec3fArray.FromNumpy(coords))
        glyph.CreateFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(faces))
        glyph.CreateFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(np.ones(faces.shape[0] // 3) * 3))
        glyph.CreateNormalsAttr().Set(normals)

        xformAPI = UsdGeom.XformCommonAPI(glyph)
        xformAPI.SetScale((0.2, 0.2, 0.2))
        xformAPI.SetTranslate((-1.78, 0.68, 0.5))
        return glyph

    def do(self):
        stage = get_context().get_stage()
        if not stage:
            logger.error("No USD stage found")
            return False

        if stage.GetPrimAtPath(self._prim_path):
            logger.warning(f"Prim already exists at {self._prim_path}")
        else:
            logger.info(f"Creating RTWTVisualization prim at {self._prim_path}")
            dataset_prim = stage.GetPrimAtPath(self._dataset_path)
            if not dataset_prim:
                logger.error(f"No dataset found at {self._dataset_path}")
                return False

            rtwt_vis_prim = UsdGeom.Xform.Define(stage, self._prim_path)

            # TODO: make this configurable.
            xform = UsdGeom.XformCommonAPI(rtwt_vis_prim)
            xform.SetScale((100.0, 100.0, 100.0))
            xform.SetRotate((0.0, 0.0, 90.0))
            xform.SetTranslate((-1.56, 0.84, 0.25))

        if not stage.GetPrimAtPath(self._prim_path.AppendChild("Streamlines")):
            logger.info(f"Creating RTWTVisualization prim at {self._prim_path.AppendChild('Streamlines')}")
            self.create_streamlines(stage, "Streamlines")
        else:
            logger.info("Using existing streamlines")

        if not stage.GetPrimAtPath(self._prim_path.AppendChild("Volumes")):
            logger.info(f"Creating RTWTVisualization prim at {self._prim_path.AppendChild('Volumes')}")
            self.create_volumes(stage, "Volumes")
        else:
            logger.info("Using existing volumes")

        if not stage.GetPrimAtPath(self._prim_path.AppendChild("Slices")):
            logger.info(f"Creating RTWTVisualization prim at {self._prim_path.AppendChild('Slices')}")
            self.create_slices(stage, "Slices")
        else:
            logger.info("Using existing slices")

        if not stage.GetPrimAtPath(self._prim_path.AppendChild("Flow")):
            logger.info(f"Creating RTWTVisualization prim at {self._prim_path.AppendChild('Flow')}")
            self.create_flow(stage, "Flow")
        else:
            logger.info("Using existing flow")

        if not stage.GetPrimAtPath(self._prim_path.AppendChild("InputMesh")):
            logger.info(f"Creating RTWTVisualization prim at {self._prim_path.AppendChild('InputMesh')}")
            self.create_input_mesh(stage, "InputMesh")
        else:
            logger.info("Using existing input mesh")

    def create_streamlines(self, stage: Usd.Stage, name: str):
        # Create streamlines.
        s_scope = UsdGeom.Scope.Define(stage, self._prim_path.AppendChild(name))
        s_scope.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        sphere_prim = self.create_seeds(stage, s_scope.GetPath().AppendChild("Seeds"))
        streamlines_path = s_scope.GetPath().AppendChild("Curves")
        success, _ = omni.kit.commands.execute("CreateCaeNanoVdbStreamlines",
                                               dataset_path=self._dataset_path,
                                               prim_path=streamlines_path)
        if not success:
            logger.error("Failed to create streamlines for RTWT visualization")
            return False

        streamlines_prim = stage.GetPrimAtPath(streamlines_path)
        if not streamlines_prim:
            logger.error(f"No streamlines prim found at {streamlines_path}")
            return False

        ns = "omni:cae:warp:streamlines"
        streamlines_prim.GetRelationship(f"{ns}:seeds").SetTargets({sphere_prim.GetPath()})
        streamlines_prim.GetRelationship(f"{ns}:velocity").SetTargets({self._dataset_path.AppendChild("velocity")})
        streamlines_prim.GetAttribute(f"{ns}:width").Set(0.01)
        return True

    def ini_velocity_colormap(self, prim, forced_opacity: float = None):
        colors = np.array([(0.09381196, 0.3983244, 0.8378378, 0),
                    (0.6644804, 0.8185328, 0.42348802, 0.033584345),
                    (0.7702882, 0.93050194, 0.39160123, 0),
                    (0.98455596, 0.80615556, 0.14445223, 0.03),
                    (0.5984556, 0.4199385, 0.27958736, 0.1),
                    (0.74098885, 0.13662587, 0.7528958, 0.01),
                    (0.3588694, 0.15274072, 0.36293435, 0)])
        if forced_opacity is not None:
            colors[:, 3] = forced_opacity
        prim.GetAttribute("rgbaPoints").Set((colors.tolist()))
        prim.GetAttribute("xPoints").Set(([0, 0.2332, 0.3617, 0.5455, 0.7212, 0.903, 1]))

        # this ensure Kit-CAE doesn't change color map range on us.
        customdata_key = "omni.cae.kit:last_prim_sync"
        prim.SetCustomDataByKey(customdata_key, str(self._dataset_path.AppendChild("velocity")))


    def init_pressure_colormap(self, prim, forced_opacity: float = None):
        colors = np.array([(0.27825743, 0.3783784, 0.013148283, 0),
                (0.5323848, 0.6911197, 0.11207347, 0.01),
                (0.7657152, 0.9150579, 0.59001803, 0),
                (1, 0.99999607, 0.99999, 0),
                (0.9111969, 0.72984296, 0.31663215, 0.015),
                (0.6795367, 0.47977096, 0.070839725, 0),
                (0.6756757, 0.3600125, 0, 0.1),
                (0.35521233, 0.259209, 0.259209, 0)])
        if forced_opacity is not None:
            colors[:, 3] = forced_opacity

        prim.GetAttribute("rgbaPoints").Set((colors.tolist()))
        prim.GetAttribute("xPoints").Set((
            [0, 0.1020979, 0.2378, 0.586, 0.7986, 0.8839, 0.9636, 1]
        ))

        # this ensure Kit-CAE doesn't change color map range on us.
        customdata_key = "omni.cae.kit:last_prim_sync"
        prim.SetCustomDataByKey(customdata_key, str(self._dataset_path.AppendChild("pressure")))


    def create_volumes(self, stage: Usd.Stage, name: str):
        s_scope = UsdGeom.Scope.Define(stage, self._prim_path.AppendChild(name))
        s_scope.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        velocity_path = s_scope.GetPath().AppendChild("VelocityMagnitude")
        omni.kit.commands.execute("CreateCaeNanoVdbIndeXVolume",
                                  prim_path=velocity_path,
                                  dataset_path=self._dataset_path)
        velocity_prim = stage.GetPrimAtPath(velocity_path)
        if not velocity_prim:
            logger.error(f"No velocity prim found at {velocity_path}")
            return False
        UsdGeom.Imageable(velocity_prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        ns = "omni:cae:index:nvdb"
        velocity_prim.GetRelationship(f"{ns}:field").SetTargets({self._dataset_path.AppendChild("velocity")})

        # e.g. /World/CAE/Volumes/VelocityMagnitude/Material/Colormap
        velocity_colormap_path = velocity_path.AppendChild("Material").AppendChild("Colormap")
        if velocity_colormap_prim := stage.GetPrimAtPath(velocity_colormap_path):
            self.ini_velocity_colormap(velocity_colormap_prim)
        else:
            logger.error(f"No velocity colormap prim found at {velocity_colormap_path}")

        # replace shader.
        velocity_shader_path = velocity_path.AppendChild("Material").AppendChild("VolumeShader")
        if velocity_shader_prim := stage.GetPrimAtPath(velocity_shader_path):
            velocity_shader_prim.GetAttribute("info:xac:sourceAsset").Set("xac/rtwt_volume_vec3.xac")
        else:
            logger.error(f"No velocity shader prim found at {velocity_shader_path}")

        # PRESSURE
        pressure_path = s_scope.GetPath().AppendChild("Pressure")
        omni.kit.commands.execute("CreateCaeNanoVdbIndeXVolume",
                                  prim_path=pressure_path,
                                  dataset_path=self._dataset_path)
        pressure_prim = stage.GetPrimAtPath(pressure_path)
        if not pressure_prim:
            logger.error(f"No pressure prim found at {pressure_path}")
            return False
        UsdGeom.Imageable(pressure_prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        pressure_prim.GetRelationship(f"{ns}:field").SetTargets({self._dataset_path.AppendChild("pressure")})

        pressure_colormap_path = pressure_path.AppendChild("Material").AppendChild("Colormap")
        if pressure_colormap_prim := stage.GetPrimAtPath(pressure_colormap_path):
            self.init_pressure_colormap(pressure_colormap_prim)
        else:
            logger.error(f"No pressure colormap prim found at {pressure_colormap_path}")

        return True
    
    def create_slices(self, stage: Usd.Stage, name: str):
        s_scope = UsdGeom.Scope.Define(stage, self._prim_path.AppendChild(name))
        s_scope.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        velocity_path = self._prim_path.AppendChild("Volumes").AppendChild("VelocityMagnitude")
        assert stage.GetPrimAtPath(velocity_path), f"No velocity volume found at {velocity_path}"

        velocity_slice_path = s_scope.GetPath().AppendChild("VelocityMagnitude")
        omni.kit.commands.execute("CreateCaeIndeXVolumeSlice",
                                  prim_path=velocity_slice_path,
                                  dataset_path=velocity_path)
        velocity_slice_prim = stage.GetPrimAtPath(velocity_slice_path)
        if not velocity_slice_prim:
            logger.error(f"No velocity slice prim found at {velocity_slice_path}")
            return False
        UsdGeom.Imageable(velocity_slice_prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        plane_prim = velocity_slice_prim.GetPrimAtPath("Plane")
        xformAPI = UsdGeom.XformCommonAPI(plane_prim)
        xformAPI.SetTranslate((0, 0, 0))
        xformAPI.SetRotate((0, 0, 90))
        xformAPI.SetScale((100, 100, 100))

        if colormap := stage.GetPrimAtPath(velocity_slice_path.AppendChild("Material").AppendChild("Colormap")):
            self.ini_velocity_colormap(colormap, forced_opacity=1.0)
        else:
            logger.error("Failed to initialize velocity slice colormap")

        # replace shader
        if shader := stage.GetPrimAtPath(velocity_slice_path.AppendChild("Material").AppendChild("SliceShader")):
            shader.GetAttribute("info:xac:sourceAsset").Set("xac/rtwt_slice_vec3.xac")
        else:
            logger.error(f"No velocity shader prim found at {velocity_slice_path.AppendChild('Material').AppendChild('VolumeShader')}")

        pressure_path = self._prim_path.AppendChild("Volumes").AppendChild("Pressure")
        assert stage.GetPrimAtPath(pressure_path), f"No pressure volume found at {pressure_path}"

        pressure_slice_path = s_scope.GetPath().AppendChild("Pressure")
        omni.kit.commands.execute("CreateCaeIndeXVolumeSlice",
                                  prim_path=pressure_slice_path,
                                  dataset_path=pressure_path)
        pressure_slice_prim = stage.GetPrimAtPath(pressure_slice_path)
        if not pressure_slice_prim:
            logger.error(f"No pressure slice prim found at {pressure_slice_path}")
            return False

        UsdGeom.Imageable(pressure_slice_prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        plane_prim = pressure_slice_prim.GetPrimAtPath("Plane")
        xformAPI = UsdGeom.XformCommonAPI(plane_prim)
        xformAPI.SetTranslate((0, 0, 0))
        xformAPI.SetRotate((0, 0, 90))
        xformAPI.SetScale((100, 100, 100))

        if colormap := stage.GetPrimAtPath(pressure_slice_path.AppendChild("Material").AppendChild("Colormap")):
            self.init_pressure_colormap(colormap, forced_opacity=1.0)
        else:
            logger.error("Failed to initialize pressure slice colormap")
        return True

    def create_flow(self, stage: Usd.Stage, name: str):
        scope = UsdGeom.Scope.Define(stage, self._prim_path.AppendChild(name))
        scope.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

        # we are going to use Environment from the USD stage
        # this avoid us have to figure out all the complex params we need to figure out.
        emitter_path = scope.GetPath().AppendChild("DataSetEmitter")
        if omni.kit.commands.execute("CreateCaeFlowDataSetEmitter",
                                     prim_path=emitter_path,
                                     dataset_path=self._dataset_path)[0] is False:
            logger.error("Failed to create flow dataset emitter for RTWT visualization")
            return False

        emitter_prim = stage.GetPrimAtPath(emitter_path)
        if not emitter_prim:
            logger.error(f"No emitter prim found at {emitter_path}")
            return False

        ns = "omni:cae:flow:emitter"
        emitter_prim.GetAttribute("enabled").Set(False)

        emitter_prim.GetAttribute("layer").Set(2)  # The prebuilt stage uses this layer
        emitter_prim.GetAttribute("velocityScale").Set(25)  # this helps scale up the velocity for a scaled up world
        emitter_prim.GetRelationship(f"{ns}:velocity").SetTargets({self._dataset_path.AppendChild("velocity")})
        
        # skip coloring Flow for now;
        # emitter_prim.GetRelationship(f"{ns}:colors").SetTargets({self._dataset_path.AppendChild("pressure")})
        return True

    def create_input_mesh(self, stage: Usd.Stage, name: str):
        mesh_path = self._prim_path.AppendChild(name)
        if omni.kit.commands.execute("CreateCaeAlgorithmsExtractExternalFaces",
                                      dataset_path=self._stl_path,
                                      prim_path=mesh_path)[0] is False:
            logger.error(f"Failed to create input mesh at {mesh_path}")
            return False

        mesh_prim = stage.GetPrimAtPath(mesh_path)
        if not mesh_prim:
            logger.error(f"No mesh prim found at {mesh_path}")
            return False

        # Set up the mesh properties
        mesh_prim.GetAttribute("visibility").Set(UsdGeom.Tokens.invisible)
        return True

    def undo(self):
        stage = get_context().get_stage()
        if not stage:
            logger.error("No USD stage found")
            return False

        prim = stage.GetPrimAtPath(self._prim_path)
        if prim:
            stage.RemovePrim(self._prim_path)
            logger.info(f"Removed RTWTVisualization prim at {self._prim_path}")
            return True
        else:
            logger.warning(f"No prim found at {self._prim_path} to remove")
            return False
