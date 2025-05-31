import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from system import gui
from system.gui.gui_controller import GUIController


class GUIAsyncioTestCase(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def loop_factory():
        loop, _ = gui.setup()
        assert not loop.is_closed()
        return loop

    async def asyncSetUp(self):
        self.controller = GUIController()
        self.controller.start()
        self.window = self.controller.window
        self.building = self.window.building_panel
        self.elevator1_UI = self.window.elevator_panels[1]
        self.elevator2_UI = self.window.elevator_panels[2]
        self.elevator1 = self.controller.elevators[1]
        self.elevator2 = self.controller.elevators[2]

    async def asyncTearDown(self):
        await self.controller.stop()
        self.window.close()
