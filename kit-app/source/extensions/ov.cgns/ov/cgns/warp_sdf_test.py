import numpy as np
import pyvtk
import warp as wp


# pure python version for testing
def build_edges_occurance(idx_tet):

    edges_occurance = {}
    num_normal = 0
    num_duplicated = 0
    for tid in range(idx_tet.shape[0] // 4):
        idx0 = idx_tet[4 * tid + 0]
        idx1 = idx_tet[4 * tid + 1]
        idx2 = idx_tet[4 * tid + 2]
        idx3 = idx_tet[4 * tid + 3]

        tri0 = [idx0, idx2, idx1]
        tri1 = [idx0, idx1, idx3]
        tri2 = [idx0, idx3, idx2]
        tri3 = [idx1, idx2, idx3]

        # sanity checking
        if len(np.unique(np.array([idx0, idx1, idx2, idx3]))) < 4:
            if num_duplicated == 0:
                print(f"[{tid}]Duplicated vertex index! ({(idx0,idx1,idx2,idx3)})")
            num_duplicated += 1

        num_normal += 1

        tri0.sort()
        tri1.sort()
        tri2.sort()
        tri3.sort()

        def e2o(tri, edge_id):
            tri_ = (tri[0], tri[1], tri[2])
            if tri_ in edges_occurance:
                tids = edges_occurance[tri_]
                tids.append((tid, edge_id))
                # edges_occurance[tri_] = tids
            else:
                edges_occurance[tri_] = [(tid, edge_id)]

        e2o(tri0, 0)
        e2o(tri1, 1)
        e2o(tri2, 2)
        e2o(tri3, 3)

    return edges_occurance


# pure python version for testing
def build_hull_triangles(edges_occurance):

    triangles = []

    for (k, v) in edges_occurance.items():

        if len(v) == 1:
            triangles.append(k[0])
            triangles.append(k[1])
            triangles.append(k[2])

    return np.array(triangles)


# simple utility function to write out tets or triangles to a vtk file for viz in Paraview
def save_tetmesh_vtk(
    vertices_np: np.array, idx_tet_np=None, idx_tri_np=None, mesh_name="Output mesh", filename="test_mesh"
):

    print("idx_tet_np=", idx_tet_np)
    print("idx_tri_np=", idx_tri_np)
    # if idx_tet_np is not None: print("Num Tets=", idx_tet_np.shape)
    # if idx_tri_np is not None: print("Num Tris=", idx_tri_np.shape)

    vertices = list(zip(vertices_np[:, 0], vertices_np[:, 1], vertices_np[:, 2]))
    idx_tet = None
    if idx_tet_np is not None:
        idx_tet = []
        for i in range(idx_tet_np.shape[0] // 4):
            this_tet = [
                int(idx_tet_np[4 * i + 0]),
                int(idx_tet_np[4 * i + 1]),
                int(idx_tet_np[4 * i + 2]),
                int(idx_tet_np[4 * i + 3]),
            ]
            idx_tet.append(this_tet)

    idx_tri = None
    if idx_tri_np is not None:
        idx_tri = []
        for i in range(idx_tri_np.shape[0] // 3):
            this_tri = [int(idx_tri_np[3 * i + 0]), int(idx_tri_np[3 * i + 1]), int(idx_tri_np[3 * i + 2])]
            idx_tri.append(this_tri)

    vtk = pyvtk.VtkData(pyvtk.UnstructuredGrid(vertices, tetra=idx_tet, triangle=idx_tri), mesh_name)
    vtk.tofile(filename)
    # vtk.tofile('Delaunay2Db','binary')


@wp.func
def count_intersections(mesh: wp.uint64, p0: wp.vec3f, n: wp.vec3f, max_t: wp.float32):

    count = wp.int32(0)
    t_cumulative = wp.float32(0.0)
    while True:
        res = wp.mesh_query_ray(mesh, p0, n, max_t)
        if res.result:
            count += 1
            t_cumulative += res.t
            p0 += (res.t + 0.001) * n
            if count > 100:
                break
        else:
            break

    return count


@wp.kernel
def fix_triangle_hull_orientation_kernel(
    mesh: wp.uint64, vertices: wp.array(dtype=wp.vec3f), idx_tri: wp.array(dtype=wp.int32)
):

    tid = wp.tid()

    a = vertices[idx_tri[3 * tid + 0]]
    b = vertices[idx_tri[3 * tid + 1]]
    c = vertices[idx_tri[3 * tid + 2]]

    eps = wp.length(a - b) / 100.0
    n = wp.normalize(wp.cross(b - a, c - a))
    abc = (a + b + c) / 3.0
    p = abc + eps * n

    res = wp.mesh_query_point_sign_winding_number(mesh, p, 1000.0 * wp.length(a - b))
    # res = wp.mesh_query_point(mesh, p, 10.0*wp.length(a-b))

    sign_avg = wp.float32(0.0)
    for i in range(11):
        rnd = wp.rand_init(42)
        n = wp.sample_unit_sphere_surface(rnd)
        count = count_intersections(mesh, p, n, 1000.0)
        if count % 2 == 0:
            sign_avg += 1.0
        else:
            sign_avg -= 1.0

    # want inside of box to be "front" of triangles
    wp.printf("mesh_query_res.sign=%f, counting avg sign=%f\n", res.sign, sign_avg)
    if sign_avg >= 0:
        tmp = idx_tri[3 * tid + 2]
        idx_tri[3 * tid + 2] = idx_tri[3 * tid + 1]
        idx_tri[3 * tid + 1] = tmp


def fix_triangle_hull_orientation(vertices, idx_tri):
    mesh = wp.Mesh(vertices, wp.array(idx_tri, dtype=wp.int32), support_winding_number=True)
    # mesh = wp.Mesh(vertices, wp.array(idx_tri, dtype=wp.int32))

    wp.launch(fix_triangle_hull_orientation_kernel, int(idx_tri.shape[0] // 3), inputs=[mesh.id, vertices, idx_tri])


if __name__ == "__main__":
    from vtk_writer import read_tetmesh_vtk, save_tetmesh_vtk

    wp.init()
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

    edge_occurances_np = build_edges_occurance(idx_tet.numpy())
    idx_tri = wp.from_numpy(build_hull_triangles(edge_occurances_np))

    fix_triangle_hull_orientation(vertices, idx_tri)

    save_tetmesh_vtk(vertices.numpy(), idx_tri_np=idx_tri.numpy(), filename="tri_mesh")
