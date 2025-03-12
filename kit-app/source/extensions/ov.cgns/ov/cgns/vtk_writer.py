import numpy as np
import vtk


def write_vtk(dataset, filename, binary=True):

    # Erase field data for compatibility with non-standard importers
    for fd in dataset.FieldData.keys():
        dataset.FieldData.RemoveArray(fd)

    writer = vtk.vtkDataSetWriter()
    writer.SetInputDataObject(dataset.VTKObject)
    writer.SetFileName(filename)
    writer.SetFileVersion(writer.VTK_LEGACY_READER_VERSION_4_2)
    if binary:
        writer.SetFileTypeToBinary()
    else:
        writer.SetFileTypeToASCII()
    writer.Write()
    print("output: ", filename)


def save_tetmesh_vtk(
    vertices_np: np.array, idx_tet_np=None, idx_tri_np=None, mesh_name="Output mesh", filename="test_mesh"
):

    print("idx_tet_np=", idx_tet_np)
    print("idx_tri_np=", idx_tri_np)
    # if idx_tet_np is not None: print("Num Tets=", idx_tet_np.shape)
    # if idx_tri_np is not None: print("Num Tris=", idx_tri_np.shape)

    import pyvtk

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


def read_tetmesh_vtk(filename, vtx_count=5):
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    reader = vtk.vtkUnstructuredGridReader()
    reader.SetFileName(filename)
    reader.Update()

    # Get the output of the reader, which is a vtkUnstructuredGrid
    unstructured_grid = reader.GetOutput()

    # Convert points to NumPy array
    points_numpy = vtk_to_numpy(unstructured_grid.GetPoints().GetData())

    # Convert cells to NumPy array
    cells_numpy_with_len = vtk_to_numpy(unstructured_grid.GetCells().GetData())
    # this list contains the number of vertices per element, which we need to eliminate
    mask = np.ones(len(cells_numpy_with_len), dtype=bool)
    mask[::vtx_count] = False
    cells_numpy = cells_numpy_with_len[mask]
    return points_numpy, np.array(cells_numpy, dtype=np.int32)
