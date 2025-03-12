import os
import time
import uuid
import json
import numpy as np
import trimesh
import tritonclient.http as httpclient
from tritonclient.utils import * 

from .file_inference import FileInference

# Bounds for our normalized dataset
BOUNDS = np.array([[-3.105525016784668, -1.7949625253677368, -0.330342], [6.356535, 1.7951075, 2.317086]])
HALF_SIZE = 0.5 * (BOUNDS[1] - BOUNDS[0])
POSITION = 0.5 * (BOUNDS[1] + BOUNDS[0])

NUM_SAMPLE_POINTS = 1_255_000


class Service:
    data = None         # loaded / received data
    extension = ""
    config_request_old = {}
    file_inferences = {}

    def __init__(self,
                 files=[],
                 field_names=[],
                 unnormalize=False,
                 preload=True,
                 prune_points=0,
                 num_points=NUM_SAMPLE_POINTS):
        self.field_names = field_names
        self.unnormalize_data = unnormalize
        self.preload_data = preload
        self.prune_points = prune_points
        self.num_sample_points = num_points

        self._reset_config()

        if len(files) > 0:
            self.from_file = files['from']
            self.to_file = files['to']

            for i in range(self.from_file, self.to_file + 1):
                filepath = FileInference.get_filepath(files, i)
                self.file_inferences[i] = FileInference(filepath)

    def _reset_config(self):
        self.config_request_old['id'] = -1
        self.config_request_old['config'] = -1
        self.config_request_old['multip'] = -1
        # self.config_request_old['params'] = ""    # not used

    def _field_names_reader(self):
        '''Get list of fields in the data dictionary'''

        if self.file_inferences:
            # load fields from a first file
            first_key = next(iter(self.file_inferences))
            self.field_names = self.file_inferences[first_key].get_field_names()
        else:
            if len(self.field_names) == 0:
                raise RuntimeError("No field names set")

        self.field_names.append('sdf_bounds')

        print(f"Data fields: {self.field_names}")

    def _get_data_from_file(self, config_request):

        file_index = int(config_request['id'])
        file_index = int(np.clip(file_index, self.from_file, self.to_file))

        if file_index not in self.file_inferences:
            print(f"ERROR: Requested file with index {file_index} not found!")
            return -1

        if not self.preload_data:
            self.file_inferences[file_index].load_data()

        if self.file_inferences and file_index in self.file_inferences:
            self.data = self.file_inferences[file_index].get_data()

        return file_index

    def _get_data_from_script(self, config_request):

        if config_request == self.config_request_old:
            return

        stl_path = config_request['id']
        stream_velocity = config_request['config']
        multiplier = config_request['multip'] if 'multip' in config_request else 1.0
        multiplier = 1.0 if multiplier < 0.0 else multiplier

        self.config_request_old = config_request

        sample_points = int(self.num_sample_points * multiplier)

        print("STARTING TRITION INFERENCE")
        triton_data = self.triton_inference(stl_path, stream_velocity, sample_points)
        print("ENDING TRITION INFERENCE")

        self.data = triton_data

    @staticmethod
    def prune_point_count(array, field_name):

        print(f"WARNING: Pruning '{field_name}' data! (array.shape={array.shape}, dtype={array.dtype})")

        rng = np.random.default_rng(0)
        levels = np.arange(1024)
        rng.shuffle(levels)
        threshold = int(1024 * (2097152 / array.shape[0]))
        pred = np.less_equal(levels, threshold)
        pred = np.tile(pred, int(array.shape[0] / 1024))
        array = np.compress(pred, array, axis=0)

        print(f"WARNING: Pruned '{field_name}' data! (array.shape={array.shape}, dtype={array.dtype})")

        return array

    def _get_array(self, field_name):
        '''Get numpy array weith specified field name, normalize and compute sdf bounds'''

        if not self.data:
            print(f"ERROR: Data for '{field_name}' does not exist")
            return None

        # This is needed by Flow voxelization
        if field_name == 'sdf_bounds':
            if 'sdf' in self.data:
                p_sdf = self.data.get('sdf')
            else:
                print("ERROR: Could not get 'sdf_bounds', 'sdf' array not found")
                return None

            if 'bounding_box_dims' in self.data:
                bounds = self.data.get('bounding_box_dims')
                halfsize = 0.5 * (bounds[1] - bounds[0])
                position = 0.5 * (bounds[1] + bounds[0])
            else:
                halfsize = HALF_SIZE
                position = POSITION

            sdf_grid_size = p_sdf.shape - np.array([1, 1, 1])
            sdf_cell_size = 2.0 * halfsize / (sdf_grid_size)

            array = 100 * np.array([position - halfsize - 0.5 * sdf_cell_size, position + halfsize + 0.5 * sdf_cell_size], dtype=np.float32)
            return array

        if self.file_inferences:
            first_key = next(iter(self.file_inferences))
            extension = self.file_inferences[first_key].extension
            if extension == '.npz':
                if field_name not in self.data.files:
                    print(f"File does not contain '{field_name}'")
                    return None
            elif extension == '.npy':
                if field_name not in self.data:
                    print(f"File does not contain '{field_name}")
                    return None
            else:
                raise RuntimeError(f"Unsupported filename extension '{self.extension}'")

        array = self.data.get(field_name)
        if array is None:
            print(f"ERROR: Could not get field '{field_name}'")
            return None

        if not isinstance(array, np.ndarray):
            print(f"ERROR: Unsupported field '{field_name}' is not an array")
            return None

        if self.unnormalize_data and (field_name == 'coordinates' or field_name == 'surface_coordinates'):
            print(f"WARNING: Unnormalizing '{field_name}' data! (array.shape={array.shape}, dtype={array.dtype})")

            array = HALF_SIZE * array + POSITION
            array = array.astype(np.float32)

        return array

    def _data_preloader(self):
        '''Cache data from file to a memory'''

        if not self.preload_data:
            return

        print("Caching data to a memory...")

        for file_inference in self.file_inferences.values():
            file_inference.load_data()
            self.data = file_inference.get_data()
            file_arrays = {}
            for field_name in self.field_names:
                array = self._get_array(field_name)
                if array is not None:
                    file_arrays[field_name] = array
                else:
                    print(f"WARNING: Could not prelaoad a field '{field_name}' not in a file")

            if self.prune_points:
                fields_to_prune = ['velocity', 'coordinates', 'pressure']
                for field_name in fields_to_prune:
                    file_arrays[field_name] = Service.prune_point_count(file_arrays[field_name], field_name)

            file_inference.arrays = file_arrays

        self.data = None

    def _request_data(self, config_request):
        '''Get data for current config request'''

        if self.file_inferences:
            file_index = self._get_data_from_file(config_request)
        else:
            file_index = -1
            self._get_data_from_script(config_request)

        if not self.data:
            print(f"WARNING: Could not load data for id {config_request['id']}")

        return file_index

    def _get_data_to_send(self, file_index, field_name, config_request):

        if self.file_inferences and self.preload_data and file_index >= 0:
            if field_name in self.file_inferences[file_index].arrays:
                array = self.file_inferences[file_index].arrays[field_name]
        else:
            array = self._get_array(field_name)
            if array is None:
                return None, None

        # Send the metadata
        metadata = {
            'timestamp': config_request['timestamp'],
            'field_name': str(field_name),
            'id': int(config_request['id']),
            'shape': array.shape,
            'dtype': str(array.dtype),
        }
        return metadata, array

    def _trimesh_to_json(self,trimesh_obj, additional_data=None):
        """Convert a Trimesh object to a JSON-serializable format."""
        # Extract mesh attributes directly from Trimesh
        vertices = trimesh_obj.vertices.tolist()  # Convert to list
        faces = trimesh_obj.faces.tolist()  # List of triangle face indices
        centers = trimesh_obj.triangles_center.tolist()  # Centers of triangles
        surface_areas = trimesh_obj.area_faces.tolist()  # Surface areas of triangles

        if not (vertices and faces):
            raise ValueError("Vertices and faces are required for JSON payload.")

        # Construct JSON payload
        payload = {
            "vertices": vertices,
            "faces": faces,
            "centers": centers,
            "surface_areas": surface_areas,
        }

        # Add additional parameters if provided
        if additional_data:
            payload.update(additional_data)

        return json.dumps(payload)

    def triton_inference(self, id, stream_velocity=30.0, num_sample_points = 20000):
        # Configuration
        IP = os.environ.get("NIM_TRITON_IP_ADDRESS", "localhost")
        TRITON_HTTP_PORT = os.environ.get("NIM_TRITON_HTTP_PORT", "8080")
        MODEL_NAME = "controller"
        TRITON_TIMEOUT = 10 * 60

        # Input parameters
        STL_PATH_FMT = "/data/low_res/detailed_car_%d/aero_suv_low.stl"
        stl_file_path = STL_PATH_FMT % id
        stencil_size = 1  # Example stencil size
        inlet_velocity = stream_velocity # Example inlet velocity
        point_cloud_size = num_sample_points # Example point cloud size
        inference_mode = "volume"  # Example inference mode

       # Read and prepare the STL file
        stl_mesh = trimesh.load(stl_file_path)
        vertices = stl_mesh.vertices.astype(np.float32)  # Nx3
        faces = stl_mesh.faces.astype(np.int32)  # Mx3
        centers = stl_mesh.triangles_center.astype(np.float32)  # Px3
        surface_normals =  stl_mesh.face_normals.astype(np.float32)  # Px3
        surface_areas = stl_mesh.area_faces.astype(np.float32)  # Px1

        # Initialize Triton client
        client = httpclient.InferenceServerClient(url=f"{IP}:{TRITON_HTTP_PORT}", ssl=False)

        # Prepare inputs and outputs
        inputs = []
        outputs = []

        # Input tensors
        inputs.append(httpclient.InferInput("vertices", vertices.shape, "FP32"))
        inputs[-1].set_data_from_numpy(vertices)

        inputs.append(httpclient.InferInput("faces", faces.shape, "INT32"))
        inputs[-1].set_data_from_numpy(faces)

        inputs.append(httpclient.InferInput("centers", centers.shape, "FP32"))
        inputs[-1].set_data_from_numpy(centers)

        inputs.append(httpclient.InferInput("surface_normals", surface_normals.shape, "FP32"))
        inputs[-1].set_data_from_numpy(surface_normals)

        inputs.append(httpclient.InferInput("surface_areas", surface_areas.shape, "FP32"))
        inputs[-1].set_data_from_numpy(surface_areas)

        inputs.append(httpclient.InferInput("STREAM_VELOCITY", [1], "FP32"))
        inputs[-1].set_data_from_numpy(np.array([stream_velocity], dtype=np.float32))

        inputs.append(httpclient.InferInput("STENCIL_SIZE", [1], "INT32"))
        inputs[-1].set_data_from_numpy(np.array([stencil_size], dtype=np.int32))

        inputs.append(httpclient.InferInput("POINT_CLOUD_SIZE", [1], "INT32"))
        inputs[-1].set_data_from_numpy(np.array([point_cloud_size], dtype=np.int32))

        inputs.append(httpclient.InferInput("INFERENCE_MODE", [1], "BYTES"))
        inputs[-1].set_data_from_numpy(np.array([inference_mode], dtype=np.object_))

        # Output tensors
        outputs.append(httpclient.InferRequestedOutput("velocity"))
        outputs.append(httpclient.InferRequestedOutput("coordinates"))
        outputs.append(httpclient.InferRequestedOutput("pressure"))
        outputs.append(httpclient.InferRequestedOutput("turbulent-kinetic-energy"))
        outputs.append(httpclient.InferRequestedOutput("turbulent-viscosity"))
        outputs.append(httpclient.InferRequestedOutput("bounding_box_dims"))
        outputs.append(httpclient.InferRequestedOutput("sdf"))
        outputs.append(httpclient.InferRequestedOutput("ERROR_MESSAGE"))
      
        # Send inference request
        print(f"Sending inference request for {stl_file_path}...")
        start_time = time.time()

        output_data = {}
        try:
            response = client.infer(
                model_name=MODEL_NAME,
                inputs=inputs,
                outputs=outputs,
                request_id=str(uuid.uuid1()),
                timeout=TRITON_TIMEOUT,
            )
            end_time = time.time()

            # Handle response
            error_message = response.as_numpy("ERROR_MESSAGE")[0].decode("utf-8")

            if error_message:
                print("Error from Triton server:", error_message)
            else:
                # Parse outputs
                velocity = response.as_numpy("velocity")  # Nx3
                coordinates = response.as_numpy("coordinates")  # Nx3
                pressure = response.as_numpy("pressure")  # Nx1
                turbulent_kinetic_energy = response.as_numpy("turbulent-kinetic-energy")   # Nx1
                turbulent_viscosity = response.as_numpy("turbulent-viscosity")  # Nx1
                bounding_box_dims = response.as_numpy("bounding_box_dims")  # 2x3
                sdf = response.as_numpy("sdf")

                print("Inference successful!")
                print(f"Velocity shape: {velocity.shape}, dtype: {velocity.dtype}")
                print(f"Coordinates shape: {coordinates.shape}, dtype: {coordinates.dtype}")
                print(f"Pressure shape: {pressure.shape}, dtype: {pressure.dtype}")
                print(f"Turbulent kinetic energy shape: {turbulent_kinetic_energy.shape}, dtype: {turbulent_kinetic_energy.dtype}")
                print(f"Turbulent viscosity shape: {turbulent_viscosity.shape}, dtype: {turbulent_viscosity.dtype}")
                print(f"Bounding box dimensions: {bounding_box_dims.shape}, dtype: {bounding_box_dims.dtype}")
                print(f"SDF shape: {sdf.shape}, dtype: {sdf.dtype}")

                output_data["velocity"]= velocity [0]
                output_data["coordinates"] = coordinates [0]
                output_data["pressure"] = pressure [0]
                output_data["turbulent-kinetic-energy"] = turbulent_kinetic_energy [0]
                output_data["turbulent-viscocity"] = turbulent_viscosity[0]
                output_data["bounding_box_dims"] = bounding_box_dims
                output_data["sdf"] = sdf[0]

            print(f"Inference completed in {end_time - start_time:.2f} seconds.")

        except InferenceServerException as e:
            print(f"Triton inference failed: {e}")

        return output_data