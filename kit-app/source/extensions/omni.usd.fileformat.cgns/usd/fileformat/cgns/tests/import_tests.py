# NOTE:
#   omni.kit.test - std python's unittest module with additional wrapping to add suport for async/await tests
#   For most things refer to unittest docs: https://docs.python.org/3/library/unittest.html
import os
import unittest

# Import extension python module we are testing with absolute import path, as if we are external user (other extension)
from pathlib import Path

import omni.kit.test
import omni.usd


# Having a test class dervived from omni.kit.test.AsyncTestCase declared on the root of module will make it auto-discoverable by omni.kit.test
class Test(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    async def test_file_format(self):
        from pxr import Sdf

        file_format = Sdf.FileFormat.FindById("cgns")
        self.assertTrue(file_format)

    async def test_open(self):
        current_path = Path(__file__).parent
        data_path = current_path.parent.parent.parent.parent.joinpath("data")
        test_data_path = str(data_path.joinpath("tut21.cgns"))
        self.assertTrue(os.path.exists(test_data_path))

        context = omni.usd.get_context()
        await context.open_stage_async(test_data_path)

        stage = context.get_stage()
        self.assertTrue(stage)

        volume_prim = stage.GetPrimAtPath("/World/Zone1")
        self.assertTrue(volume_prim)
