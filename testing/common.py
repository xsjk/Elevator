import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from system import gui
from system.core.controller import Controller
from system.core.elevator import Elevator, TargetFloorChains, logger
from system.gui.gui_controller import GUIController
from system.utils.common import Direction, DoorDirection, DoorState, ElevatorId, ElevatorState, Event, Floor, FloorAction, FloorLike

logger.setLevel("CRITICAL")  # Suppress logging during tests


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


__all__ = [
    "GUIAsyncioTestCase",
    "Controller",
    "Elevator",
    "TargetFloorChains",
    "logger",
    "GUIController",
    "Direction",
    "DoorDirection",
    "DoorState",
    "Event",
    "ElevatorState",
    "ElevatorId",
    "Floor",
    "FloorAction",
    "FloorLike",
]
