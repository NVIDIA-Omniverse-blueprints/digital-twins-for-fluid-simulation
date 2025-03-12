# Copyright 2019-2023 NVIDIA CORPORATION

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

import asyncio

import carb
import carb.profiler
import carb.settings
import numpy as np

import asyncio
import threading
import functools
import ctypes
import time

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import omni.ext
import omni.ui as ui
import omni.usd
import warp as wp
import warp.render

import omni.cgns as ocgns
import time

from pxr import Gf, Sdf, Tf, Usd, UsdGeom, Vt, UsdShade
from omni.kit.window.file_importer import get_file_importer
from omni.kit.window.popup_dialog import MessageDialog
from ov.cgns import (
    advect_vector_field,
    upload_vdb_cpu_to_gpu,
    return_array,
    return_field_array,
    save_tetmesh_vtk,
    generate_hull,
    hull_mesh_to_stage,
    compress_vertices,
    points_to_usd
)

import carb.events
import omni.kit.app

import omni.stageupdate

from pxr import Gf, Sdf, Tf, Usd, UsdGeom, Vt


INFERENCE_COMPLETE_EVENT= carb.events.type_from_string("inference_complete_signal_kit")

g_stage_update = None
g_stage_stage_subscription = None
g_stage_vdb_callback_fn = None
g_stage_data_callback_fn = None
g_stage_timestamp_data = 0
g_stage_timestamp_vdb = 0

def send_message( message):
    print(f"[UI] Sending message: {message}")   

    # Publish event with payload
    bus = omni.kit.app.get_app().get_message_bus_event_stream()
    bus.push(INFERENCE_COMPLETE_EVENT, payload={"message": message})

def stage_update_callback(currentTime, elapsedSecs):
    global g_stage_timestamp_data
    global g_stage_timestamp_vdb
    global g_stage_vdb_callback_fn
    global g_stage_data_callback_fn
    icgns = ocgns.get_interface()
    timestamp = icgns.get_latest_timestamp()
    if timestamp != 0 and timestamp != g_stage_timestamp_vdb:
        if icgns.has_data_timestamp("flow_nvdb", timestamp):
            carb.log_info(f"streamline stage_update callback on flow_vdb {timestamp}")
            g_stage_timestamp_vdb = timestamp
            if g_stage_vdb_callback_fn is not None:
                g_stage_vdb_callback_fn(timestamp)
            send_message("inference_complete")      
    if timestamp != 0 and timestamp != g_stage_timestamp_data:
        if (icgns.has_data_timestamp("coordinates", timestamp) and
                icgns.has_data_timestamp("velocity", timestamp) and
                icgns.has_data_timestamp("pressure", timestamp)):
            carb.log_info(f"streamline stage_update callback on coordinates/velocity/pressure {timestamp}")
            g_stage_timestamp_data = timestamp
            if g_stage_data_callback_fn is not None:
                g_stage_data_callback_fn(timestamp)
            send_message("inference_complete")       


def stage_update_init():
    global g_stage_update
    global g_stage_stage_subscription
    if g_stage_update is not None:
        return
    g_stage_update = omni.stageupdate.get_stage_update_interface()
    g_stage_stage_subscription = g_stage_update.create_stage_update_node("cgns_streamlines", on_update_fn=stage_update_callback)
    return

def stage_update_release():
    global g_stage_stage_subscription
    global g_stage_update
    g_stage_stage_subscription = None
    g_stage_update = None
    return

def stage_update_register_vdb_callback(callback_str, callback_fn):
    global g_stage_vdb_callback_fn
    g_stage_vdb_callback_fn = callback_fn
    return

def stage_update_register_data_callback(callback_str, callback_fn):
    global g_stage_data_callback_fn
    g_stage_data_callback_fn = callback_fn
    return

def stage_update_unregister_vdb_callback(callback_str):
    global g_stage_vdb_callback_fn
    g_stage_vdb_callback_fn = None
    return

def stage_update_unregister_data_callback(callback_str):
    global g_stage_data_callback_fn
    g_stage_data_callback_fn = None
    return


# Functions and vars are available to other extensions as usual in python: `ov.cgns_ui.some_public_function(x)`
def some_public_function(x: int):
    print(f"[ov.cgns_ui] some_public_function was called with {x}")
    return x**x



def compute_bbox(prim: Usd.Prim) -> Gf.Range3d:
    """
    Compute Bounding Box using ComputeWorldBound at UsdGeom.Imageable
    See https://openusd.org/release/api/class_usd_geom_imageable.html

    Args:
        prim: A prim to compute the bounding box.
    Returns:
        A range (i.e. bounding box), see more at: https://openusd.org/release/api/class_gf_range3d.html
    """
    imageable = UsdGeom.Imageable(prim)
    time = Usd.TimeCode.Default()   # The time at which we compute the bounding box
    bound = imageable.ComputeWorldBound(time, UsdGeom.Tokens.default_)
    bound_range = bound.ComputeAlignedBox()
    return bound_range


def make_basis_curve(stage, vertices, scalars, idx_count, N, path="/World/streamlines", width=0.5, pressure=False, xmin=None, xmax=None):
    prim = stage.GetPrimAtPath(path)
    if prim:
        basis_curve = UsdGeom.BasisCurves(prim)
        # stage.RemovePrim(path)
    else:
        basis_curve = UsdGeom.BasisCurves.Define(stage, path)
        basis_curve.CreatePointsAttr()
        basis_curve.CreateCurveVertexCountsAttr()
        basis_curve.CreateTypeAttr().Set("linear")
        basis_curve.CreateWidthsAttr()  # .Set(2*np.ones(len(idx_count)))

    basis_curve.GetWidthsAttr().Set((width * np.ones(N)).tolist())
    basis_curve.SetWidthsInterpolation("constant")

    vertices_vt = Vt.Vec3fArray.FromNumpy(vertices)


    basis_curve.GetPointsAttr().Set(vertices_vt)
    basis_curve.GetCurveVertexCountsAttr().Set(idx_count)


    # colors
    from matplotlib import cm
    from matplotlib.colors import Normalize, LinearSegmentedColormap

    # try to use Flow colormap
    if pressure:
        primColormap = stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowOffscreen_pressure/colormap")
        primMinMax = stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowRender_pressure/rayMarch")
    else:
        primColormap = stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowOffscreen/colormap")
        primMinMax = stage.GetPrimAtPath("/World/Flow_CFD/CFDResults/flowRender/rayMarch")

    if primColormap:
        color_colors = primColormap.GetAttribute("rgbaPoints").Get()
        #color_colors_noAlpha = [t[:-1] for t in color_colors]
        color_x = primColormap.GetAttribute("xPoints").Get()
        # ensure points start and end exactly at [0,1]
        color_x = list(color_x)
        color_x[0] = 0.0
        color_x[-1] = 1.0

        # get xmin/xmax from Flow
        xmax = primMinMax.GetAttribute("colormapXMax").Get()
        xmin = primMinMax.GetAttribute("colormapXMin").Get()

        print(f"points X = {color_x}, colors={color_colors}")

        colormap = LinearSegmentedColormap.from_list('flow', list(zip(color_x, color_colors)), N=256)
        if isinstance(xmin, type(None)):
            xmin = np.min(scalars)
        if isinstance(xmax, type(None)):
            xmax = np.max(scalars)

        # print("Using Flow colormap with min/max=", xmin, xmax)
        norm = Normalize(vmin=xmin, vmax=xmax)
        colors = colormap(norm(scalars))

    else:
        norm = Normalize(vmin=np.min(scalars), vmax=np.max(scalars))
        colors = cm.viridis(norm(scalars))

    basis_curve.GetBasisAttr().Set("catmullRom")
    colorAttr = basis_curve.GetPrim().GetAttribute("primvars:displayColor")
    colorAttr.SetMetadata("interpolation", "vertex")
    colorAttr.Set(colors[:,0:3])

    return basis_curve

@carb.profiler.profile
def getMesh(stage, path, force_elem_type=np.int32, get_vertices=False):
    mesh_prim = stage.GetPrimAtPath(path)  # "/World/Zone1/volume/GridElements"

    if get_vertices:
        coords_x = return_array(mesh_prim, "coordsXHdf5Path")
        coords_y = return_array(mesh_prim, "coordsYHdf5Path")
        coords_z = return_array(mesh_prim, "coordsZHdf5Path")
        xyz_wp = wp.array(np.column_stack((coords_x, coords_y, coords_z)), dtype=wp.vec3f)
    else:
        xyz_wp = None

    idx_elem = return_array(mesh_prim, "meshConnectivityHdf5Path") - 1 # -1 because CGNS uses 1-based indexing!
    try:
        idx_offset = return_array(mesh_prim, "meshOffsetHdf5Path")
        idx_offset = wp.array(idx_offset.astype(force_elem_type))
    except:
        idx_offset = None


    mesh_type = mesh_prim.GetAttribute("meshType").Get()
    return (xyz_wp, wp.array(idx_elem.astype(force_elem_type)), idx_offset, mesh_type)

@carb.profiler.profile
def getTetMesh(stage) -> list:
    zoneGroupPaths = getZoneGroupPaths(stage)
    tetMeshes = []

    for zonePath in zoneGroupPaths:
        prim = stage.GetPrimAtPath(zonePath)
        if prim:
            for child in prim.GetAllChildren():
                if child.HasAttribute("meshType"):
                    meshType = child.GetAttribute("meshType").Get()
                    print("mesh type",meshType)
                    if meshType:
                        if meshType == "TETRA_4" or meshType == "HEXA_8":
                            tetMeshes.append(child)
    return tetMeshes


def triangulate_hull_fn():
    stage = omni.usd.get_context().get_stage()

    mesh_prims = {}

    zone_paths = getZoneGroupPaths(stage)
    for (zone_path, zone) in zone_paths.items():
        mesh_prims[zone] = []
        prim = stage.GetPrimAtPath(zone_path)
        for child in prim.GetAllChildren():
            if child.GetTypeName() == "CGNSMeshAsset":
                mesh_prims[zone].append(child)

    facet_limit = 1000000
    all_zones_vertices = {}
    for (zone_path, zone) in zone_paths.items():
        need_vertices = True
        for mesh_prim in mesh_prims[zone]:

            vertices_maybe, idx_elem_allvtx, idx_offset_maybe, mesh_type = getMesh(stage, str(mesh_prim.GetPath()), get_vertices=need_vertices)
            if isinstance(idx_offset_maybe, np.ndarray):
                num_facets = idx_offset_maybe.shape[0]
                if num_facets > facet_limit:
                    print(f"Skipping {mesh_prim.GetName()} because it has too many faces and is probably a volumetric collection ({num_facets} > {facet_limit})")
                    continue

            min_idx_value = idx_elem_allvtx.numpy().min()
            if min_idx_value < 0:
                print(f"WARNING: Skipping Mesh {mesh_prim.GetName()} because connectivity has negative values! (min={min_idx_value})")
                continue
            if need_vertices:
                all_zones_vertices[zone] = vertices_maybe
                need_vertices = False


            vertices, idx_elem = compress_vertices(all_zones_vertices[zone], idx_elem_allvtx)

            if mesh_type == "TRI_3":
                hull_mesh_to_stage(vertices.numpy(), idx_elem.numpy(), idx_offset_maybe, stage, f"/World/{zone}/viz_meshes", 3, str(mesh_prim.GetName()))
            elif mesh_type == "TETRA_4":
                idx_tri = generate_hull(idx_elem, mesh_type)
                hull_mesh_to_stage(vertices.numpy(), idx_tri.numpy(), idx_offset_maybe, stage, f"/World/{zone}/viz_meshes", 3, str(mesh_prim.GetName()))
            elif mesh_type == "HEXA_8":
                idx_quad = generate_hull(idx_elem, mesh_type)
                hull_mesh_to_stage(vertices.numpy(), idx_quad.numpy(), idx_offset_maybe, stage, f"/World/{zone}/viz_meshes", 4, str(mesh_prim.GetName()))
            elif mesh_type == "NGON_n":
               hull_mesh_to_stage(vertices.numpy(), idx_elem.numpy(), idx_offset_maybe.numpy(), stage, f"/World/{zone}/viz_meshes", 3, str(mesh_prim.GetName()))
            else:
                print(f"NOTE: Can't visualize mesh '{str(mesh_prim.GetName())}' of type: {mesh_type}")

def run_in_new_loop(coro):
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    new_loop.run_until_complete(coro)
    new_loop.close()

def start_new_thread(coro):
    thread = threading.Thread(target=run_in_new_loop, args=(coro,))
    thread.start()
    return thread


@carb.profiler.profile
def apply_transform(point, transform):
    # Ensure a Vec3d
    point3d = Gf.Vec3d(point[0], point[1], point[2])
    # Apply the transformation
    transformed_point = transform.Transform(point3d)

    # Convert back to 3D coordinates
    return (transformed_point[0], transformed_point[1], transformed_point[2])


@carb.profiler.profile
def extract_scale(matrix):
    # Extract the upper-left 3x3 submatrix
    m3 = Gf.Matrix3d(matrix.ExtractRotationMatrix())

    # Calculate the length of each column vector
    scale_x = Gf.Vec3d(m3[0][0], m3[1][0], m3[2][0]).GetLength()
    scale_y = Gf.Vec3d(m3[0][1], m3[1][1], m3[2][1]).GetLength()
    scale_z = Gf.Vec3d(m3[0][2], m3[1][2], m3[2][2]).GetLength()

    return Gf.Vec3d(scale_x, scale_y, scale_z)


@carb.profiler.profile
def generatePointsInSphere(spherePrim, pointCt, starting_position=(0.,0.,0.))-> np.array:

    if spherePrim.IsA(UsdGeom.Sphere):
        # Get the world transform
        xform_cache: UsdGeom.XformCache = UsdGeom.XformCache()
        # world_transform: Gf.Matrix4d = xform_cache.GetLocalToWorldTransform(spherePrim)
        (world_transform, _) = xform_cache.GetLocalTransformation(spherePrim)
        radius_attr: Usd.Attribute = spherePrim.GetAttribute("radius")
        # only take x-scale
        scale = extract_scale(world_transform)[0]

        if radius_attr:
            radius: float = radius_attr.Get() * scale
        else:
            radius = 1.0 * scale

        #print(f"radius={radius}, scale={scale}")

        position = apply_transform(starting_position, world_transform)

        starting_points = []
        np.random.seed(42)
        for _ in range(pointCt):
            # Generate random points in spherical coordinates
            r = radius * (np.random.rand() ** (1/3))  # to ensure uniform distribution in 3D
            theta = np.random.rand() * 2 * np.pi
            phi = np.random.rand() * np.pi
            # Convert spherical coordinates to Cartesian coordinates
            x = position[0] + r * np.sin(phi) * np.cos(theta)
            y = position[1] + r * np.sin(phi) * np.sin(theta)
            z = position[2] + r * np.cos(phi)
            starting_points.append((x, y, z))
        return np.array(starting_points)
    return None

def generatePointsOnPlane(planePrim, gridX, gridY)-> np.array:
    xformable = UsdGeom.Xformable(planePrim)
    local_to_world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

    (min_xyz, max_xyz) = UsdGeom.Boundable(planePrim).GetExtentAttr().Get()

    x = np.linspace(min_xyz[0], max_xyz[0], gridX)
    y = np.linspace(min_xyz[1], max_xyz[1], gridY)
    xx,  yy = np.meshgrid(x,  y)
    starting_points = []

    for i in range(gridY):
        for j in range(gridX):
            Txy = local_to_world_transform.Transform(Gf.Vec3d(xx[i,  j],  yy[i,  j],  0.0))
            starting_points.append((Txy[0],  Txy[1],  Txy[2]))
    return np.array(starting_points)

@carb.profiler.profile
def streamlines_fn(self):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # If no event loop is running, create a new one
        loop = asyncio.new_event_loop()
        print("new loop needed")

    try:
        self._updatingStreamLines = True
        velocity_or_pressure = self.velocity_pressure_combo.model.get_item_value_model().get_value_as_int()
        should_upload_vdb_to_gpu = self._should_upload_vdb_to_gpu

        asyncio.run(streamlines_fn_async(
            gridX=self._gridX,
            gridY=self._gridY,
            scalar_type=velocity_or_pressure,
            crvDTMAX=self._crvDTMAX,
            crvSegments=self._crvSegments,
            crvWidth=self._crvWidth,
            should_upload_vdb_to_gpu=should_upload_vdb_to_gpu,
            ))

        self._should_upload_vdb_to_gpu = False

    finally:
        self._updatingStreamLines = False

# Cache the VDB gpu data in a global
vdb_gpu = None

@carb.profiler.profile
def update_streamlines_fn(vdb, gridX, gridY, scalar_type=1, crvDT0=0.2, crvDTMAX=1.0, crvSegments=75, crvWidth=1.01, should_upload_vdb_to_gpu: bool = True):
    ptct = gridX*gridY
    stage = omni.usd.get_context().get_stage()
    ssPrim =  stage.GetPrimAtPath("/World/Streamlines/StreamStart_sphere")

    starting_points_np = generatePointsInSphere(ssPrim, ptct)

    starting_points_wp = wp.array(starting_points_np, dtype=wp.vec3f)

    num_steps = crvSegments

    ptr = ctypes.pythonapi.PyCapsule_GetPointer(vdb.data, None)
    ptr_int = ctypes.cast(ptr, ctypes.c_void_p).value
    print(f"vdb=(ts:{vdb.timestamp},id:{vdb.id},size={vdb.size_bytes},data={ptr_int})")

    settings = carb.settings.get_settings()
    vec4_enabled = settings.get("exts/omni.flowusd/voxelize_velocity_vec4")
    vdb_vec3 = not vec4_enabled

    # Cached vdb gpu data stored as a module global
    # Re-upload if requested or none
    global vdb_gpu
    if vdb_gpu is None or should_upload_vdb_to_gpu:
        vdb_gpu = upload_vdb_cpu_to_gpu(vdb)

    (streamlines_paths, streamlines_scalars) = advect_vector_field(
        None, None, "VDB", None, starting_points_wp,
        vdb, vdb_gpu, dt=crvDT0, num_steps=num_steps,
        streamlines_scalar_type=scalar_type,
        vdb_vec3=vdb_vec3, dt_MAX=crvDTMAX)

    make_basis_curve(
        stage,
        streamlines_paths.numpy(),
        streamlines_scalars.numpy(),
        num_steps * np.ones(ptct),
        ptct,
        width=crvWidth,
        path=f"/World/Streamlines/StreamLines",
        pressure=scalar_type==1
    )
    return 1

@carb.profiler.profile
async def streamlines_fn_async(gridX, gridY, scalar_type=1, crvDTMAX=0.5, crvSegments=75, crvWidth=1.01, should_upload_vdb_to_gpu: bool = True):
    icgns = ocgns.get_interface()
    vdb = icgns.get_latest_vdb_data()
    update_streamlines_fn(vdb, gridX, gridY, scalar_type, 0.2, crvDTMAX, crvSegments, crvWidth, should_upload_vdb_to_gpu)
    icgns.release_vdb_data(vdb.timestamp)


def getZoneGroupPaths(stage) -> dict:
    zoneGroupPathDict = {}
    prim = stage.GetPrimAtPath("/World")
    if prim:
        for child in prim.GetAllChildren():
            zoneAttr = child.GetAttribute("ZoneAssetGroup")
            if zoneAttr:
                if child.GetPath() not in zoneGroupPathDict:
                    zoneGroupPathDict[child.GetPath()] = child.GetName()
    return zoneGroupPathDict

def getFieldGroupPath(stage, parentPrimPath) -> dict:
    fieldPathsDict = {}
    prim = stage.GetPrimAtPath(parentPrimPath)
    if prim:
        for child in prim.GetAllChildren():
            fieldAttr = child.GetAttribute("FieldAssetGroup")
            if fieldAttr:
                for fieldChild in child.GetAllChildren():
                    if fieldChild.GetPath() not in fieldPathsDict:
                        fieldPathsDict[fieldChild.GetName()] = fieldChild.GetPath()
    return fieldPathsDict



def create_bbox_visualization(stage: Usd.Stage, bbox: Gf.Range3d, path: str):
    prim = stage.GetPrimAtPath(path)
    if prim:
        stage.RemovePrim(path)
    bbox_prim = UsdGeom.Cube.Define(stage, path)

    # Set the size of the cube
    size = bbox.GetSize()
    bbox_prim.GetSizeAttr().Set(max(size[0], size[1], size[2]))

    # Set the position of the cube
    center = bbox.GetMidpoint()
    xform = bbox_prim.AddXformOp(UsdGeom.XformOp.TypeTranslate)
    xform.Set(center)

    # Set the scale of the cube
    scale_op = bbox_prim.AddXformOp(UsdGeom.XformOp.TypeScale)
    scale_op.Set(Gf.Vec3d(size[0], size[1], size[2]))

def create_range3d(xmin, ymin, zmin, xmax, ymax, zmax):
    min_point = Gf.Vec3d(float(xmin), float(ymin), float(zmin))
    max_point = Gf.Vec3d(float(xmax), float(ymax), float(zmax))
    return Gf.Range3d(min_point, max_point)

# Any class derived from `omni.ext.IExt` in the top level module (defined in `python.modules` of `extension.toml`) will
# be instantiated when the extension gets enabled, and `on_startup(ext_id)` will be called.
# Later when the extension gets disabled on_shutdown() is called.
class MyExtension(omni.ext.IExt):
    # ext_id is the current extension id. It can be used with the extension manager to query additional information,
    # like where this extension is located on the filesystem.

    def clean(self):
        # Unsubscribe from stage events
        self._stage_event_sub = None
        # Clear objects changed listener
        self._toggle_objects_changed_listener(False)

    # Subscribed event - fired every time something happens in the stage
    def _on_stage_event(self, evt):
        if evt.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._update_selection()
        if evt.type == int(omni.usd.StageEventType.OPENED):
            self._update_selection()

    # Fired when the selection changes in the stage
    def _update_selection(self):
        # Update the selected prim paths
        self._selected_paths = omni.usd.get_context().get_selection().get_selected_prim_paths()

    # Toggles the _on_objects_changed listener on/off
    def _toggle_objects_changed_listener(self, toggle: bool):
        if toggle:
            if self._objects_changed_listener is None:
                self._objects_changed_listener = Tf.Notice.Register(
                    Usd.Notice.ObjectsChanged, self._on_objects_changed, omni.usd.get_context().get_stage()
                )
        else:
            if self._objects_changed_listener is not None:
                self._objects_changed_listener.Revoke()
                self._objects_changed_listener = None

    @carb.profiler.profile
    def _on_objects_changed(self, notice, sender):
        changed_paths_prims = []
        # Get prim paths of changed prims
        primsToTrack = ["/World/Streamlines/StreamStart_sphere",
                        "/World/Flow_CFD/CFDResults/flowOffscreen/colormap",
                        "/World/Flow_CFD/CFDResults/flowRender/rayMarch",
                        "/World/Flow_CFD/CFDResults/flowOffscreen_pressure/colormap",
                        "/World/Flow_CFD/CFDResults/flowRender_pressure/rayMarch"]
        try:
            changed_paths_prims = [Sdf.Path.GetAbsoluteRootOrPrimPath(i) for i in notice.GetChangedInfoOnlyPaths()]
            #  print(f"Changed prim paths: {changed_paths_prims}")
            #if changed_paths_prims[0] == "/World/Streamlines/StreamStart_sphere" or changed_paths_prims[0] == "/World/Flow_CFD/CFDResults/flowOffscreen/colormap":
            if changed_paths_prims[0] in primsToTrack:
                if not self._updatingStreamLines:
                    self._updatingStreamLines = True
                    streamlines_fn(self)
        except Exception as e:
            print(e)

    def updateStreamlineProps(self,  prop, val):
        #print(f"prop: {prop} , val: {val}")
        setattr(self, prop, val)
        streamlines_fn(self)

    def generateStreamStartPrim(self,ssType, make : bool):
        # Check if an Xform exists, if not create one
        if make:
            streamBasePrim = omni.usd.get_context().get_stage().GetPrimAtPath(self._streamBase)
            if not streamBasePrim:
                xform = UsdGeom.Xform.Define(omni.usd.get_context().get_stage(), self._streamBase)
            print(ssType)
            if ssType == 'sphere':
                # Create a sphere prim
                sphere_path =Sdf.Path( f"{self._streamBase}/StreamStart_sphere")
                sphere_prim: UsdGeom.Sphere = UsdGeom.Sphere.Define(omni.usd.get_context().get_stage() , sphere_path)
                prim: Usd.Prim = sphere_prim.GetPrim()

                # Set the radius attribute
                radius_attr: Usd.Attribute = prim.GetAttribute("radius")
                radius_attr.Set(10.0)
        else:
            print(omni.usd.get_context().get_stage(), make)


    def service_request_clicker(self, restart, from_files=False):

        icgns = ocgns.get_interface()

        # config is applied only after the button has been pressed
        if restart:
            address = self.file_service_address.model.get_value_as_string() if from_files else self.remote_service_address.model.get_value_as_string()
            service_config = ocgns.ServiceConfig(address)
            service_config.from_files = from_files
            service = icgns.init_service(restart, service_config)
            if not service:
                print("service error")

        if restart and not from_files:
            return

        config = ocgns.RequestConfig()
        config.id = self._configFileId if self._configCarId == 0 else self._configCarId
        config.config = self._configSpeed
        config.multip = self._point_count_drag.model.get_value_as_float() if self._point_count_drag else 1.0
        icgns.request_config(config)
        # configs changed, make sure to reupload the VDB data to the GPU
        self._should_upload_vdb_to_gpu = True

    def updateRequestProps(self, prop, val):
        # print(f"prop: {prop} , val: {val}")
        setattr(self, prop, val)
        self.service_request_clicker(False)

    def dump_latest_data(self):
        icgns = ocgns.get_interface()
        data = icgns.get_latest_vdb_data()

        time = data.timestamp

        pos = icgns.get_data(None, time, "coordinates")
        vel = icgns.get_data(None, time, "velocity")
        pres = icgns.get_data(None, time, "pressure")

        settings = carb.settings.get_settings()
        path = settings.get("exts/omni.cgns/file_path_dump")
        np.save(f'{path}/{time}_pos.npy', pos)
        np.save(f'{path}/{time}_vel.npy', vel)
        np.save(f'{path}/{time}_pres.npy', pres)

        icgns.release_data(None, time, "coordinates")
        icgns.release_data(None, time, "velocity")
        icgns.release_data(None, time, "pressure")
        icgns.release_vdb_data(time)

    def on_startup(self, ext_id):
        MyExtension.instance = self
        print("[ov.cgns_ui] Extension startup")
        # self._usd_context = omni.usd.get_context()
        # self._stage = self._usd_context.get_stage()
        # self._selection = omni.usd.get_context().get_selection()
        self._selected_paths = []
        self._objects_changed_listener = None
        self._updatingStreamLines = False
        self._gridX = 5
        self._gridY = 5
        self._crvDTMAX = 5.0
        self._crvSegments = 200
        self._crvWidth = 1.0
        self._streamBase = "/World/Streamlines"
        self._configCarId = 0
        self._configFileId = 0
        self._configSpeed = 30
        self._point_count_drag = None
        self._should_upload_vdb_to_gpu = True
        # Subscribe to stage events
        self._stage_event_sub = omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event
        )
        # Subscribe to stage events
        self._stage_event_sub = omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event
        )
        # Only subscribe to the ObjectsChanged listener when the user has more than one object selected.
        self._toggle_objects_changed_listener(False)

        stage_update_init()

        self.field_names = []

        send_message("Inference complete")      

        try:
            import ov.cgns
        except:
            raise RuntimeError("Couldn't load 'ov.cgns', please enable the CGNS loader extension")

        self._count = 0

        self._window = ui.Window("RTWT UI Explorer", width=350, height=400)
        self._window .deferred_dock_in("Property", ui.DockPolicy.CURRENT_WINDOW_IS_ACTIVE)

        def visualize_streamlines_callback_fn(timestamp):
            velocity_or_pressure = self.velocity_pressure_combo.model.get_item_value_model().get_value_as_int()
            icgns = ocgns.get_interface()
            # getting latest as the timestamp received in callback might be already released
            vdb = icgns.get_latest_vdb_data()
            update_streamlines_fn(vdb, self._gridX, self._gridY, velocity_or_pressure,
                                  0.2, self._crvDTMAX, self._crvSegments, self._crvWidth)
            icgns.release_vdb_data(vdb.timestamp)

        def visualize_data_callback_fn(timestamp):
            icgns = ocgns.get_interface()
            points_orig = icgns.get_data(None, timestamp, "coordinates")
            pressure = icgns.get_data(None, timestamp, "pressure")
            # velocity = icgns.get_data(None, timestamp, "coordinates")

            # m -> cm
            # make a copy otherwise the *= 100 will modify the internal buffers!
            points = np.copy(points_orig)
            points *= 100

            print(f"Got COORDINATES (num={points.size})")
            stage = omni.usd.get_context().get_stage()
            xmin = np.min(points[:,0])
            xmax = np.max(points[:,0])

            ymin = np.min(points[:,1])
            ymax = np.max(points[:,1])

            zmin = np.min(points[:,2])
            zmax = np.max(points[:,2])

            bbox = create_range3d(xmin,ymin,zmin,xmax,ymax,zmax)
            print("bbox=", bbox)
            # create_bbox_visualization(stage, bbox, "/World/points_bbox")

            subset_N = 50000
            subset_rows = np.random.choice(points.shape[0], subset_N)
            subset_points = points[subset_rows]

            points_to_usd(stage, subset_points, scalar_field=pressure[subset_rows].reshape(subset_N), point_size=1.0, path="/World/Streamlines/pointcloud")
            icgns.release_data(timestamp=timestamp, field_name="coordinates")
            icgns.release_data(timestamp=timestamp, field_name="pressure")

            # update_streamlines_fn(vdb, self._gridX, self._gridY,
            #                       self._crvResolution, self._crvSegments, self._crvWidth)


        def updateCallbacks(callback_str: str, callback_fn, enable: bool, vdb_callback: bool):
            icgns = ocgns.get_interface()
            if vdb_callback:
                stage_update_unregister_vdb_callback(callback_str)
            else:
                stage_update_unregister_data_callback(callback_str)
            if enable:
                if vdb_callback:
                    stage_update_register_vdb_callback(callback_str, callback_fn)
                else:
                    stage_update_register_data_callback(callback_str, callback_fn)

        with self._window.frame:
            with ui.VStack(height=0):
                with ui.HStack():
                    # This one will restart the already running service
                    ui.Button("Start File Service", width=80, clicked_fn=lambda restart=True, files=True: self.service_request_clicker(restart, files))
                    self.file_service_address = ui.StringField(width=100, height=20)
                    self.file_service_address.model.set_value("localhost")
                    ui.Spacer(width=15)
                    ui.Label("File Id:", width=45)
                    config_file_id_slider = ui.IntSlider(height=25, min=0, max=9, name="_configFileId")
                    config_file_id_slider.model.set_value(self._configFileId)
                    config_file_id_slider.model.add_value_changed_fn(
                        lambda val, b=self, files=True,
                        n=config_file_id_slider.name: self.updateRequestProps(n, val.get_value_as_int())
                    )

                with ui.HStack():
                    ui.Button("Start Service", width=80, clicked_fn=lambda restart=True, files=False: self.service_request_clicker(restart, files))

                    settings = carb.settings.get_settings()
                    address = settings.get("exts/omni.cgns/zmq_ip_address")

                    self.remote_service_address = ui.StringField(width=100, height=20)
                    self.remote_service_address.model.set_value(address)

                with ui.HStack():
                    ui.Label("Car Id:", width=45)
                    ui.Spacer(width=5)
                    config_file_id_slider = ui.IntSlider(height=25, min=500, max=515, name="_configCarId")
                    config_file_id_slider.model.set_value(self._configCarId)
                    config_file_id_slider.model.add_value_changed_fn(
                        lambda val, b=self,
                        n=config_file_id_slider.name: self.updateRequestProps(n, val.get_value_as_int())
                    )
                with ui.HStack():
                    ui.Label("Stream Velocity:", width=100)
                    config_speed_slider = ui.IntSlider(height=25, min=30, max=100, name="_configSpeed")
                    config_speed_slider.model.set_value(self._configSpeed)
                    config_speed_slider.model.add_value_changed_fn(
                        lambda val, b=self,
                        n=config_speed_slider.name: self.updateRequestProps(n, val.get_value_as_int())
                    )

                with ui.HStack(height=25):
                    ui.Label("Point count multiplier", height=25)
                    ui.Spacer(width=5)
                    self._point_count_drag = ui.FloatDrag(min=0.01, max=2)
                    ui.Spacer(width=5)

                    def reset_mult():
                        self._point_count_drag.model.set_value(1.0)

                    ui.Button("Reset", clicked_fn=reset_mult, width=60)
                    reset_mult()

                    ui.Button("Dump Data", tooltip="set 'exts/omni.cgns/file_path_dump' for the folder path", clicked_fn=self.dump_latest_data, width=60)

                with ui.HStack(height=25):
                    updatecb = ui.CheckBox(width=25)
                    updatecb.model.add_value_changed_fn(lambda m: updateCallbacks("viz_streamlines",
                                                                                  visualize_streamlines_callback_fn,
                                                                                  m.get_value_as_bool(), True))
                    updatecb.model.set_value(True)
                    ui.Label("Visualize streamlines", height=25)
                    ui.Spacer(width=5)
                    updatecb = ui.CheckBox(width=25)
                    updatecb.model.add_value_changed_fn(lambda m: updateCallbacks("viz_points",
                                                                                  visualize_data_callback_fn,
                                                                                  m.get_value_as_bool(), False))
                    updatecb.model.set_value(False)
                    ui.Label("Visualize points", height=25)

                with ui.CollapsableFrame(title="Stream Lines", height=100):
                    with ui.VStack():                      
                        with ui.VStack():
                            ui.Label("Generate Streamline Controllers")
                            with ui.HStack():
                                ui.Button("Sphere", clicked_fn=lambda typ = 'sphere', make = True : self.generateStreamStartPrim(typ, make), width=80)

                        ui.Separator(height=10)
                        with ui.HStack():
                            ui.Label("Streamline coloring from: ")
                        self.velocity_pressure_combo = ui.ComboBox()
                        self.velocity_pressure_combo.model.append_child_item(None, ui.SimpleStringModel("|Velocity|"))
                        self.velocity_pressure_combo.model.append_child_item(None, ui.SimpleStringModel("Pressure"))
                       
                        ui.Separator(height=10)
                        with ui.HStack(height=25):
                            ui.Label("X Count", width=100)
                            xc = ui.IntSlider(height=25, min=2, max=100, name="_gridX")
                            xc.model.set_value(self._gridX)
                            xc.model.add_value_changed_fn(
                                lambda val, b=self, n=xc.name: self.updateStreamlineProps(n,  val.get_value_as_int())
                            )
                        with ui.HStack(height=25):
                            ui.Label("Y Count", width=100)
                            yc = ui.IntSlider(height=25, min=2, max=100, name="_gridY")
                            yc.model.set_value(self._gridY)
                            yc.model.add_value_changed_fn(
                                lambda val, b=self, n=yc.name: self.updateStreamlineProps(n,  val.get_value_as_int())
                            )
                        with ui.HStack(height=25):
                            ui.Label("Curve Segments", width=100)
                            cs = ui.IntSlider(height=25, min=100, max=1000, name="_crvSegments")
                            cs.model.set_value(self._crvSegments)
                            cs.model.add_value_changed_fn(
                                lambda val, b=self, n=cs.name: self.updateStreamlineProps(n,  val.get_value_as_int())
                            )
                        with ui.HStack(height=25):
                            ui.Label("Segments Max Length", width=100)
                            csl = ui.FloatSlider(height=25, min=0.1, max=10.00, name="_crvDTMAX")
                            csl.model.set_value(self._crvDTMAX)
                            csl.model.add_value_changed_fn(
                                lambda val, b=self, n=csl.name: self.updateStreamlineProps(n,  val.get_value_as_float())
                            )
                        with ui.HStack(height=25):
                            ui.Label("Curve Radius", width=100)
                            cr = ui.FloatSlider(height=25, min=0.0001, max=1.00, name="_crvWidth")
                            cr.model.set_value(0.01)
                            cr.model.add_value_changed_fn(
                                lambda val, b=self, n=cr.name: self.updateStreamlineProps(n, val.get_value_as_float())
                            )
                        ui.Separator(height=10)
                        with ui.HStack(height=25):
                            livecb = ui.CheckBox(width=25)
                            livecb.model.add_value_changed_fn(
                                lambda a: self._toggle_objects_changed_listener(a.get_value_as_bool())
                            )
                            ui.Label("Live", height=25)


    def on_shutdown(self):
        print("[ov.cgns_ui] Extension shutdown")
        icgns = ocgns.get_interface()
        stage_update_unregister_vdb_callback("viz_streamlines")
        stage_update_unregister_data_callback("viz_points")
        stage_update_release()
