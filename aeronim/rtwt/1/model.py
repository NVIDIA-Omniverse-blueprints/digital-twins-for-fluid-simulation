"""Triton Python backend model for the RTWT (Real-Time Wind Tunnel) inference pipeline.

Each Triton request supplies a serialised USD layer that describes the simulation
state (mesh selection, domain extents, stream velocity).  This model:

1. Parses the USD layer to extract inference parameters.
2. Loads (and caches) the corresponding surface mesh.
3. Builds a structured point-cloud over the volumetric domain.
4. Forwards the geometry and parameters to the upstream "model" Triton ensemble.
5. Converts the raw velocity / pressure outputs into NanoVDB GPU buffers and
   returns them alongside the domain extents.
"""

import os
import traceback
from pathlib import Path

import dav
import numpy as np
import trimesh
import triton_python_backend_utils as pb_utils
import warp as wp
from pxr import Gf, Sdf, Usd

from .logging import get_logger, setup_logger

logger = get_logger()

_UPSTREAM_OUTPUTS = ["velocity", "pressure", "ERROR_MESSAGE"]
_NANOVDB_OUTPUTS = {
    "velocity": "nvdb_velocity",
    "velocity_magnitude": "nvdb_velocity_magnitude",
    "pressure": "nvdb_pressure",
}


def _extract_int(request, name: str) -> int:
    """Return the first element of a named input tensor as a Python int."""
    tensor = pb_utils.get_input_tensor_by_name(request, name)
    return int(tensor.as_numpy().ravel().astype(np.int32, copy=False)[0])


def _extract_str(request, name: str) -> str:
    """Return the first element of a named input tensor as a decoded UTF-8 string."""
    tensor = pb_utils.get_input_tensor_by_name(request, name)
    return tensor.as_numpy().ravel()[0].decode("utf-8")


_SUBLAYER_PATH = "/opt/stages/BaseCAEVariants.usda"


def _load_stage_from_string(usd_string: str) -> Usd.Stage:
    """Parse a USD layer from a string and open it as a stage.

    The layer's sublayer list is replaced with a fixed path to the mounted
    BaseCAEVariants.usda so that variant-set composition resolves correctly
    inside the container regardless of where the caller serialised the layer.
    """
    layer = Sdf.Layer.CreateAnonymous(".usda")
    layer.ImportFromString(usd_string)
    # Redirect sublayers to the mounted filesystem path so composition resolves
    layer.subLayerPaths = [_SUBLAYER_PATH]
    return Usd.Stage.Open(layer, load=Usd.Stage.LoadNone)


def _to_nanovdb_buffer(data: np.ndarray, dims: wp.vec3i, origin: wp.vec3i, voxel_size: wp.vec3f, bg_value) -> np.ndarray:
    """Convert a NumPy array to a serialised NanoVDB buffer via Warp + DAV.

    Scalar fields (shape ``(N,)`` or ``(N, 1)``) are stored as ``float32``
    grids; vector fields (shape ``(N, 3)``) are stored as ``vec3f`` grids.
    The returned array is a flat ``uint8`` byte buffer ready to be wrapped in
    a ``pb_utils.Tensor``.
    """
    if data.ndim == 2 and data.shape[1] == 3:
        wp_array = wp.array(data, dtype=wp.vec3f, device="cuda", copy=False)
    else:
        wp_array = wp.array(data.reshape(-1), dtype=wp.float32, device="cuda", copy=False)

    field = dav.Field.from_array(wp_array, dav.AssociationType.VERTEX)
    nvdb_field = field.to_nanovdb(dims=dims, origin=origin, voxel_size=voxel_size, bg_value=bg_value, device="cuda")
    return nvdb_field.get_data().array().numpy()


class TritonPythonModel:
    """Triton Python backend entry-point for the ``rtwt`` model.

    Triton calls ``initialize`` once at load time, ``execute`` for each
    incoming batch of requests, and ``finalize`` when the model is unloaded.
    """

    def initialize(self, args: dict):
        """Set up logging, initialise Warp, and prepare the mesh cache."""
        setup_logger(int(args["model_instance_device_id"]), args["model_name"])
        wp.init()

        self._model_root = Path(os.environ.get("RTWT_MODEL_ROOT", "/opt/data"))
        self._mesh_cache: dict[Path, dict[str, np.ndarray]] = {}

        logger.info(f"Using RTWT model root: {self._model_root}")

    async def execute(self, requests: list) -> list:
        """Handle a batch of Triton inference requests.

        Each request must supply the following input tensors:

        * ``USD_LAYER``    — serialised USD layer (bytes) describing the scene.
        * ``PRIM_PATH``    — path to the inference prim within that layer.
        * ``STENCIL_SIZE`` — stencil radius passed to the upstream model.
        * ``BATCH_SIZE``   — batch size passed to the upstream model.

        Each response contains:

        * ``nvdb_velocity``           — NanoVDB ``vec3f`` grid (velocity vectors).
        * ``nvdb_velocity_magnitude`` — NanoVDB ``float`` grid (speed).
        * ``nvdb_pressure``           — NanoVDB ``float`` grid (pressure).
        * ``EXTENT_MIN`` / ``EXTENT_MAX`` — IJK domain bounds (``int32[3]``).
        * ``ERROR_MESSAGE``           — empty on success; error text on failure.
        """
        responses = []

        for request in requests:
            try:
                usd_string = _extract_str(request, "USD_LAYER")
                prim_path = _extract_str(request, "PRIM_PATH")
                stencil_size = _extract_int(request, "STENCIL_SIZE")
                batch_size = _extract_int(request, "BATCH_SIZE")

                stage = _load_stage_from_string(usd_string)
                stream_velocity, model_tag, origin, spacing, extent_min, extent_max = \
                    self._extract_params_from_stage(stage, prim_path)

                mesh_tensors = self._get_mesh_tensors(model_tag)
                point_cloud, dims = self._build_point_cloud(origin, spacing, extent_min, extent_max)

                logger.info("=" * 60)
                logger.info(f"Model tag: {model_tag}")
                logger.info(f"Stream velocity: {stream_velocity} m/s")
                logger.info(f"Stencil size: {stencil_size}")
                logger.info(f"Batch size: {batch_size}")
                logger.info(f"Point cloud dims: {tuple(int(v) for v in dims)} ({point_cloud.shape[0]:,} samples)")

                infer_request = pb_utils.InferenceRequest(
                    model_name="model",
                    requested_output_names=_UPSTREAM_OUTPUTS,
                    inputs=[
                        pb_utils.Tensor("vertices", mesh_tensors["vertices"]),
                        pb_utils.Tensor("faces", mesh_tensors["faces"]),
                        pb_utils.Tensor("centers", mesh_tensors["centers"]),
                        pb_utils.Tensor("surface_normals", mesh_tensors["surface_normals"]),
                        pb_utils.Tensor("surface_areas", mesh_tensors["surface_areas"]),
                        pb_utils.Tensor("STREAM_VELOCITY", np.array([stream_velocity], dtype=np.float32)),
                        pb_utils.Tensor("STENCIL_SIZE", np.array([stencil_size], dtype=np.int32)),
                        pb_utils.Tensor("POINT_CLOUD", point_cloud),
                        pb_utils.Tensor("INFERENCE_MODE", np.array(["volume_custom"], dtype=np.object_)),
                        pb_utils.Tensor("BATCH_SIZE", np.array([batch_size], dtype=np.int32)),
                    ],
                )

                logger.info("Sending inference request to 'model'")
                result = await infer_request.async_exec()
                if result.has_error():
                    raise pb_utils.TritonModelException(result.error().message())

                voxel_size = wp.vec3f(float(spacing[0]), float(spacing[1]), float(spacing[2]))
                origin_ijk = wp.vec3i(int(extent_min[0]), int(extent_min[1]), int(extent_min[2]))

                outputs = [pb_utils.Tensor("ERROR_MESSAGE", np.array([""], dtype=np.object_))]
                upstream_error = pb_utils.get_output_tensor_by_name(result, "ERROR_MESSAGE")
                if upstream_error is not None:
                    err_value = upstream_error.as_numpy().ravel()[0].decode("utf-8")
                    if err_value:
                        outputs[0] = pb_utils.Tensor("ERROR_MESSAGE", np.array([err_value], dtype=np.object_))
                        responses.append(pb_utils.InferenceResponse(output_tensors=outputs))
                        logger.error(f"Upstream model error: {err_value}")
                        continue

                velocity = pb_utils.get_output_tensor_by_name(result, "velocity").as_numpy()
                pressure = pb_utils.get_output_tensor_by_name(result, "pressure").as_numpy()
                if velocity.ndim == 3 and velocity.shape[0] == 1:
                    velocity = velocity.squeeze(0)
                if pressure.ndim == 3 and pressure.shape[0] == 1:
                    pressure = pressure.squeeze(0)
                if pressure.ndim == 2 and pressure.shape[1] == 1:
                    pressure = pressure.squeeze(1)
                velocity_magnitude = np.linalg.norm(velocity, axis=1).astype(np.float32, copy=False)

                outputs.append(
                    pb_utils.Tensor(
                        _NANOVDB_OUTPUTS["velocity"],
                        _to_nanovdb_buffer(
                            velocity,
                            dims=dims,
                            origin=origin_ijk,
                            voxel_size=voxel_size,
                            bg_value=wp.vec3f(0.0, 0.0, 0.0),
                        ),
                    )
                )
                outputs.append(
                    pb_utils.Tensor(
                        _NANOVDB_OUTPUTS["velocity_magnitude"],
                        _to_nanovdb_buffer(
                            velocity_magnitude,
                            dims=dims,
                            origin=origin_ijk,
                            voxel_size=voxel_size,
                            bg_value=0.0,
                        ),
                    )
                )
                outputs.append(
                    pb_utils.Tensor(
                        _NANOVDB_OUTPUTS["pressure"],
                        _to_nanovdb_buffer(
                            pressure,
                            dims=dims,
                            origin=origin_ijk,
                            voxel_size=voxel_size,
                            bg_value=0.0,
                        ),
                    )
                )

                outputs.append(pb_utils.Tensor("EXTENT_MIN", extent_min))
                outputs.append(pb_utils.Tensor("EXTENT_MAX", extent_max))

                logger.info(
                    "NanoVDB conversion complete: "
                    + ", ".join(
                        f"{tensor.name()}~{tensor.shape()[0] / (1024 * 1024):,.1f} MB"
                        for tensor in outputs
                        if tensor.name() not in ("ERROR_MESSAGE", "EXTENT_MIN", "EXTENT_MAX")
                    )
                )
                responses.append(pb_utils.InferenceResponse(output_tensors=outputs))

            except Exception as exc:
                traceback.print_exc()
                logger.error(f"Inference error: {exc}")
                responses.append(
                    pb_utils.InferenceResponse(
                        output_tensors=[
                            pb_utils.Tensor("ERROR_MESSAGE", np.array([str(exc)], dtype=np.object_))
                        ]
                    )
                )

        return responses

    def finalize(self) -> None:
        """Called by Triton when the model is being unloaded."""
        logger.info("Finalized")

    def _extract_params_from_stage(
        self, stage: Usd.Stage, prim_path: str
    ) -> tuple[float, str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Read inference parameters from the USD stage.

        Returns ``(stream_velocity, model_tag, origin, spacing, extent_min, extent_max)``
        where the last four arrays are ``float32`` / ``int32`` vectors of length 3
        describing the voxel-grid domain in IJK space.
        """
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            raise ValueError(f"Prim not found at path: {prim_path}")

        stream_velocity = float(prim.GetAttribute("omni:rtwt:inference:velocity").Get())

        model_rel = prim.GetRelationship("cae:viz:dataset_selection:model:target")
        model_prim = stage.GetPrimAtPath(model_rel.GetForwardedTargets()[0])
        model_tag = str(model_prim.GetAttribute("omni:rtwt:model:tag").Get())

        domain_rel = prim.GetRelationship("cae:viz:dataset_selection:domain:target")
        domain_prim = stage.GetPrimAtPath(domain_rel.GetForwardedTargets()[0])
        origin = np.array(domain_prim.GetAttribute("cae:vtk:origin").Get(), dtype=np.float32)
        spacing = np.array(domain_prim.GetAttribute("cae:vtk:spacing").Get(), dtype=np.float32)
        extent_min = np.array(domain_prim.GetAttribute("cae:vtk:minExtent").Get(), dtype=np.int32)
        extent_max = np.array(domain_prim.GetAttribute("cae:vtk:maxExtent").Get(), dtype=np.int32)

        logger.info(f"Extracted from USD: model_tag={model_tag}, stream_velocity={stream_velocity}")
        return stream_velocity, model_tag, origin, spacing, extent_min, extent_max

    def _get_mesh_tensors(self, model_tag: str) -> dict[str, np.ndarray]:
        """Load and cache the surface mesh for *model_tag*.

        Returns a dict with keys ``vertices``, ``faces``, ``centers``,
        ``surface_normals``, and ``surface_areas`` as ``float32`` / ``int32``
        NumPy arrays, ready to be passed directly to the upstream Triton model.
        Meshes are kept in ``_mesh_cache`` so repeated requests for the same
        tag skip disk I/O.
        """
        mesh_path = self._resolve_model_path(model_tag)
        if mesh_path not in self._mesh_cache:
            logger.info(f"Loading mesh: {mesh_path}")
            mesh = trimesh.load_mesh(str(mesh_path), process=False)
            self._mesh_cache[mesh_path] = {
                "vertices": np.asarray(mesh.vertices, dtype=np.float32),
                "faces": np.asarray(mesh.faces, dtype=np.int32),
                "centers": np.asarray(mesh.triangles_center, dtype=np.float32),
                "surface_normals": np.asarray(mesh.face_normals, dtype=np.float32),
                "surface_areas": np.asarray(mesh.area_faces, dtype=np.float32),
            }
        return self._mesh_cache[mesh_path]

    def _resolve_model_path(self, model_tag: str) -> Path:
        """Resolve *model_tag* to an absolute mesh path under ``_model_root``.

        Raises ``ValueError`` if the resolved path escapes the model root
        (path-traversal guard) and ``FileNotFoundError`` if the file is absent.
        """
        tag_path = Path(model_tag)
        candidate = (self._model_root / tag_path).resolve()
        root_resolved = self._model_root.resolve()
        if root_resolved not in candidate.parents and candidate != root_resolved:
            raise ValueError(f"MODEL_TAG escapes RTWT model root: {model_tag}")
        if not candidate.exists():
            raise FileNotFoundError(f"Model mesh not found for tag '{model_tag}' at {candidate}")
        return candidate

    def _build_point_cloud(
        self, origin: np.ndarray, spacing: np.ndarray, extent_min: np.ndarray, extent_max: np.ndarray
    ) -> tuple[np.ndarray, wp.vec3i]:
        """Build a dense point-cloud over the voxel domain.

        Generates world-space XYZ coordinates for every voxel centre in the
        IJK range ``[extent_min, extent_max]`` (inclusive) using the grid
        *origin* and *spacing*.  Returns ``(point_cloud, dims)`` where
        ``point_cloud`` has shape ``(N, 3)`` in Fortran (IJK-major) order and
        ``dims`` is the corresponding ``wp.vec3i`` voxel count.
        """
        ii = np.arange(extent_min[0], extent_max[0] + 1, dtype=np.float32)
        jj = np.arange(extent_min[1], extent_max[1] + 1, dtype=np.float32)
        kk = np.arange(extent_min[2], extent_max[2] + 1, dtype=np.float32)
        gi, gj, gk = np.meshgrid(ii, jj, kk, indexing="ij")
        point_cloud = np.stack(
            [
                origin[0] + gi * spacing[0],
                origin[1] + gj * spacing[1],
                origin[2] + gk * spacing[2],
            ],
            axis=-1,
        ).reshape(-1, 3, order="F")

        dims = wp.vec3i(
            int(extent_max[0] - extent_min[0] + 1),
            int(extent_max[1] - extent_min[1] + 1),
            int(extent_max[2] - extent_min[2] + 1),
        )
        return np.asarray(point_cloud, dtype=np.float32), dims
