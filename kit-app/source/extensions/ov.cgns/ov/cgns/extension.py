import h5py
import numpy as np
import omni.ext
import omni.cgns as ocgns
import carb


# Functions and vars are available to other extensions as usual in python: `ov.cgns.some_public_function(x)`
def some_public_function(x: int):
    print(f"[ov.cgns] some_public_function was called with {x}")
    return x**x


def return_field_array(prim):

    hdf5_fieldpath_attr = prim.GetAttribute("hdf5_field_path")
    if not hdf5_fieldpath_attr:
        raise RuntimeError(f"Couldn't open attribute: 'hdf5_field_path'")
    else:
        hdf5_fieldpath = hdf5_fieldpath_attr.Get()

    hdf5_filepath_attr = prim.GetAttribute("filepath")
    if not hdf5_filepath_attr:
        raise RuntimeError(f"Couldn't open attribute: 'filepath'")
    else:
        hdf5_filepath = hdf5_filepath_attr.Get()

    with h5py.File(hdf5_filepath, "r") as hf:
        field_array = hf[hdf5_fieldpath]
        return np.array(field_array)


def test_my_wicked_function(x):
    import h5py
    import numpy as np

    a = np.ones(10)
    b = np.ones(10)
    print("HERE!!")
    return a + b


def print_vdb_data(data):
    print(data.timestamp)
    print(data.id)
    print(data.size)
    print(data.data)

    import ctypes
    capsule = data.data
    PyCapsule_GetPointer = ctypes.pythonapi.PyCapsule_GetPointer
    PyCapsule_GetPointer.restype = ctypes.c_void_p
    PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    pointer = PyCapsule_GetPointer(capsule, None)
    if pointer:
        print(pointer)


def print_array(data):
    print(data.size)
    print(data)


def test_get_vdb_data_callback_fn(timestamp):
    carb.log_warn(f"Received VDB data '{timestamp}'...")

    icgns = ocgns.get_interface()

    vdb_data = icgns.get_vdb_data(timestamp)
    #print_vdb_data(vdb_data)

    icgns.release_vdb_data(timestamp)

def test_get_data_callback_fn(timestamp, field_name):
    carb.log_warn(f"Received data '{field_name}': '{timestamp}'...")

    icgns = ocgns.get_interface()

    data = icgns.get_data(timestamp=timestamp, field_name=field_name)
    #print_array(data)

    icgns.release_data(timestamp=timestamp, field_name=field_name)

# Any class derived from `omni.ext.IExt` in the top level module (defined in `python.modules` of `extension.toml`) will
# be instantiated when the extension gets enabled, and `on_startup(ext_id)` will be called.
# Later when the extension gets disabled on_shutdown() is called.
class MyExtension(omni.ext.IExt):
    # ext_id is the current extension id. It can be used with the extension manager to query additional information,
    # like where this extension is located on the filesystem.
    def on_startup(self, ext_id):
        print("[ov.cgns] Extension startup")

        # icgns = ocgns.get_interface()
        # icgns.register_data_callback("python_test", test_get_data_callback_fn)
        # icgns.register_vdb_callback("python_test", test_get_vdb_data_callback_fn)
        # carb.log_warn(f"Registered get data callback in CGNS plugin")

    def on_shutdown(self):
        print("[ov.cgns] Extension shutdown")
