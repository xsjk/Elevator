import asyncio
import unittest

from common import DoorState, Floor, GUIAsyncioTestCase


class ElevatorUITest(GUIAsyncioTestCase):
    async def test_open_door_button(self):
        """Test the internal open door button of Elevator 1."""
        self.assertFalse(self.elevator1.state.is_door_open())

        # Simulate clicking the "Open Door" button
        self.elevator1_UI.open_door_button.click()

        self.assertIn("open_door#1", self.controller.message_tasks)

        await asyncio.sleep(0.02)
        self.assertTrue(self.elevator1.state.is_door_open())  # Door is opening or opened
        self.assertIn("开", self.elevator1_UI.door_label.text())

        await asyncio.sleep(self.elevator1.door_move_duration * 2 + self.elevator1.door_stay_duration)
        await asyncio.sleep(self.elevator1.door_move_duration / 2)
        self.assertFalse(self.elevator1.state.is_door_open())
        self.assertIn("关", self.elevator1_UI.door_label.text())

    async def test_close_door_button(self):
        """Test the internal close door button of Elevator 1."""
        self.assertFalse(self.elevator1.state.is_door_open())

        # Simulate clicking the "Open Door" button
        self.elevator1_UI.open_door_button.click()
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.OPENING)

        # Click the "Close Door" button
        self.elevator1_UI.close_door_button.click()
        await asyncio.sleep(self.elevator1.door_move_duration + self.elevator1.door_stay_duration)
        await asyncio.sleep(0.02)

        # Check tasks in the controller
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.CLOSING)

    async def test_select_floor_and_move(self):
        """Test selecting a floor button triggers elevator movement."""
        target_floor_up = Floor("3")

        # Simulate clicking the internal floor button (floor 3 button)
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.02)  # Wait for the controller to start the task

        # Controller should receive the command
        self.assertIn("select_floor@3#1", self.controller.message_tasks)
        # Floor button should be checked
        self.assertTrue(self.elevator1_UI.floor_buttons["3"].isChecked())

        # Wait for elevator movement to complete (including acceleration, travel, and door opening)
        duration = self.elevator1.calculate_duration(
            n_floors=2,  # From floor 1 to floor 3
            n_stops=0,
        )
        await asyncio.sleep(duration)
        await asyncio.sleep(0.02)

        # Elevator should reach the target floor
        self.assertEqual(self.elevator1.current_floor, target_floor_up)
        # Floor indicator in UI should change to 3
        self.assertIn("3", self.elevator1_UI.floor_label.text())
        # Button should be unchecked
        self.assertFalse(self.elevator1_UI.floor_buttons["3"].isChecked())


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
