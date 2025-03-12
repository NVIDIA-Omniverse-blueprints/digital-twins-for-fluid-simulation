import sys
import numpy as np
import os

from pathlib import Path


DO_NOT_LOAD_FIELDS = ['bounding_box_dims', 'stream_velocity', 'surface_coordinates', 'surface_pressure']


class FileInference():
    data = {}
    arrays = {}
    filepath = ""
    extension = ""

    def __init__(self, filepath):
        if not os.path.exists(filepath):
            raise RuntimeError(f"ERROR: The file '{filepath}' does not exist")

        self.filepath = filepath
        self.extension = Path(self.filepath).suffix

    @staticmethod
    def get_filepath(files_info, file_index):
        '''Get filepath the data will be read from'''

        if not files_info['filepath']:
            raise RuntimeError("No filepath set")

        filename = files_info['filepath']
        from_file = files_info['from']
        to_file = files_info['to']

        file_index = from_file if file_index < 0 else file_index
        filepath = filename if from_file == to_file else filename % (file_index)
        return filepath

    def load_data(self):
        print(f"Loading data from '{self.filepath}'...")

        if self.extension == '.npz':
            self.data = np.load(self.filepath, allow_pickle=True)
        elif self.extension == '.npy':
            data = np.load(self.filepath, allow_pickle=True)
            self.data = data.item()

    def get_data(self):
        return self.data

    def get_field_names(self):
        field_names = []

        if self.extension == '.npz':
            data = np.load(self.filepath, allow_pickle=True)
            field_names = data.files

        elif self.extension == '.npy':
            data = np.load(self.filepath, allow_pickle=True)
            data = data.item()
            for key, _ in data.items():
                if key not in DO_NOT_LOAD_FIELDS:
                    field_names.append(key)

        return field_names


if __name__ == "__main__":
    if len(sys.argv) == 2:
        file_inference = FileInference(sys.argv[1])
        file_dict = file_inference.get_data()
