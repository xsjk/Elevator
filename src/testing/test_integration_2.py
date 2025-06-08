import asyncio
import unittest

from common import ElevatorState, Floor, GUIAsyncioTestCase


class ElevatorTest(GUIAsyncioTestCase):
    async def test_complex_sequence_integration(self):
        # Step 1: press down button on floor 2 (external)
        self.building.down_buttons["2"].click()
        await asyncio.sleep(0.02)
        self.assertIn("call_down@2", self.controller.message_tasks)

        cfg = self.controller.config

        # Step 2: wait elevator arrives, then simulate open door just before it closes
        travel_time = self.elevator1.calculate_duration(n_floors=1, n_stops=0)
        await asyncio.sleep(travel_time)
        await asyncio.sleep(0.02)
        await asyncio.sleep(cfg.door_move_duration)
        await asyncio.sleep(0.02)
        await asyncio.sleep(cfg.door_stay_duration)

        self.assertEqual(self.elevator1.current_floor, Floor(2))
        self.assertEqual(self.elevator2.current_floor, Floor(1))
        self.assertEqual(self.elevator1.state, ElevatorState.CLOSING_DOOR)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_CLOSED)

        await asyncio.sleep(cfg.door_move_duration / 2)
        self.elevator1_UI.open_door_button.click()
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state, ElevatorState.OPENING_DOOR)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_CLOSED)
        await asyncio.sleep(0.02)

        await asyncio.sleep(cfg.door_move_duration / 2)
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state, ElevatorState.STOPPED_DOOR_OPENED)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_CLOSED)

        # Step 3: press floor -1, then floor 3
        self.elevator1_UI.floor_buttons["-1"].click()
        await asyncio.sleep(0.02)
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.02)

        self.assertIn("select_floor@-1#1", self.controller.message_tasks)
        self.assertIn("select_floor@3#1", self.controller.message_tasks)

        await asyncio.sleep(cfg.door_stay_duration + cfg.door_move_duration)

        # Step 4: wait elevator reaches -1, then press up button on floor 2
        travel = self.elevator1.calculate_duration(n_floors=2, n_stops=0)
        await asyncio.sleep(travel)

        self.assertEqual(self.elevator1.current_floor, Floor(-1))
        self.assertEqual(self.elevator2.current_floor, Floor(1))
        self.assertEqual(self.elevator1.state, ElevatorState.OPENING_DOOR)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_CLOSED)

        await asyncio.sleep(cfg.door_move_duration)
        await asyncio.sleep(0.02)

        self.assertEqual(self.elevator1.state, ElevatorState.STOPPED_DOOR_OPENED)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_CLOSED)

        self.building.up_buttons["2"].click()
        await asyncio.sleep(0.02)
        self.assertIn("call_up@2", self.controller.message_tasks)
        await asyncio.sleep(0.02)

        # Step 5: door is open, press close door button
        await asyncio.sleep(cfg.floor_travel_duration)
        self.assertEqual(self.elevator2.current_floor, Floor(2))
        self.assertEqual(self.elevator2.state, ElevatorState.OPENING_DOOR)

        await asyncio.sleep(cfg.door_move_duration)
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_OPENED)

        self.elevator2_UI.close_door_button.click()
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator2.state, ElevatorState.CLOSING_DOOR)

        await asyncio.sleep(cfg.door_move_duration)
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator2.state, ElevatorState.STOPPED_DOOR_CLOSED)


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
