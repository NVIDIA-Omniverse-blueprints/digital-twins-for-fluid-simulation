import sys

import h5py
import numpy as np
from pxr import Sdf, Usd, UsdGeom, UsdVol


def open_stage(stage_url):

    stage = Usd.Stage.Open(stage_url)
    if not stage:
        print(f"Couldn't open stage: {stage_url}")
        sys.exit(1)

    return stage


def return_array(prim, attribute="hdf5_field_path"):

    hdf5_fieldpath_attr = prim.GetAttribute(attribute)
    if not hdf5_fieldpath_attr:
        print("Hello")
        raise RuntimeError(f"Couldn't open attribute: '{attribute}'")
    else:
        hdf5_fieldpath = hdf5_fieldpath_attr.Get()

    hdf5_filepath_attr = prim.GetAttribute("cgnsFilePath")
    if not hdf5_filepath_attr:
        raise RuntimeError(f"Couldn't open attribute: 'cgnsFilePath'")
    else:
        hdf5_filepath = hdf5_filepath_attr.Get()

    with h5py.File(hdf5_filepath, "r") as hf:
        field_array = hf[hdf5_fieldpath]
        return np.array(field_array)


def return_field_array(prim):
    return return_array(prim, attribute="fieldHdf5Path")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Open USDA file and load hdf5 arrays")
    parser.add_argument("usda_file", help="USDA file to open")
    args = parser.parse_args()
    stage = open_stage(args.usda_file)
    prim = stage.GetPrimAtPath("/World/Zone1/Pressure")
    if not prim:
        print("ERROR: Couldn't open prim '/World/Zone1/Pressure'")
        sys.exit(1)
    array = return_field_array("data/yf17_hdf5.cgns", prim)
    print("Array looks like: ", array)
