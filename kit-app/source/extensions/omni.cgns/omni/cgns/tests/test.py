import numpy

import omni.kit.test
import omni.cgns


class Test(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        pass

    # After running each test
    async def tearDown(self):
        pass

    # Actual test, notice it is "async" function, so "await" can be used if needed
    async def testInterface(self):
        icgns = omni.cgns.get_interface()
        print(dir(icgns))
