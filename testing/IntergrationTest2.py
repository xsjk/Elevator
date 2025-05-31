import asyncio
import os
import sys
import unittest

from common import GUIAsyncioTestCase

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from system.utils.common import ElevatorState, Floor


class ElevatorTest(GUIAsyncioTestCase):
    async def test_complex_sequence_integration(self):
        # Step 1: press down button on floor 2 (external)
        self.building.down_buttons["2"].click()
        await asyncio.sleep(0.1)
        self.assertIn("call_down@2", self.controller.message_tasks)

        # Step 2: wait elevator arrives, then simulate open door just before it closes
        travel_time = self.controller.calculate_duration(n_floors=1, n_stops=0)
        await asyncio.sleep(travel_time + self.controller.config.door_stay_duration + self.controller.config.door_move_duration)

        self.assertEqual(self.elevator1.current_floor, 2)
        self.assertEqual(self.elevator1.state, ElevatorState.CLOSING_DOOR)

        self.elevator1_UI.open_door_button.click()
        await asyncio.sleep(0.5)
        # self.assertIn("open_door#1", self.controller.message_tasks)
        self.assertIn(self.elevator1.state, [ElevatorState.OPENING_DOOR, ElevatorState.STOPPED_DOOR_OPENED])

        # Step 3: press floor -1, then floor 3
        self.elevator1_UI.floor_buttons["-1"].click()
        await asyncio.sleep(0.1)
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.1)

        self.assertIn("select_floor@-1#1", self.controller.message_tasks)
        self.assertIn("select_floor@3#1", self.controller.message_tasks)

        # Step 4: wait elevator reaches -1, then press up button on floor 2
        # 估计 -1 到达时间
        travel = self.controller.calculate_duration(n_floors=2, n_stops=0)
        await asyncio.sleep(travel + 5.0)

        self.assertEqual(self.elevator1.current_floor, Floor("-1"))

        self.building.up_buttons["2"].click()
        await asyncio.sleep(0.1)
        self.assertIn("call_up@2", self.controller.message_tasks)

        # Step 5: door is open, press close door button
        await asyncio.sleep(travel_time + self.controller.config.door_move_duration)
        self.assertEqual(self.elevator2.current_floor, Floor("2"))
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_OPENED)

        self.elevator2_UI.close_door_button.click()
        await asyncio.sleep(0.5)

        # self.assertIn("close_door#1", self.controller.message_tasks)

        # 最终确认状态
        self.assertEqual(self.elevator2.state, ElevatorState.CLOSING_DOOR)


if __name__ == "__main__":
    unittest.main()
