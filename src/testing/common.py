import asyncio
import re
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from system import gui
from system.core.controller import Controller
from system.core.elevator import Elevator, Elevators, TargetFloorChains, TargetFloors, logger
from system.gui import main_window
from system.gui.gui_controller import GUIController
from system.gui.main_window import ElevatorPanel
from system.gui.theme_manager import ThemeManager
from system.gui.visualizer import ElevatorVisualizer
from system.utils.common import Direction, DoorDirection, DoorState, ElevatorId, ElevatorState, Event, Floor, FloorAction, FloorLike, Strategy
from system.utils.zmq_async import Client, Server

logger.setLevel("CRITICAL")  # Suppress logging during tests


class GUIAsyncioTestCase(unittest.IsolatedAsyncioTestCase):
    loop_factory = staticmethod(gui.setup)
    if sys.version_info < (3, 13):
        raise RuntimeError("This test requires Python 3.13 or higher for loop_factory support")

    async def asyncSetUp(self):
        self.controller = GUIController()
        await self.controller.start()
        self.window = self.controller.window
        self.building = self.window.building_panel

        self.controller.set_config(
            floor_travel_duration=0.2,
            door_stay_duration=0.1,
            door_move_duration=0.1,
        )

    elevator1: Elevator
    elevator2: Elevator
    elevator1_UI: ElevatorPanel
    elevator2_UI: ElevatorPanel

    def __getattribute__(self, name: str):
        if match := re.match(r"elevator(\d+)_UI", name):
            elevator_id = int(match.group(1))
            return self.window.elevator_panels[elevator_id]
        elif match := re.match(r"elevator(\d+)", name):
            elevator_id = int(match.group(1))
            return self.controller.elevators[elevator_id]
        return super().__getattribute__(name)

    async def asyncTearDown(self):
        await self.controller.stop()
        self.window.close()


async def message_sender(server: Server, client_addr: str, queue: asyncio.Queue):
    while True:
        message = await queue.get()
        await server.send(client_addr, message)
        queue.task_done()


__all__ = [
    "GUIAsyncioTestCase",
    "message_sender",
    # Core
    "Controller",
    "Elevator",
    "Elevators",
    "TargetFloors",
    "TargetFloorChains",
    "logger",
    # GUI
    "main_window",
    "GUIController",
    "ElevatorPanel",
    "ThemeManager",
    "ElevatorVisualizer",
    # Utils
    "Direction",
    "DoorDirection",
    "DoorState",
    "Event",
    "ElevatorState",
    "ElevatorId",
    "Floor",
    "FloorAction",
    "FloorLike",
    "Strategy",
    # ZMQ
    "Client",
    "Server",
]
