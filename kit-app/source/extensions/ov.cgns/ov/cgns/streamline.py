import sys

import numpy as np
import pyvtk
import warp as wp
import cupy as cp
import ctypes
import carb.profiler
from cuda import cuda
import os

from pxr import Gf, Sdf, Tf, Usd, UsdGeom, Vt

# Gives a transform that yields a matrix that transforms a point into the reference coordinate system
# in other words, converts the points into barycentric coordinates (3D)
@wp.func
def Mref_tet(point: wp.vec3f, vertices: wp.array(dtype=wp.vec3f), idx_tet: wp.array(dtype=wp.int32), idx: wp.int32):

    a = vertices[idx_tet[4 * idx + 0]]
    b = vertices[idx_tet[4 * idx + 1]]
    c = vertices[idx_tet[4 * idx + 2]]
    d = vertices[idx_tet[4 * idx + 3]]

    v1 = b - a
    v2 = c - a
    v3 = d - a

    M = wp.inverse(wp.mat33(v1, v2, v3))

    return M


# matrix to convert input point into reference HEX coordinates
@wp.func
def Mref_hex(point: wp.vec3f, vertices: wp.array(dtype=wp.vec3f), idx_hex: wp.array(dtype=wp.int32), idx: wp.int32):

    a = vertices[idx_hex[8 * idx + 3]]
    b = vertices[idx_hex[8 * idx + 0]]
    c = vertices[idx_hex[8 * idx + 2]]
    d = vertices[idx_hex[8 * idx + 7]]

    v1 = b - a
    v2 = c - a
    v3 = d - a

    M = wp.inverse(wp.mat33(v1, v2, v3))

    return M



@wp.func
def point_in_tetrahedra(
    point: wp.vec3f, vertices: wp.array(dtype=wp.vec3f), idx_tet: wp.array(dtype=wp.int32), idx: wp.int32
):

    a = vertices[idx_tet[4 * idx + 0]]
    b = vertices[idx_tet[4 * idx + 1]]
    c = vertices[idx_tet[4 * idx + 2]]
    d = vertices[idx_tet[4 * idx + 3]]

    v1 = b - a
    v2 = c - a
    v3 = d - a

    M123 = wp.mat33(v1, v2, v3)
    M = wp.inverse(M123)

    pt = M @ (point - a)

    cond1 = pt[0] >= 0 and pt[1] >= 0 and pt[2] >= 0
    cond2 = pt[0] <= 1 and pt[1] <= 1 and pt[2] <= 1
    cond3 = (pt[0] + pt[1] + pt[2]) <= 1.0

    # print(f"({pt[0]},{pt[1]},{pt[2]})")
    # print("pt")
    # print(pt)
    return cond1 and cond2 and cond3


@wp.func
def point_in_hexahedra(
    point: wp.vec3f, vertices: wp.array(dtype=wp.vec3f), idx_hex: wp.array(dtype=wp.int32), idx: wp.int32
):

    a = vertices[idx_hex[8 * idx + 3]]
    b = vertices[idx_hex[8 * idx + 0]]
    c = vertices[idx_hex[8 * idx + 2]]
    d = vertices[idx_hex[8 * idx + 7]]

    # wp.printf("[%d]: (%f,%f,%f)--(%f,%f,%f)--(%f,%f,%f)--(%f,%f,%f)\n",
    #           idx,
    #           a[0],a[1],a[2],
    #           b[0],b[1],b[2],
    #           c[0],c[1],c[2],
    #           d[0],d[1],d[2]
    #           )

    v1 = b - a
    v2 = c - a
    v3 = d - a

    M123 = wp.mat33(v1, v2, v3)
    M = wp.inverse(M123)

    pt = M @ (point - a)

    cond1 = pt[0] >= 0 and pt[1] >= 0 and pt[2] >= 0
    cond2 = pt[0] <= 1 and pt[1] <= 1 and pt[2] <= 1
    cond3 = (pt[0] + pt[1] + pt[2]) <= 3.0

    # print(f"({pt[0]},{pt[1]},{pt[2]})")
    # print("pt")
    # print(pt)
    return cond1 and cond2 and cond3



@wp.func
def interpolate_field(
    point: wp.vec3f,
    vertices: wp.array(dtype=wp.vec3f),
    idx_tet: wp.array(dtype=wp.int32),
    idx: wp.int32,
    field: wp.array(dtype=wp.float32),
):

    a = vertices[idx_tet[4 * idx + 0]]
    b = vertices[idx_tet[4 * idx + 1]]
    c = vertices[idx_tet[4 * idx + 2]]
    d = vertices[idx_tet[4 * idx + 3]]

    M = Mref_tet(point, vertices, idx_tet, idx)

    pref = M @ (point - a)

    f0 = field[idx_tet[4 * idx + 0]]
    f1 = field[idx_tet[4 * idx + 1]]
    f2 = field[idx_tet[4 * idx + 2]]
    f3 = field[idx_tet[4 * idx + 3]]

    x = pref[0]
    y = pref[1]
    z = pref[2]
    # solution to vandermonde matrix (https://en.wikipedia.org/wiki/Vandermonde_matrix)
    fp = f0 + (f1 - f0) * x + (f2 - f0) * y + (f3 - f0) * z

    return fp


@wp.func
def interpolate_vector_field_tet(
    point: wp.vec3f,
    vertices: wp.array(dtype=wp.vec3f),
    idx_tet: wp.array(dtype=wp.int32),
    idx: wp.int32,
    vector_field: wp.array(dtype=wp.vec3f),
):

    a = vertices[idx_tet[4 * idx + 0]]
    # b = vertices[idx_tet[4 * idx + 1]]
    # c = vertices[idx_tet[4 * idx + 2]]
    # d = vertices[idx_tet[4 * idx + 3]]

    M = Mref_tet(point, vertices, idx_tet, idx)

    pref = M @ (point - a)

    f0 = vector_field[idx_tet[4 * idx + 0]]
    f1 = vector_field[idx_tet[4 * idx + 1]]
    f2 = vector_field[idx_tet[4 * idx + 2]]
    f3 = vector_field[idx_tet[4 * idx + 3]]

    x = pref[0]
    y = pref[1]
    z = pref[2]
    # solution to vandermonde matrix (https://en.wikipedia.org/wiki/Vandermonde_matrix)
    fp = f0 + (f1 - f0) * x + (f2 - f0) * y + (f3 - f0) * z

    return fp


@wp.func
def interpolate_vector_field_hex(
    point: wp.vec3f,
    vertices: wp.array(dtype=wp.vec3f),
    idx_hex: wp.array(dtype=wp.int32),
    idx: wp.int32,
    vector_field: wp.array(dtype=wp.vec3f),
):

    a = vertices[idx_hex[8 * idx + 3]]

    M = Mref_hex(point, vertices, idx_hex, idx)

    pref = M @ (point - a)

    f0 = vector_field[idx_hex[8 * idx + 3]]
    f1 = vector_field[idx_hex[8 * idx + 2]]
    f2 = vector_field[idx_hex[8 * idx + 1]]
    f3 = vector_field[idx_hex[8 * idx + 0]]
    f4 = vector_field[idx_hex[8 * idx + 7]]
    f5 = vector_field[idx_hex[8 * idx + 4]]
    f6 = vector_field[idx_hex[8 * idx + 5]]
    f7 = vector_field[idx_hex[8 * idx + 6]]

    x = pref[0]
    y = pref[1]
    z = pref[2]

    # see compute_interpolation_hex() below for how to get the correct coefficients
    # solution to vandermonde matrix (https://en.wikipedia.org/wiki/Vandermonde_matrix)
    # computed using sympy
    fp = f0 + x*y*z*(-f0 + f1 - f2 + f3 + f4 - f5 + f6 - f7) + x*y*(f0 - f1 + f2 - f3)\
        + x*z*(f0 - f3 - f4 + f5) + x*(-f0 + f3) + y*z*(f0 - f1 - f4 + f7)\
        + y*(-f0 + f1) + z*(-f0 + f4)

    return fp


def pointsToVolume(points: wp.array(dtype=wp.vec3f), radius_factor=2.0):

    print("hello")
    xyz_cp = cp.array(points)
    min_xyz = cp.min(xyz_cp[:,0:3])
    max_xyz = cp.max(xyz_cp[:,0:3])

    radius_avg = float(max_xyz - min_xyz)/pow(points.shape[0],1/3)*radius_factor
    print(f"Radius=({float(max_xyz - min_xyz)}/{points.shape[0]})=", radius_avg)

    vol = wp.Volume.allocate_by_voxels(points, radius_avg)
    return vol


@wp.kernel
def rasterizeVelocityToVoxelsKernel(volume: wp.uint64,
                                    points: wp.array(dtype=wp.vec3f),
                                    velocity_field_points: wp.array(dtype=wp.vec3f),
                                    velocity_field_voxels: wp.array(dtype=wp.vec3f),
                                    num_points_in_voxel: wp.array(dtype=wp.float32)):

    tid = wp.tid()
    ijk_f = wp.volume_world_to_index(volume, points[tid])
    idx = wp.volume_lookup_index(volume,
                                 int(wp.round(ijk_f[0])),
                                 int(wp.round(ijk_f[1])),
                                 int(wp.round(ijk_f[2])))
    if idx < 0:
        wp.printf("WARNING: Voxel index lookup (%f,%f,%f) failed\n",
                  points[tid][0],
                  points[tid][1],
                  points[tid][2]
                  )
        return
    wp.atomic_add(velocity_field_voxels, idx, velocity_field_points[tid])
    wp.atomic_add(num_points_in_voxel, idx, 1.0)
    # wp.printf("[%d](%f,%f,%f)->(%d,%d,%d)[idx=%d] field=(%f,%f,%f)\n",
    #           tid,
    #           points[tid][0],
    #           points[tid][1],
    #           points[tid][2],
    #           int(wp.round(ijk_f[0])),
    #           int(wp.round(ijk_f[1])),
    #           int(wp.round(ijk_f[2])),
    #           idx,
    #           velocity_field_voxels[idx][0],
    #           velocity_field_voxels[idx][1],
    #           velocity_field_voxels[idx][2])

@wp.kernel
def finalizeAverageVoxelVelocityKernel(velocity_field_voxels: wp.array(dtype=wp.vec3f),
                                       num_points_in_voxel: wp.array(dtype=wp.float32)):
    tid = wp.tid()
    if num_points_in_voxel[tid] > 0:
        velocity_field_voxels[tid] = velocity_field_voxels[tid] / num_points_in_voxel[tid]

def rasterizeVelocityToVoxels(points,
                              velocity_field,
                              volume):
    velocity_field_voxels = wp.zeros(volume.get_voxel_count(), dtype=wp.vec3f)
    num_points_in_voxel = wp.zeros(volume.get_voxel_count(), dtype=wp.float32)
    wp.launch(rasterizeVelocityToVoxelsKernel, velocity_field.shape[0],
              inputs=[volume.id, points, velocity_field, velocity_field_voxels, num_points_in_voxel])
    wp.synchronize()
    num_points_in_voxel_cp = cp.array(num_points_in_voxel)
    min_pts = cp.min(num_points_in_voxel_cp)
    max_pts = cp.max(num_points_in_voxel_cp)
    print(f"Max/Min pts per voxel: {(float(max_pts), float(min_pts))}")
    wp.launch(finalizeAverageVoxelVelocityKernel, num_points_in_voxel.shape[0],
              inputs=[velocity_field_voxels, num_points_in_voxel])
    return velocity_field_voxels


@wp.func
def sampleVolumeInternalField(volume: wp.uint64,
                              point: wp.vec3f):

    point_uvw = wp.volume_world_to_index(volume, point)
    return wp.volume_sample(volume, point_uvw, wp.Volume.LINEAR, dtype=wp.vec3f)
    # return wp.volume_sample_f(volume, point_uvw, wp.Volume.LINEAR)

@wp.func
def sampleVolumeInternalFieldVec4(volume: wp.uint64,
                              point: wp.vec3f):

    point_uvw = wp.volume_world_to_index(volume, point)
    return wp.volume_sample(volume, point_uvw, wp.Volume.LINEAR, dtype=wp.vec4f)
    # return wp.volume_sample_f(volume, point_uvw, wp.Volume.LINEAR)




@wp.func
def sampleVolume(volume0: wp.uint64,
                 volume1: wp.uint64,
                 volume2: wp.uint64,
                 volume3: wp.uint64,
                 point: wp.vec3f,
                 velocity_field0: wp.array(dtype=wp.vec3f),
                 velocity_field1: wp.array(dtype=wp.vec3f),
                 velocity_field2: wp.array(dtype=wp.vec3f),
                 velocity_field3: wp.array(dtype=wp.vec3f),
                 verbose_lookup_check: wp.bool):

    q = wp.volume_world_to_index(volume0, point)
    idx = wp.volume_lookup_index(volume0,
                                 int(wp.round(q[0])),
                                 int(wp.round(q[1])),
                                 int(wp.round(q[2])))
    if idx >= 0:
        return wp.volume_sample_index(volume0, q, wp.Volume.LINEAR, velocity_field0, wp.vec3f(0.0,0.0,0.0))

    q = wp.volume_world_to_index(volume1, point)
    idx = wp.volume_lookup_index(volume1,
                                 int(wp.round(q[0])),
                                 int(wp.round(q[1])),
                                 int(wp.round(q[2])))
    if idx >= 0:
        return wp.volume_sample_index(volume1, q, wp.Volume.LINEAR, velocity_field1, wp.vec3f(0.0,0.0,0.0))

    q = wp.volume_world_to_index(volume2, point)
    idx = wp.volume_lookup_index(volume2,
                                 int(wp.round(q[0])),
                                 int(wp.round(q[1])),
                                 int(wp.round(q[2])))
    if idx >= 0:
        return wp.volume_sample_index(volume2, q, wp.Volume.LINEAR, velocity_field2, wp.vec3f(0.0,0.0,0.0))

    q = wp.volume_world_to_index(volume3, point)
    idx = wp.volume_lookup_index(volume3,
                                 int(wp.round(q[0])),
                                 int(wp.round(q[1])),
                                 int(wp.round(q[2])))
    if idx >= 0:
        return wp.volume_sample_index(volume3, q, wp.Volume.LINEAR, velocity_field3, wp.vec3f(0.0,0.0,0.0))

    if verbose_lookup_check and idx < 0:
        wp.printf("WARNING: Voxel index lookup on coarsest volume (%f,%f,%f) failed, consider increasing voxel radius!\n",
                  point[0],
                  point[1],
                  point[2]
                  )

    return wp.vec3f(0.0,0.0,0.0)


@wp.kernel
def testSampleVolumeKernel(volume: wp.uint64,
                           bvh: wp.uint64,
                           points: wp.array(dtype=wp.vec3f),
                           vertices: wp.array(dtype=wp.vec3f),
                           idx_elem: wp.array(dtype=wp.int32),
                           velocity_field_points: wp.array(dtype=wp.vec3f),
                           velocity_field_voxels: wp.array(dtype=wp.vec3f)):

    point = points[wp.tid()]
    vs = sampleVolume(volume, volume, volume, volume, point,
                      velocity_field_voxels,
                      velocity_field_voxels,
                      velocity_field_voxels,
                      velocity_field_voxels,
                      False)
    eps = wp.vec3f(1e-8, 1e-8, 1e-8)
    lower_b = point - eps
    upper_b = point + eps
    query = wp.bvh_query_aabb(bvh, lower_b, upper_b)
    candidate_idx = wp.int32(-1)
    while wp.bvh_query_next(query, candidate_idx):
        if point_in_hexahedra(point, vertices, idx_elem, candidate_idx):
            found_idx = candidate_idx
            vi = interpolate_vector_field_hex(point, vertices, idx_elem, found_idx, velocity_field_points)
            wp.printf("interpolate p(%f,%f,%f)->hex(%f,%f,%f) vs vox(%f,%f,%f)\n",
                      point[0],point[1],point[2],
                      vi[0],vi[1],vi[2],
                      vs[0],vs[1],vs[2]
                      )

def testSampleVolume():
    vertices_hexes, idx_hex, field_hex, initial_points_hex = get_hex_data()
    more_points = wp.array([
        # wp.vec3f(0.001,0.5,0.5),
        # wp.vec3f(1.25,0.25,0.25),
        # wp.vec3f(1.25,0.75,0.25),
        # wp.vec3f(1.25,0.25,0.75),
        # wp.vec3f(1.25,0.75,0.75),
        wp.vec3f(1.000000,0.323522,0.323522)
    ], dtype=wp.vec3f)
    points_dense, field_dense = gen_point_cloud_hex(10)
    bvh_hex = build_hex_bvh(vertices_hexes, idx_hex)
    volume = pointsToVolume(points_dense)
    vector_field_voxels = rasterizeVelocityToVoxels(points_dense, field_dense, volume)
    wp.launch(testSampleVolumeKernel,
              more_points.shape[0], inputs=[volume.id, bvh_hex.id,
                                            more_points,
                                            vertices_hexes, idx_hex,
                                            field_hex,
                                            vector_field_voxels])

@wp.func
def norm3f(v: wp.vec3f):
    return wp.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])


@wp.func
def sampleVDB(volume0: wp.uint64, p: wp.vec3f, vdb_vec3: wp.int32, streamlines_scalar_type: wp.int32):
    # save |velocity| as scalar
    if streamlines_scalar_type == 0:
        if vdb_vec3 == 1:
            vs = sampleVolumeInternalField(volume0, p)
            return (vs, norm3f(vs))
        else:
            vs4 = sampleVolumeInternalFieldVec4(volume0, p)
            vs = wp.vec3f(vs4[0], vs4[1], vs4[2])
            return (vs, norm3f(vs))
    # save pressure as scalar
    else:
        if vdb_vec3 == 1:
            vs = sampleVolumeInternalField(volume0, p)
            norm_vs = norm3f(vs)
            wp.printf("[WARNING] VDB doesnt have pressure field (vec3 only), saving |velocity|=%f\n", norm_vs)
            return (vs, norm_vs)
        else:
            vs4 = sampleVolumeInternalFieldVec4(volume0, p)
            vs = wp.vec3f(vs4[0], vs4[1], vs4[2])
            return (vs, vs4[3])


@wp.kernel
def advect_vector_field_kernel(volume0: wp.uint64, # bvh or vdb with volume factor (vf) 0.1
                               volume1: wp.uint64, # vf 0.5
                               volume2: wp.uint64, # vf 1.0
                               volume3: wp.uint64, # vf 2.0
                               initial_points: wp.array(dtype=wp.vec3),
                               dt: wp.float32,
                               num_timesteps: wp.int32,
                               vertices: wp.array(dtype=wp.vec3f),
                               idx_elem: wp.array(dtype=wp.int32),
                               pts_per_elem: wp.int32,
                               interpolation_technique: wp.int32,
                               streamlines_scalar_type: wp.int32,
                               vdb_vec3: wp.int32,
                               field0: wp.array(dtype=wp.vec3f),
                               field1: wp.array(dtype=wp.vec3f),
                               field2: wp.array(dtype=wp.vec3f),
                               field3: wp.array(dtype=wp.vec3f),
                               streamlines_paths: wp.array(dtype=wp.vec3f),
                               streamlines_scalars: wp.array(dtype=wp.float32),
                               dt_MIN: wp.float32,
                               dt_MAX: wp.float32,
                               epsilon: wp.float32):

    tid = wp.tid()
    p = initial_points[tid]
    for it in range(num_timesteps):
        # bounding box is just a point +- epsilon
        if interpolation_technique == 0: # FEM
            eps = wp.vec3f(1e-8, 1e-8, 1e-8)
            lower_b = p - eps
            upper_b = p + eps
            query = wp.bvh_query_aabb(volume0, lower_b, upper_b)
            candidate_idx = wp.int32(-1)
            found_idx = wp.int32(-1)
            while wp.bvh_query_next(query, candidate_idx):
                if pts_per_elem == 4:

                    if point_in_tetrahedra(p, vertices, idx_elem, candidate_idx):
                        found_idx = candidate_idx
                        # wp.printf("FOUND tet %d\n", found_idx)
                        vi = interpolate_vector_field_tet(p, vertices, idx_elem, found_idx, field0)
                        # wp.printf("vi:(%f,%f,%f)\n",vi[0],vi[1],vi[2])
                        streamlines_paths[tid * num_timesteps + it] = p
                        streamlines_scalars[tid * num_timesteps + it] = norm3f(vi)

                        # euler time-stepping
                        p = p + dt * vi
                        break
                elif pts_per_elem == 8:
                    if point_in_hexahedra(p, vertices, idx_elem, candidate_idx):
                        found_idx = candidate_idx
                        vi = interpolate_vector_field_hex(p, vertices, idx_elem, found_idx, field0)
                        streamlines_paths[tid * num_timesteps + it] = p
                        streamlines_scalars[tid * num_timesteps + it] = norm3f(vi)

                        # euler time-stepping
                        p = p + dt * vi
            if found_idx == -1:
                # wp.printf("[%d] NOTHING FOUND, solution stalled! (p=(%f,%f,%f))\n", tid, p[0],p[1],p[2])
                streamlines_paths[tid * num_timesteps + it] = p
                streamlines_scalars[tid * num_timesteps + it] = 0.0
                donothing = 0

        elif interpolation_technique == 1: #multi-VDB
            vs = sampleVolume(volume0, volume1, volume2, volume3, p,
                              field0, field1, field2, field3,
                              False)
            streamlines_paths[tid * num_timesteps + it] = p
            streamlines_scalars[tid * num_timesteps + it] = norm3f(vs)
            # euler time-stepping
            p = p + dt * vs

        elif interpolation_technique == 2: #single-VDB

            streamlines_paths[tid * num_timesteps + it] = p
            (vs, scalar_v) = sampleVDB(volume0, p, vdb_vec3, streamlines_scalar_type)
            streamlines_scalars[tid * num_timesteps + it] = scalar_v

            # euler time-stepping
            # p = p + dt * vs

            # # rk4 time-stepping
            # # https://en.wikipedia.org/wiki/Runge%E2%80%93Kutta_methods
            # k1 = vs
            # (k2,_) = sampleVDB(volume0, p + dt/2.0*k1, vdb_vec3, streamlines_scalar_type)
            # (k3,_) = sampleVDB(volume0, p + dt/2.0*k2, vdb_vec3, streamlines_scalar_type)
            # (k4,_) = sampleVDB(volume0, p + dt*k3, vdb_vec3, streamlines_scalar_type)

            # # if it>0:
            # #     time[tid* num_timesteps + it] = time[tid* num_timesteps + it-1] + dt
            # # else:
            # #     time[tid* num_timesteps + it] = 0
            # p = p + dt/6.0 * (k1 + 2.0*k2 + 2.0*k3 + k4)

            # rk45 adaptive time-stepping
            # a2, a3, a4, a5, a6 = 1/4, 3/8, 12/13, 1, 1/2
            # b21 = 1/4
            # b31, b32 = 3/32, 9/32
            # b41, b42, b43 = 1932/2197, -7200/2197, 7296/2197
            # b51, b52, b53, b54 = 439/216, -8, 3680/513, -845/4104
            # b61, b62, b63, b64, b65 = -8/27, 2, -3544/2565, 1859/4104, -11/40
            # c1, c3, c4, c5, c6 = 16/135, 6656/12825, 28561/56430, -9/50, 2/55
            # d1, d3, d4, d5 = 25/216, 1408/2565, 2197/4104, -1/5

            # Define coefficients
            a2, a3, a4, a5, a6 = 0.25, 0.375, 12.0/13.0, 1.0, 0.5
            b21 = 0.25
            b31, b32 = 3.0/32.0, 9.0/32.0
            b41, b42, b43 = 1932.0/2197.0, -7200.0/2197.0, 7296.0/2197.0
            b51, b52, b53, b54 = 439.0/216.0, -8.0, 3680.0/513.0, -845.0/4104.0
            b61, b62, b63, b64, b65 = -8.0/27.0, 2.0, -3544.0/2565.0, 1859.0/4104.0, -11.0/40.0
            c1, c3, c4, c5, c6 = 16.0/135.0, 6656.0/12825.0, 28561.0/56430.0, -9.0/50.0, 2.0/55.0
            d1, d3, d4, d5 = 25.0/216.0, 1408.0/2565.0, 2197.0/4104.0, -1.0/5.0


            # Compute the six function evaluations
            k1, _ = sampleVDB(volume0, p, vdb_vec3, streamlines_scalar_type)
            k2, _ = sampleVDB(volume0, p + dt * (b21 * k1), vdb_vec3, streamlines_scalar_type)
            k3, _ = sampleVDB(volume0, p + dt * (b31 * k1 + b32 * k2), vdb_vec3, streamlines_scalar_type)
            k4, _ = sampleVDB(volume0, p + dt * (b41 * k1 + b42 * k2 + b43 * k3), vdb_vec3, streamlines_scalar_type)
            k5, _ = sampleVDB(volume0, p + dt * (b51 * k1 + b52 * k2 + b53 * k3 + b54 * k4), vdb_vec3, streamlines_scalar_type)
            k6, _ = sampleVDB(volume0, p + dt * (b61 * k1 + b62 * k2 + b63 * k3 + b64 * k4 + b65 * k5), vdb_vec3, streamlines_scalar_type)

            # Compute the 5th order and 4th order estimates
            p5 = p + dt * (c1 * k1 + c3 * k3 + c4 * k4 + c5 * k5 + c6 * k6)
            p4 = p + dt * (d1 * k1 + d3 * k3 + d4 * k4 + d5 * k5)

            # Compute the error estimate
            error = norm3f(p5 - p4)

            # use 5th order estimate
            # Wikipedia uses an average of p4&p5
            p = p5

            MIN_STEP_SIZE = dt_MIN
            MAX_STEP_SIZE = dt_MAX

            # grow step size
            if error < epsilon:

                if error == 0.0:
                    # Limit step size increase
                    dt_new = 2.0*dt
                else:
                    dt_new = 0.9 * dt * (epsilon / error)**(1.0/5.0)
                    # Limit step size increase
                    dt_new = min(dt_new, 2.0*dt)

                # Ensure step size is not too big
                dt_new = min(dt_new, MAX_STEP_SIZE)
                # wp.printf(" [%d:%d/%d] grow dt: error=%f, dt=%f, dt_new=%f (max=%f)\n", tid, it, num_timesteps, error, dt, dt_new, dt_MAX)

            # shrink step size
            else:

                dt_new = 0.9 * dt * (epsilon / error)**(1.0/5.0)
                # wp.printf("[%d:%d/%d] shrink dt: error=%f, dt=%f, dt_new=%f\n", tid, it, num_timesteps, error, dt, dt_new)

                # Ensure step size is not too small
                dt_new = max(dt_new, MIN_STEP_SIZE)

            dt = dt_new


def build_tet_bvh(vertices, idx_tet):

    N = idx_tet.shape[0] // 4

    lower_b = wp.empty(N, dtype=wp.vec3)
    upper_b = wp.empty(N, dtype=wp.vec3)

    wp.launch(build_tetrahedra_bb, N, inputs=[vertices, idx_tet, lower_b, upper_b])

    mesh_bvh = wp.Bvh(lower_b, upper_b)

    return mesh_bvh

def build_hex_bvh(vertices, idx_hex):

    N = idx_hex.shape[0] // 8

    lower_b = wp.empty(N, dtype=wp.vec3)
    upper_b = wp.empty(N, dtype=wp.vec3)

    wp.launch(build_hexahedra_bb, N, inputs=[vertices, idx_hex, lower_b, upper_b])

    mesh_bvh = wp.Bvh(lower_b, upper_b)

    return mesh_bvh


interop_dict = {}

def resolve_interop_handle(interop_handle, interop_size_in_bytes):
    # for this to work the following has to be set in flow
    # exts."omni.flowusd".voxelize_interop_enabled = false
    # exts."omni.flowusd".voxelize_readback_enabled = true

    if interop_handle == 0:
        raise Exception("Interop_handle is zero")

    if interop_handle in interop_dict:
        return interop_dict[interop_handle]

    desc = cuda.CUDA_EXTERNAL_MEMORY_HANDLE_DESC()
    desc.type = cuda.CUexternalMemoryHandleType.CU_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD
    dup_handle = os.dup(interop_handle)
    desc.handle.fd = dup_handle
    desc.size = interop_size_in_bytes
    (ret, externalMem) = cuda.cuImportExternalMemory(desc)
    if ret != cuda.CUresult.CUDA_SUCCESS:
        raise Exception(f"Failed to Import handle: cuImportExternalMemory :: {cuda.cuGetErrorString(ret)[1]}")

    buf_desc = cuda.CUDA_EXTERNAL_MEMORY_BUFFER_DESC()
    buf_desc.size = interop_size_in_bytes

    (ret, dev_ptr) = cuda.cuExternalMemoryGetMappedBuffer(externalMem, buf_desc)
    if ret != cuda.CUresult.CUDA_SUCCESS:
        raise Exception(f"Failed to get pointer: 'cuExternalMemoryGetMappedBuffer' :: {cuda.cuGetErrorString(ret)[1]}")

    interop_dict[interop_handle] = int(dev_ptr)

    return int(dev_ptr)

def upload_vdb_cpu_to_gpu(vdb, device=0):
    try:
        dev_ptr = resolve_interop_handle(vdb.handle_value, vdb.handle_size_bytes)
        vdb_warp = wp.array(ptr=dev_ptr, dtype=wp.uint32, shape=vdb.handle_size_bytes//4, device=f"cuda:{device}")
        return vdb_warp
    except Exception as e:
        print("Resolving GPU Interrop handle failed!: ", e, " Falling back to CPU pointer")
        ptr = ctypes.pythonapi.PyCapsule_GetPointer(vdb.data, None)
        ptr_int = ctypes.cast(ptr, ctypes.c_void_p).value
        vdb_shape = vdb.shape
        vdb_cpu = wp.array(ptr=ptr_int, dtype=wp.uint32, shape=vdb_shape, device="cpu")
        vdb_gpu = wp.array(vdb_cpu, dtype=wp.uint32, device=f"cuda:{device}")
        return vdb_gpu

@carb.profiler.profile
def advect_vector_field(vertices, idx_elem, mesh_type, vector_field_points, initial_points, vdb, vdb_gpu, dt=0.1, num_steps=5, streamlines_scalar_type=0, vdb_vec3=True, dt_MIN=0.01, dt_MAX=1.0, rk45_epsilon=0.001, device=0):
    carb.profiler.begin(1, "advect_vector_field pre warp kernel")
    wp.set_device(f"cuda:{device}")
    streamlines_paths = wp.zeros(initial_points.shape[0] * num_steps, dtype=wp.vec3f)
    streamlines_scalars = wp.zeros(initial_points.shape[0] * num_steps, dtype=wp.float32)

    interpolation_FEM = 0
    interpolation_MULTI_RESOLUTION_VDB = 1
    interpolation_SINGLE_VDB = 2
    interpolation_technique = -1
    if mesh_type == "TETRA_4":
        volume = build_tet_bvh(vertices, idx_elem)
        volumes = [volume, volume, volume, volume]
        vector_field = vector_field_points
        vector_fields = [vector_field, vector_field, vector_field, vector_field]
        pts_per_elem = 4
        interpolation_technique = interpolation_FEM
    elif mesh_type == "HEXA_8":
        volume = build_hex_bvh(vertices, idx_elem)
        volumes = [volume, volume, volume, volume]
        vector_field = vector_field_points
        vector_fields = [vector_field, vector_field, vector_field, vector_field]
        pts_per_elem = 8
        interpolation_technique = interpolation_FEM
    elif mesh_type == "POINTS":
        print("Running POINTS based advection")
        radius_factors = [0.1, 0.5, 1.0, 2.0]
        volumes = []
        vector_fields = []
        for radius_factor in radius_factors:
            volume = pointsToVolume(vertices, radius_factor=radius_factor)
            vector_field = rasterizeVelocityToVoxels(vertices, vector_field_points, volume)
            volumes.append(volume)
            vector_fields.append(vector_field)
        pts_per_elem = 0
        interpolation_technique = interpolation_MULTI_RESOLUTION_VDB

    elif mesh_type == "VDB":
        print("Running VDB based advection")
        radius_factors = [0.1, 0.5, 1.0, 2.0]
        # (vdb_ptr, vdb_size) = vdb

        # vdb_wp = wp.from_numpy(vdb)
        carb.profiler.begin(2, "advect_vector_field warp volume from vdb")
        vdb_ptr = vdb_gpu.ptr
        vdb_size = vdb.size_bytes
        volume = wp.Volume.load_from_address(vdb_ptr, vdb_size, device=f"cuda:{device}")
        carb.profiler.end(2)
        # f_vdb = open(vdb,"rb")
        # volume = wp.Volume.load_from_nvdb(f_vdb)
        # f_vdb.close()
        gi = wp.Volume.get_grid_info(volume)
        print("GridInfo=", gi)
        volumes = [volume, volume, volume, volume]
        empty_vector_field = wp.zeros(1, dtype=wp.vec3f)
        vector_fields = [empty_vector_field, empty_vector_field, empty_vector_field, empty_vector_field]
        pts_per_elem = -1
        interpolation_technique = interpolation_SINGLE_VDB
    else:
        pts_per_elem = -2
        raise RuntimeError(f"Unsupported element type: {mesh_type}")

    carb.profiler.end(1)
    carb.profiler.begin(1, "advect_vector_field warp kernel")
    wp.launch(
        advect_vector_field_kernel,
        dim=initial_points.shape,
        inputs=[volumes[0].id, volumes[1].id, volumes[2].id, volumes[3].id,
                initial_points, dt, num_steps, vertices, idx_elem, pts_per_elem,
                interpolation_technique,
                streamlines_scalar_type,
                int(vdb_vec3),
                vector_fields[0], vector_fields[1], vector_fields[2], vector_fields[3],
                streamlines_paths, streamlines_scalars, dt_MIN, dt_MAX, rk45_epsilon],
        device=f"cuda:{device}"
    )
    carb.profiler.end(1)

    return (streamlines_paths, streamlines_scalars)


def display_streamline(stage, vertices):
    wp_stage = wp.render.UsdRenderer(stage)
    stage.render_line_list(name="test_line")


@wp.kernel
def build_hexahedra_bb(
    vertices: wp.array(dtype=wp.vec3f),
    idx_hex: wp.array(dtype=wp.int32),
    lower_b: wp.array(dtype=wp.vec3),
    upper_b: wp.array(dtype=wp.vec3),
):

    tid = wp.tid()
    a = vertices[idx_hex[8 * tid + 0]]
    b = vertices[idx_hex[8 * tid + 1]]
    c = vertices[idx_hex[8 * tid + 2]]
    d = vertices[idx_hex[8 * tid + 3]]
    e = vertices[idx_hex[8 * tid + 4]]
    f = vertices[idx_hex[8 * tid + 5]]
    g = vertices[idx_hex[8 * tid + 6]]
    h = vertices[idx_hex[8 * tid + 7]]


    min_x = a.x
    min_x = min(min_x, b.x)
    min_x = min(min_x, c.x)
    min_x = min(min_x, d.x)
    min_x = min(min_x, d.x)
    min_x = min(min_x, e.x)
    min_x = min(min_x, f.x)
    min_x = min(min_x, g.x)
    min_x = min(min_x, h.x)

    min_y = a.y
    min_y = min(min_y, b.y)
    min_y = min(min_y, c.y)
    min_y = min(min_y, d.y)
    min_y = min(min_y, e.y)
    min_y = min(min_y, f.y)
    min_y = min(min_y, g.y)
    min_y = min(min_y, h.y)

    min_z = a.z
    min_z = min(min_z, b.z)
    min_z = min(min_z, c.z)
    min_z = min(min_z, d.z)
    min_z = min(min_z, e.z)
    min_z = min(min_z, f.z)
    min_z = min(min_z, g.z)
    min_z = min(min_z, h.z)

    max_x = a.x
    max_x = max(max_x, b.x)
    max_x = max(max_x, c.x)
    max_x = max(max_x, d.x)
    max_x = max(max_x, d.x)
    max_x = max(max_x, e.x)
    max_x = max(max_x, f.x)
    max_x = max(max_x, g.x)
    max_x = max(max_x, h.x)

    max_y = a.y
    max_y = max(max_y, b.y)
    max_y = max(max_y, c.y)
    max_y = max(max_y, d.y)
    max_y = max(max_y, e.y)
    max_y = max(max_y, f.y)
    max_y = max(max_y, g.y)
    max_y = max(max_y, h.y)

    max_z = a.z
    max_z = max(max_z, b.z)
    max_z = max(max_z, c.z)
    max_z = max(max_z, d.z)
    max_z = max(max_z, e.z)
    max_z = max(max_z, f.z)
    max_z = max(max_z, g.z)
    max_z = max(max_z, h.z)

    lower_b[tid] = wp.vec3(min_x, min_y, min_z)
    upper_b[tid] = wp.vec3(max_x, max_y, max_z)


@wp.kernel
def build_tetrahedra_bb(
    vertices: wp.array(dtype=wp.vec3f),
    idx_tet: wp.array(dtype=wp.int32),
    lower_b: wp.array(dtype=wp.vec3),
    upper_b: wp.array(dtype=wp.vec3)):

    tid = wp.tid()
    a = vertices[idx_tet[4 * tid + 0]]
    b = vertices[idx_tet[4 * tid + 1]]
    c = vertices[idx_tet[4 * tid + 2]]
    d = vertices[idx_tet[4 * tid + 3]]

    min_x = a.x
    min_x = min(min_x, b.x)
    min_x = min(min_x, c.x)
    min_x = min(min_x, d.x)

    min_y = a.y
    min_y = min(min_y, b.y)
    min_y = min(min_y, c.y)
    min_y = min(min_y, d.y)

    min_z = a.z
    min_z = min(min_z, b.z)
    min_z = min(min_z, c.z)
    min_z = min(min_z, d.z)

    max_x = a.x
    max_x = max(max_x, b.x)
    max_x = max(max_x, c.x)
    max_x = max(max_x, d.x)

    max_y = a.y
    max_y = max(max_y, b.y)
    max_y = max(max_y, c.y)
    max_y = max(max_y, d.y)

    max_z = a.z
    max_z = max(max_z, b.z)
    max_z = max(max_z, c.z)
    max_z = max(max_z, d.z)

    lower_b[tid] = wp.vec3(min_x, min_y, min_z)
    upper_b[tid] = wp.vec3(max_x, max_y, max_z)


# def test_tet_bb(vertices, idx_tet):

#     N = idx_tet.shape[0] // 4

#     lower_b = wp.empty(N, dtype=wp.vec3)
#     upper_b = wp.empty(N, dtype=wp.vec3)

#     wp.launch(build_tetrahedra_bb, N, inputs=[vertices, idx_tet, lower_b, upper_b])

#     print("lower_b=", lower_b)
#     print("upper_b=", upper_b)


# @wp.kernel
# def test_point_in_tetrahedra(vertices: wp.array(dtype=wp.vec3f), idx_tet: wp.array(dtype=wp.int32)):
#     p = wp.vec3f(0.1, 0.1, 0.1)
#     p2 = wp.vec3f(1.1, 0.1, 0.1)
#     p3 = wp.vec3f(0.99, 0.99, 0.99)
#     if point_in_tetrahedra(p, vertices, idx_tet, 0) != True:
#         print("ERROR Test 'p' failed")
#     if point_in_tetrahedra(p2, vertices, idx_tet, 0) != False:
#         print("ERROR Test 'p2' failed")
#     if point_in_tetrahedra(p3, vertices, idx_tet, 1) != True:
#         print("ERROR Test 'p3' failed")


@wp.kernel
def test_point_in_hexahedra(vertices: wp.array(dtype=wp.vec3f), idx_elem: wp.array(dtype=wp.int32)):
    p = wp.vec3f(0.1, 0.1, 0.1)
    p2 = wp.vec3f(1.1, 0.1, 0.1)
    p3 = wp.vec3f(0.99, 0.99, 0.99)
    p4 = wp.vec3f(1.1, 0.1, 0.1)
    if point_in_hexahedra(p, vertices, idx_elem, 0) != True:
        print("ERROR Test 'p' failed")
    if point_in_hexahedra(p2, vertices, idx_elem, 0) != False:
        print("ERROR Test 'p2' failed")
    if point_in_hexahedra(p2, vertices, idx_elem, 1) != True:
        print("ERROR Test 'p2' failed")
    if point_in_hexahedra(p3, vertices, idx_elem, 0) != True:
        print("ERROR Test 'p3' failed")
    if point_in_hexahedra(p4, vertices, idx_elem, 1) != True:
        print("ERROR Test 'p4' failed")


# @wp.kernel
# def test_tetrahedra_cube_ratio(
#     points: wp.array(dtype=wp.vec3f),
#     vertices: wp.array(dtype=wp.vec3f),
#     idx_tet: wp.array(dtype=wp.int32),
#     results: wp.array(dtype=wp.int32),
# ):

#     # p_ = points[wp.tid()]
#     # p = wp.vec3f(points[wp.tid(),0], points[wp.tid(),1], points[wp.tid(),2])
#     p = points[wp.tid()]
#     if point_in_tetrahedra(p, vertices, idx_tet, 0):
#         results[wp.tid()] = 1


# @wp.kernel
# def test_tetrahedra_interpolation(
#     vertices: wp.array(dtype=wp.vec3f), idx_tet: wp.array(dtype=wp.int32), field: wp.array(dtype=wp.float32)
# ):
#     fp0 = interpolate_field(wp.vec3f(0.0, 0.0, 0.0), vertices, idx_tet, 0, field)
#     fp1 = interpolate_field(wp.vec3f(1.0, 0.0, 0.0), vertices, idx_tet, 0, field)
#     fp2 = interpolate_field(wp.vec3f(0.0, 1.0, 0.0), vertices, idx_tet, 0, field)
#     fp3 = interpolate_field(wp.vec3f(0.0, 0.0, 1.0), vertices, idx_tet, 0, field)
#     fp4 = interpolate_field(wp.vec3f(1.0, 1.0, 1.0), vertices, idx_tet, 1, field)

#     print("fp=")
#     print(fp0)
#     print(fp1)
#     print(fp2)
#     print(fp3)
#     print(fp4)


# @wp.kernel
# def test_tetrahedra_vec_interpolation(
#     vertices: wp.array(dtype=wp.vec3f), idx_tet: wp.array(dtype=wp.int32), vec_field: wp.array(dtype=wp.vec3f)
# ):
#     fp0 = interpolate_vector_field(wp.vec3f(0.0, 0.0, 0.0), vertices, idx_tet, 0, vec_field)
#     fp1 = interpolate_vector_field(wp.vec3f(1.0, 0.0, 0.0), vertices, idx_tet, 0, vec_field)
#     fp2 = interpolate_vector_field(wp.vec3f(0.0, 1.0, 0.0), vertices, idx_tet, 0, vec_field)
#     fp3 = interpolate_vector_field(wp.vec3f(0.0, 0.0, 1.0), vertices, idx_tet, 0, vec_field)
#     fp4 = interpolate_vector_field(wp.vec3f(1.0, 1.0, 1.0), vertices, idx_tet, 1, vec_field)
#     fp5 = interpolate_vector_field(wp.vec3f(0.9, 0.9, 0.9), vertices, idx_tet, 1, vec_field)

#     print("fp=")
#     print(fp0)
#     print(fp1)
#     print(fp2)
#     print(fp3)
#     print(fp4)
#     print(fp5)

def make_basis_curve(stage, vertices, idx_count, N, path="/World/streamlines", width=0.5):
    prim = stage.GetPrimAtPath(path)
    if prim:
        stage.RemovePrim(path)

    basis_curve = UsdGeom.BasisCurves.Define(stage, path)
    basis_curve.CreatePointsAttr()
    basis_curve.CreateCurveVertexCountsAttr()
    basis_curve.CreateTypeAttr().Set("linear")
    basis_curve.CreateWidthsAttr()  # .Set(2*np.ones(len(idx_count)))
    basis_curve.GetWidthsAttr().Set((width * np.ones(N)).tolist())
    basis_curve.SetWidthsInterpolation("constant")
    # print("widths=", widths)
    # greenish = np.linspace(0.1, 1.0, N)
    # color = [Gf.Vec3f(g, 1.0, 0.0) for g in greenish]
    # # basis_curve.CreateDisplayColorAttr().Set([Gf.Vec3f(0.0,1.0,0.0)])
    # basis_curve.CreateDisplayColorAttr().Set(color)

    vertices_vt = Vt.Vec3fArray.FromNumpy(vertices)

    # print("vertices_vt=", vertices_vt)
    # print("idx_count=", idx_count_vt)
    # for i in range(vertices.shape[0]):
    # vertices_vt.append(Gf.Vec3f(vertices[i,0].item(), vertices[i,1].item(), vertices[i,2].item()))

    basis_curve.GetPointsAttr().Set(vertices_vt)
    basis_curve.GetCurveVertexCountsAttr().Set(idx_count)
    # print("VertexCounts=", basis_curve.GetCurveVertexCountsAttr().Get())

    return basis_curve

def test_tet():
    vertices = wp.array(
        [
            wp.vec3f(0.0, 0.0, 0.0),
            wp.vec3f(1.0, 0.0, 0.0),
            wp.vec3f(0.0, 1.0, 0.0),
            wp.vec3f(0.0, 0.0, 1.0),
            wp.vec3f(1.0, 1.0, 1.0),
        ],
        dtype=wp.vec3f,
    )

    idx_tet = wp.array([0, 1, 2, 3, 1, 2, 3, 4], dtype=wp.int32)

    save_tetmesh_vtk(vertices.numpy(), idx_tet.numpy())

    wp.launch(kernel=test_point_in_tetrahedra, dim=(1,), inputs=[vertices, idx_tet])
    # sys.exit(0)
    # p = wp.vec3f(0.1, 0.1, 0.1)
    # p2 = wp.vec3f(1.1, 0.1, 0.1)
    # p3 = wp.vec3f(0.5, 0.5, 0.5)
    # assert(point_in_tetrahedra(p, vertices, idx_tet) is True)
    # assert(point_in_tetrahedra(p2, vertices, idx_tet) is False)
    # print("p3=", point_in_tetrahedra(p2, vertices, idx_tet))

    N = 10000
    p3 = cp.random.random((N, 3), dtype=cp.float32)
    p3wp = wp.from_numpy(p3.get(), dtype=wp.vec3)

    results = wp.zeros(N, dtype=wp.int32)

    wp.launch(kernel=test_tetrahedra_cube_ratio, dim=(N,), inputs=[p3wp, vertices, idx_tet, results])

    print("Ratio=", cp.sum(cp.array(results)) / N, "vs ", 1 / 6)

    field = wp.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=wp.float32)
    vector_field = wp.array(
        [
            wp.vec3f(1.0, 1.0, 1.0),
            wp.vec3f(2.0, 2.0, 2.0),
            wp.vec3f(3.0, 3.0, 3.0),
            wp.vec3f(4.0, 4.0, 4.0),
            wp.vec3f(5.0, 5.0, 5.0),
        ],
        dtype=wp.vec3f,
    )
    initial_points = wp.array([wp.vec3f(0.2, 0.2, 0.2), wp.vec3f(0.6, 0.6, 0.6)], dtype=wp.vec3f)
    # wp.launch(kernel=test_tetrahedra_interpolation, dim=(1,), inputs=[vertices, idx_tet, field])
    # wp.launch(kernel=test_tetrahedra_vec_interpolation, dim=(1,), inputs=[vertices, idx_tet, vector_field])

    # test_tet_bb(vertices, idx_tet)

    solutions = advect_vector_field(vertices, idx_tet, "TETRA_4", vector_field, initial_points, dt=0.01)

def get_hex_data():
    vertices_hexes = wp.array(
        [
            # CGNS layout
            wp.vec3f(1.0, 0.0, 0.0),
            wp.vec3f(1.0, 1.0, 0.0),
            wp.vec3f(0.0, 1.0, 0.0),
            wp.vec3f(0.0, 0.0, 0.0),

            wp.vec3f(1.0, 0.0, 1.0),
            wp.vec3f(1.0, 1.0, 1.0),
            wp.vec3f(0.0, 1.0, 1.0),
            wp.vec3f(0.0, 0.0, 1.0),

            wp.vec3f(2.0, 0.0, 0.0),
            wp.vec3f(2.0, 1.0, 0.0),
            wp.vec3f(2.0, 1.0, 1.0),
            wp.vec3f(2.0, 0.0, 1.0),

        ],
        dtype=wp.vec3f,
    )

    idx_hex = wp.array([0, 1, 2, 3,   4, 5, 6, 7,   8, 9, 1, 0,   11, 10, 5, 4], dtype=wp.int32)

    field_hex = wp.array([
        wp.vec3f(0.5, 0.1, 0.1), # 0
        wp.vec3f(0.5, -0.1, 0.1), # 1
        wp.vec3f(0.5, -0.1, 0.1), # 2
        wp.vec3f(0.5, 0.1, 0.1), # 3

        wp.vec3f(0.5, 0.1, -0.1), # 4
        wp.vec3f(0.5, -0.1, -0.1), # 5
        wp.vec3f(0.5, -0.1, -0.1), # 6
        wp.vec3f(0.5, 0.1, -0.1), # 7

        wp.vec3f(0.5, 0.1, 0.1), # 8
        wp.vec3f(0.5, -0.1, 0.1), # 9
        wp.vec3f(0.5, -0.1, -0.1), # 10
        wp.vec3f(0.5, 0.1, -0.1), # 11
        ], dtype=wp.vec3f)

    initial_points_hex = wp.array([
        # wp.vec3f(0.001,0.5,0.5),
        wp.vec3f(0.25,0.25,0.25),
        wp.vec3f(0.25,0.75,0.25),
        wp.vec3f(0.25,0.25,0.75),
        wp.vec3f(0.25,0.75,0.75),
    ], dtype=wp.vec3f)

    return vertices_hexes, idx_hex, field_hex, initial_points_hex


# def lots_of_hex_data(N=100):



def test_hex():

    vertices_hexes, idx_hex, field_hex, initial_points_hex = get_hex_data()

    wp.launch(kernel=test_point_in_hexahedra, dim=(1,), inputs=[vertices_hexes, idx_hex])


    num_steps=10
    solutions_hex = advect_vector_field(vertices_hexes, idx_hex, "HEXA_8", field_hex, initial_points_hex, dt=0.4, num_steps=num_steps)

    # print(f"solutions_hex={solutions_hex}")

    stage = Usd.Stage.CreateNew('test_2hex_streamlines.usda')

    idx_hull = generate_hull(idx_hex, "HEXA_8")
    hull_mesh_to_stage(vertices_hexes.numpy(), idx_hull.numpy(), None, stage, "/World", 4)

    print("solutions_hex=", solutions_hex)
    make_basis_curve(stage, solutions_hex.numpy(), num_steps * np.ones(4), 4, width=0.02,path="/World/streamlines")

    stage.Save()


def test_nanovdb_build():

    volume = np.load("/home/max/dev/cgns-carbonite/examples/file_0_volume.npy")
    xyz = volume[:,0:3]
    v = volume[:,3:6]

    xyz_wp = wp.from_numpy(xyz, dtype=wp.vec3f)
    v_wp = wp.from_numpy(v, dtype=wp.vec3f)

    vol = pointsToVolume(xyz_wp)


def test_nanovdb_sparse_hex():

    vertices_hexes, idx_hex, field_hex, initial_points_hex = get_hex_data()

    # vol = pointsToVolume(vertices_hexes)

    num_steps=10
    solutions_points = advect_vector_field(vertices_hexes, None, "POINTS", field_hex, initial_points_hex, dt=0.4, num_steps=num_steps)
    solutions_hex = advect_vector_field(vertices_hexes, idx_hex, "HEXA_8", field_hex, initial_points_hex, dt=0.4, num_steps=num_steps)

    stage = Usd.Stage.CreateNew('test_hexpoints_streamlines.usda')

    idx_hull = generate_hull(idx_hex, "HEXA_8")
    hull_mesh_to_stage(vertices_hexes.numpy(), idx_hull.numpy(), None, stage, "/World", 4)

    print("solutions_hex=", solutions_hex)
    print("solutions_points=", solutions_points)
    make_basis_curve(stage, solutions_hex.numpy(), num_steps * np.ones(4), 4, width=0.02,path="/World/streamlines_hex")
    make_basis_curve(stage, solutions_points.numpy(), num_steps * np.ones(4), 4, width=0.02,path="/World/streamlines_points")

    stage.Save()


def test_nanovdb_dense_hex():

    vertices_hexes, idx_hex, field_hex, initial_points_hex = get_hex_data()
    points_dense, field_dense = gen_point_cloud_hex(10)

    vol = pointsToVolume(points_dense)

    num_steps=10
    solutions_points = advect_vector_field(points_dense, None, "POINTS", field_dense, initial_points_hex, dt=0.4, num_steps=num_steps)
    solutions_hex = advect_vector_field(vertices_hexes, idx_hex, "HEXA_8", field_hex, initial_points_hex, dt=0.4, num_steps=num_steps)

    stage = Usd.Stage.CreateNew('test_hexpoints_streamlines.usda')

    idx_hull = generate_hull(idx_hex, "HEXA_8")
    hull_mesh_to_stage(vertices_hexes.numpy(), idx_hull.numpy(), None, stage, "/World", 4)

    print("solutions_hex=", solutions_hex)
    print("solutions_points=", solutions_points)
    make_basis_curve(stage, solutions_hex.numpy(), num_steps * np.ones(4), 4, width=0.02,path="/World/streamlines_hex")
    make_basis_curve(stage, solutions_points.numpy(), num_steps * np.ones(4), 4, width=0.02,path="/World/streamlines_points")

    stage.Save()



@wp.kernel
def interpolate_pointcloud_kernel(bvh: wp.uint64,
                           points: wp.array(dtype=wp.vec3f),
                           vertices: wp.array(dtype=wp.vec3f),
                           idx_elem: wp.array(dtype=wp.int32),
                           sparse_velocity_field: wp.array(dtype=wp.vec3f),
                           dense_velocity_field: wp.array(dtype=wp.vec3f)):

    tid = wp.tid()
    point = points[tid]
    eps = wp.vec3f(1e-8, 1e-8, 1e-8)
    lower_b = point - eps
    upper_b = point + eps
    query = wp.bvh_query_aabb(bvh, lower_b, upper_b)
    candidate_idx = wp.int32(-1)
    while wp.bvh_query_next(query, candidate_idx):
        if point_in_hexahedra(point, vertices, idx_elem, candidate_idx):
            found_idx = candidate_idx
            dense_velocity_field[tid] = interpolate_vector_field_hex(point, vertices, idx_elem, found_idx, sparse_velocity_field)


def storeValuesVDB(volume: wp.uint64,
                   points: wp.array(dtype=wp.vec3f),
                   velocity_field: wp.array(dtype=wp.vec3f)):

    tid = wp.tid()
    point = points[tid]
    q = wp.volume_world_to_index(volume, point)



def gen_point_cloud_hex(N=10):

    vertices_hexes, idx_hex, field_hex, initial_points_hex = get_hex_data()
    eps = 1e-8
    x = np.linspace(0+eps,2-eps,N)
    y = np.linspace(0+eps,1-eps,N)
    z = np.linspace(0+eps,1-eps,N)
    X,Y,Z = np.meshgrid(x,y,z)
    XYZ_np = np.column_stack((X.ravel(),Y.ravel(),Z.ravel()))
    XYZ = wp.from_numpy(XYZ_np, dtype=wp.vec3f)
    dense_velocity_field = wp.zeros_like(XYZ)
    bvh_hex = build_hex_bvh(vertices_hexes, idx_hex)
    wp.launch(interpolate_pointcloud_kernel, XYZ.shape[0],
              inputs=[bvh_hex.id, XYZ, vertices_hexes, idx_hex, field_hex, dense_velocity_field])
    return XYZ, dense_velocity_field


def compute_interpolation_hex():
    from sympy import symbols,Matrix,S
    from sympy.solvers.solveset import linsolve
    x,y,z,f0,f1,f2,f3,f4,f5,f6,f7 = symbols("x,y,z,f0,f1,f2,f3,f4,f5,f6,f7")
    # The linear interpolating polynomial. Needs 8 terms for 8 corners
    eq = [S.One, x, x*y, y,z,x*z,y*z,x*y*z]
    corners = [(0,0,0),(0,1,0),(1,1,0),(1,0,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
    # vandermonde matrix, essentially 'eq' evaluated at each point
    V = Matrix([[eqi.subs({x:xi,y:yi,z:zi}) for eqi in eq] for (xi,yi,zi) in corners])
    b = Matrix([f0,f1,f2,f3,f4,f5,f6,f7])
    # solver solves V@x = b for 'x'. Basically solve for the right combo of
    # 'fn' so that the interpolation is correct at all the corners
    x = Matrix(linsolve((V,b)).args[0])
    interpolation_expr = Matrix(eq).T @ x
    print("interpolation = ", interpolation_expr)


def points_to_usd(stage, point_cloud, point_size=0.01, scalar_field=None, path="/World/pointcloud"):

    num_points = point_cloud.shape[0]

    # pointInstancer = UsdGeom.PointInstancer.Define(stage, path)
    # pointInstancer.CreatePositionsAttr(points)


    # Sample color data using NumPy
    # colors = np.random.rand(num_points, 3)  # Random RGB colors

    # Add colors as a primvar
    # colorPrimvar = pointInstancer.CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3f, UsdGeom.Tokens.vertex)
    # colorPrimvar.Set(colors)
    # colorPrimvar.Set(colormap[:, :3])  # Use RGB values from colormap

    # chatgpt
    # breakpoint()
    # gf_colormap = [Gf.Vec3f(*color) for color in colormap]
    # colormap_gf = [Gf.Vec3f(*color) for color in colormap[:,0:3]]

    from matplotlib import cm
    from matplotlib.colors import Normalize
    points = UsdGeom.Points.Define(stage, path)
    points.GetPointsAttr().Set(point_cloud)
    sizes = np.ones(num_points)*point_size
    points.GetWidthsAttr().Set(sizes)

    if not isinstance(scalar_field, type(None)):
        assert num_points == scalar_field.shape[0]
        norm = Normalize(vmin=np.min(scalar_field), vmax=np.max(scalar_field))
        colormap = cm.viridis(norm(scalar_field))

        print(f"scalar_field.shape={scalar_field.shape}, colormap.shape=", colormap.shape)
        points.CreateDisplayColorAttr(colormap[:,0:3])
        points.GetDisplayColorPrimvar().SetInterpolation('vertex')


def initial_points_from_pointcloud(points, eps=0.05, line=False):

        # bounds
    eps = 0.05
    xmin = np.min(points[:,0])
    xmax = np.max(points[:,0])

    ymin = np.min(points[:,1])
    ymax = np.max(points[:,1])

    zmin = np.min(points[:,2])
    zmax = np.max(points[:,2])

    npoints = 10
    print(f"Bounding box: ({(xmin,ymin,zmin)})x({(xmax,ymax,zmax)})")

    xd = xmax-xmin
    xmin += eps*xd
    xmax -= eps*xd
    yd = ymax-ymin
    ymin += eps*yd
    ymax -= eps*yd
    zd = zmax-zmin
    zmin += eps*zd
    zmax -= eps*zd


    # line
    if line:
        X = np.ones(npoints)*xmin
        Y = np.ones(npoints)*((ymax-ymin)/2 + ymin)
        Z = np.linspace(zmin, zmax, npoints)
        initial_points = wp.from_numpy(np.column_stack((X.ravel(), Y.ravel(),Z.ravel())), dtype=wp.vec3f)
        return initial_points

    # plane
    y = np.linspace(ymin, ymax, npoints)
    z = np.linspace(zmin, zmax, npoints)
    # X,Y,Z = np.meshgrid(x, y, z)
    Y,Z = np.meshgrid(y, z)
    X = np.ones(npoints*npoints)*xmin
    initial_points = wp.from_numpy(np.column_stack((X.ravel(), Y.ravel(),Z.ravel())), dtype=wp.vec3f)

    return initial_points


def test_numpy_to_usd(points, vector_field=None, scalar_field=None, point_size=0.01, stage_url="pointcloud.usd"):

    stage = Usd.Stage.CreateNew(stage_url)
    points_to_usd(stage, points, scalar_field=scalar_field, point_size=point_size)

    if isinstance(vector_field, type(None)):
        return

    # bounds
    eps = 0.05
    xmin = np.min(points[:,0])
    xmax = np.max(points[:,0])

    ymin = np.min(points[:,1])
    ymax = np.max(points[:,1])

    zmin = np.min(points[:,2])
    zmax = np.max(points[:,2])

    npoints = 10
    print(f"Bounding box: ({(xmin,ymin,zmin)})x({(xmax,ymax,zmax)})")

    xd = xmax-xmin
    xmin += eps*xd
    xmax -= eps*xd
    yd = ymax-ymin
    ymin += eps*yd
    ymax -= eps*yd
    zd = zmax-zmin
    zmin += eps*zd
    zmax -= eps*zd

    x = np.ones(npoints)*xmin
    # y = np.linspace(ymin, ymax, npoints)
    y = np.ones(npoints)*((ymax-ymin)/2 + ymin)
    z = np.linspace(zmin, zmax, npoints)
    X,Y,Z = np.meshgrid(x, y, z)
    initial_points = wp.from_numpy(np.column_stack((X.ravel(), Y.ravel(),Z.ravel())), dtype=wp.vec3f)

    num_steps=30
    solutions_points = advect_vector_field(wp.from_numpy(points, dtype=wp.vec3f), None, "POINTS", wp.from_numpy(vector_field, dtype=wp.vec3f), initial_points, dt=0.4, num_steps=num_steps)
    num_streamlines = initial_points.shape[0]
    make_basis_curve(stage, solutions_points.numpy(), num_steps * np.ones(num_streamlines), num_streamlines, width=0.02,path="/World/streamlines")
    stage.Save()

if __name__ == "__main__":
    import cupy as cp
    from vtk_writer import save_tetmesh_vtk
    from triangulated_hull import generate_hull, hull_mesh_to_stage

    # compute_interpolation_hex()

    # test_tet()
    # test_hex()
    test_nanovdb_dense_hex()

    testSampleVolume()

    points_dense, field_dense = gen_point_cloud_hex(10)
    wp.synchronize()
    # breakpoint()
    test_numpy_to_usd(points_dense.numpy(), scalar_field=np.linalg.norm(field_dense.numpy(),axis=-1),
                      point_size=0.05,
                      stage_url="pointcloud_test_color.usda")

    pc = np.load("/home/max/dev/cgns-carbonite/examples/new_files/file_0_volume.npy", allow_pickle=True).item()
    pv = np.load("/home/max/dev/cgns-carbonite/examples/file_0_volume.npy")
    test_numpy_to_usd(pv[:,:3],
                      vector_field=pv[:,3:],
                      scalar_field=np.linalg.norm(pv[:,3:], axis=-1),
                      stage_url='file_0_volume.usd')


    # from stage import create_cgns_stage

    # stage = create_cgns_stage("volume", "/home/max/dev/cgns_work/data/yf17_hdf5.cgns")

    # create_cgns_stage

    # total_inside = 0
    # for i in range(N):
    #     p = wp.vec3f(p3[i,0], p3[i,1], p3[i,2])
    # if point_in_tetrahedra(p, vertices, idx_tet):
    #     total_inside += 1

    # print(f"Ratio inside: {total_inside/N} vs {1/6}")
