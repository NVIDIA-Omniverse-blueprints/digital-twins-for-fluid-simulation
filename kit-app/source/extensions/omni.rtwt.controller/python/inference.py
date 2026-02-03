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
import os
import uuid
from tritonclient.http.aio import InferenceServerClient
from tritonclient.http import InferenceServerException, InferInput, InferRequestedOutput
from tritonclient.utils import np_to_triton_dtype 
import trimesh
import numpy as np
from carb.settings import get_settings
import carb.events
from omni.kit.app import get_app
import asyncio
from pxr import Usd
from omni.cae.schema import cae
from omni.cae.data import usd_utils
from omni.cae.algorithms.core import Algorithm

from .delegate import InferenceDataDelegate

# non-public API use
from omni.cae.data.impl import cache
from omni.cae.algorithms.core.playback import get_controller

logger = getLogger(__name__)


class InferenceData:
    coordinates: np.ndarray
    velocity: np.ndarray
    pressure: np.ndarray
    turbulent_kinetic_energy: np.ndarray
    turbulent_viscosity: np.ndarray
    bounding_box_dims: np.ndarray
    sdf: np.ndarray

    def __init__(self, coordinates: np.ndarray, velocity: np.ndarray, pressure: np.ndarray,
                 turbulent_kinetic_energy: np.ndarray, turbulent_viscosity: np.ndarray,
                 bounding_box_dims: np.ndarray, sdf: np.ndarray):
        self.coordinates = coordinates.squeeze()
        self.velocity = velocity.squeeze()
        self.pressure = pressure.squeeze()
        self.turbulent_kinetic_energy = turbulent_kinetic_energy.squeeze()
        self.turbulent_viscosity = turbulent_viscosity.squeeze()
        self.bounding_box_dims = bounding_box_dims.squeeze()
        self.sdf = sdf.squeeze()

    @property
    def velocity_magnitude(self) -> np.ndarray:
        return np.linalg.norm(self.velocity, axis=1)

    def save_npz(self, fname: str):
        logger.warning(f"Saving InferenceData to {fname}")
        os.makedirs(os.path.dirname(fname), exist_ok=True)
        np.savez_compressed(fname, coordinates=self.coordinates, velocity=self.velocity,
                            pressure=self.pressure, turbulent_kinetic_energy=self.turbulent_kinetic_energy,
                            turbulent_viscosity=self.turbulent_viscosity, bounding_box_dims=self.bounding_box_dims,
                            sdf=self.sdf)


class InputData:
    points: np.ndarray
    faceVertexCounts: np.ndarray
    faceVertexIndices: np.ndarray

    def __init__(self, points: np.ndarray, faceVertexCounts: np.ndarray, faceVertexIndices: np.ndarray):
        self.points = points
        self.faceVertexCounts = faceVertexCounts
        self.faceVertexIndices = faceVertexIndices

    @classmethod
    def from_stlmesh(cls, stlmesh: trimesh.Trimesh) -> "InputData":
        return cls(points=stlmesh.vertices.astype(np.float32, copy=False),
                   faceVertexCounts=np.full((len(stlmesh.faces),), 3, dtype=np.int32),
                   faceVertexIndices=stlmesh.faces.flatten().astype(np.int32, copy=False))


class Triton(Algorithm):
    ns = "omni:rtwt:triton"
    stl_cache = {}

    @staticmethod
    def push_data():
        # this is a temporary workaround to force all existing algorithms to execute
        # since currently Kit-CAE algorithms don't automatically update when their datasets change.
        if rt_controller := get_controller():
            for path, algo in rt_controller._algorithms.items():
                if not isinstance(algo, Triton):
                    logger.warning(f"Forcing re-execution of {path} ({type(algo)})")
                    algo._needs_init = True

        # clear all Kit-CAE caches
        cache.clear()  # clear cache to ensure data is reloaded next time

    def __init__(self, prim: Usd.Prim):
        super().__init__(prim, ["RtwtTritonAPI"])

        settings = get_settings()
        self._stl_path_format = settings.get_as_string("/exts/omni.rtwt.controller/stl_path_format")
        self._debug_inference_data_path = settings.get_as_string("/exts/omni.rtwt.controller/debug_inference_data_path")
        self._triton_http_url = settings.get_as_string("/exts/omni.rtwt.controller/triton_http_url") or "localhost:8080"
        self._triton_timeout = settings.get_as_int("/exts/omni.rtwt.controller/triton_timeout_s") or 60 * 10
        self._triton_model_name = settings.get_as_string("/exts/omni.rtwt.controller/triton_model_name") or "controller"
        self._triton_batch_size = settings.get_as_int("/exts/omni.rtwt.controller/triton_batch_size") or 128_000
        self._triton_stencil_size = settings.get_as_int("/exts/omni.rtwt.controller/triton_stencil_size") or 1
        self._triton_inference_mode = settings.get_as_string("/exts/omni.rtwt.controller/triton_inference_mode") or "volume"


        logger.warning("Triton initialized")
        logger.warning("  stl_path_format: %s", self._stl_path_format)
        logger.warning("  triton_http_url: %s", self._triton_http_url)
        logger.warning("  triton_timeout: %s", self._triton_timeout)
        logger.warning("  debug_inference_data_path: %s", self._debug_inference_data_path)

    def send_message(self, message: str):
        logger.warning("Sending 'inference_complete_signal' with message: %s", message)
        INFERENCE_COMPLETE_EVENT = carb.events.type_from_string("inference_complete_signal_kit")
        # Publish event with payload
        bus = get_app().get_message_bus_event_stream()
        bus.push(INFERENCE_COMPLETE_EVENT, payload={"message": message})

    async def execute_impl(self, timeCode: Usd.TimeCode) -> None:
        logger.info("Triton algorithm executing ...")
        if not usd_utils.get_attribute(self.prim, f"{self.ns}:enabled", timeCode, quiet=True):
            logger.warning("Triton inferencing is disabled.")
            return

        model_id = usd_utils.get_attribute(self.prim, f"{self.ns}:modelId", timeCode)
        stream_velocity = usd_utils.get_attribute(self.prim, f"{self.ns}:streamVelocity", timeCode)
        point_cloud_size = usd_utils.get_attribute(self.prim, f"{self.ns}:pointCloudSize", timeCode)
        self.send_message("inference_start")
        data = await self.do_inference(model_id, stream_velocity, point_cloud_size)
        self.send_message("inference_complete")
        if data is None:
            logger.error("Inference failed, no data returned")
            return

        # now update the dataset prims
        with self.edit_context:
            if child_input := self.prim.GetChild("Input"):
                for child in child_input.GetChildren():
                    if attr := child.GetAttribute(InferenceDataDelegate.TAG_ATTR):
                        attr.Set(f"{model_id}")
            if child_result := self.prim.GetChild("Result"):
                for child in child_result.GetChildren():
                    if attr := child.GetAttribute(InferenceDataDelegate.TAG_ATTR):
                        attr.Set(f"{id(data)}")

        # data data the inference data delegate
        if delegate := InferenceDataDelegate.get_instance():
            delegate.set_data("input", f"{model_id}", InputData.from_stlmesh(Triton.stl_cache[model_id]))
            delegate.set_data("result", f"{id(data)}", data)
        self.push_data()

    async def do_inference(self, car_model_id: int, stream_velocity: float, point_cloud_size: int):
        logger.warning(f"Triggering inference for model ID {car_model_id} with stream velocity {stream_velocity} and point cloud size {point_cloud_size}")
        client = InferenceServerClient(url=self._triton_http_url, verbose=False)
        try:
            response = await client.infer(model_name=self._triton_model_name,
                                          inputs=await self._create_inputs(car_model_id, stream_velocity, point_cloud_size),
                                          outputs=await self._create_outputs(),
                                          request_id=str(uuid.uuid1()),
                                          timeout=self._triton_timeout)

            if err := response.as_numpy("ERROR_MESSAGE")[0].decode("utf-8"):
                logger.error("Inference Error Message: %s", err)
                inference_data = None
            else:
                logger.info("Inference successful")
                velocity = response.as_numpy("velocity")  # Nx3
                coordinates = response.as_numpy("coordinates")  # Nx3
                pressure = response.as_numpy("pressure")  # Nx1
                turbulent_kinetic_energy = response.as_numpy("turbulent-kinetic-energy")   # Nx1
                turbulent_viscosity = response.as_numpy("turbulent-viscosity")  # Nx1
                bounding_box_dims = response.as_numpy("bounding_box_dims")  # 2x3
                sdf = response.as_numpy("sdf")

                logger.warning("Inference successful!")
                logger.warning(f"Velocity shape: {velocity.shape}, dtype: {velocity.dtype}")
                logger.warning(f"Coordinates shape: {coordinates.shape}, dtype: {coordinates.dtype}")
                logger.warning(f"Pressure shape: {pressure.shape}, dtype: {pressure.dtype}")
                logger.warning(f"Turbulent kinetic energy shape: {turbulent_kinetic_energy.shape}, dtype: {turbulent_kinetic_energy.dtype}")
                logger.warning(f"Turbulent viscosity shape: {turbulent_viscosity.shape}, dtype: {turbulent_viscosity.dtype}")
                logger.warning(f"Bounding box dimensions: {bounding_box_dims.shape}, dtype: {bounding_box_dims.dtype}")
                logger.warning(f"SDF shape: {sdf.shape}, dtype: {sdf.dtype}")

                inference_data = InferenceData(
                    coordinates=coordinates,
                    velocity=velocity,
                    pressure=pressure,
                    turbulent_kinetic_energy=turbulent_kinetic_energy,
                    turbulent_viscosity=turbulent_viscosity,
                    bounding_box_dims=bounding_box_dims,
                    sdf=sdf
                )
                if self._debug_inference_data_path:
                    inference_data.save_npz(os.path.join(self._debug_inference_data_path,
                                                         f"inference_data_cm.{car_model_id}_sv.{stream_velocity}_pc.{point_cloud_size}.npz"))

        except InferenceServerException as e:
            logger.error(f"Inference failed: {e}")
            inference_data = None
        except OSError as e:
            logger.error(f"OS error during inference: {e}")
            inference_data = None
        finally:
            await client.close()

        return inference_data

    async def _load_mesh(self, car_model_id) -> trimesh.Trimesh:
        if car_model_id in self.stl_cache:
            return self.stl_cache[car_model_id]

        fname = self._stl_path_format.format(car_model_id)
        logger.warning("Loading STL: %s", fname)
        if not os.path.exists(fname):
            raise FileNotFoundError(f"STL file not found: {fname}")
        stlmesh = await asyncio.to_thread(trimesh.load_mesh, fname)
        Triton.stl_cache[car_model_id] = stlmesh
        logger.warning(f"STL loaded with {len(stlmesh.faces):,} triangles")
        return stlmesh

    async def _create_inputs(self, car_model_id: int, stream_velocity: float, point_cloud_size: int) -> list[InferInput]:
        mesh = await self._load_mesh(car_model_id)

        inputs = []
        inputs.append(InferInput("vertices", mesh.vertices.shape, np_to_triton_dtype(np.float32)))
        inputs[-1].set_data_from_numpy(mesh.vertices.astype(np.float32, copy=False))

        inputs.append(InferInput("faces", mesh.faces.shape, np_to_triton_dtype(np.int32)))
        inputs[-1].set_data_from_numpy(mesh.faces.astype(np.int32, copy=False))

        inputs.append(InferInput("centers", mesh.triangles_center.shape, np_to_triton_dtype(np.float32)))
        inputs[-1].set_data_from_numpy(mesh.triangles_center.astype(np.float32, copy=False))

        inputs.append(InferInput("surface_normals", mesh.face_normals.shape, np_to_triton_dtype(np.float32)))
        inputs[-1].set_data_from_numpy(mesh.face_normals.astype(np.float32, copy=False))

        inputs.append(InferInput("surface_areas", mesh.area_faces.shape, np_to_triton_dtype(np.float32)))
        inputs[-1].set_data_from_numpy(mesh.area_faces.astype(np.float32, copy=False))

        inputs.append(InferInput("STREAM_VELOCITY", [1], np_to_triton_dtype(np.float32)))
        inputs[-1].set_data_from_numpy(np.array([stream_velocity], dtype=np.float32))

        inputs.append(InferInput("STENCIL_SIZE", [1], np_to_triton_dtype(np.int32)))
        inputs[-1].set_data_from_numpy(np.array([self._triton_stencil_size], dtype=np.int32))

        inputs.append(InferInput("POINT_CLOUD_SIZE", [1], np_to_triton_dtype(np.int32)))
        inputs[-1].set_data_from_numpy(np.array([point_cloud_size], dtype=np.int32))

        inputs.append(InferInput("INFERENCE_MODE", [1], "BYTES"))
        inputs[-1].set_data_from_numpy(np.array([self._triton_inference_mode], dtype=np.object_))

        inputs.append(InferInput("BATCH_SIZE", [1], "INT32"))
        inputs[-1].set_data_from_numpy(np.array([self._triton_batch_size], dtype=np.int32))

        return inputs

    async def _create_outputs(self) -> list[InferRequestedOutput]:
        outputs = []
        outputs.append(InferRequestedOutput("velocity"))
        outputs.append(InferRequestedOutput("coordinates"))
        outputs.append(InferRequestedOutput("pressure"))
        outputs.append(InferRequestedOutput("turbulent-kinetic-energy"))
        outputs.append(InferRequestedOutput("turbulent-viscosity"))
        outputs.append(InferRequestedOutput("bounding_box_dims"))
        outputs.append(InferRequestedOutput("sdf"))
        outputs.append(InferRequestedOutput("ERROR_MESSAGE"))
        return outputs

