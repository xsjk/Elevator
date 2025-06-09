import asyncio
import unittest

from common import DoorState, ElevatorState, Floor, GUIAsyncioTestCase


class SystemTestOpenDoor(GUIAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.elevator2.current_floor = 3

    async def test_open_door_by_button_and_autoclose(self):
        """UC1-a: Static press open door button -> door opens"""
        """UC2-b: Door auto-closes after stay duration if no action"""
        # User clicks open door
        self.elevator1_UI.open_door_button.click()
        self.elevator2_UI.open_door_button.click()
        await asyncio.sleep(0.02)  # Give the elevator state machine time to react        # Check if the door is open
        self.assertTrue(self.elevator1.state.is_door_open())
        self.assertTrue(self.elevator2.state.is_door_open())
        self.assertIn("Open", self.elevator1_UI.door_label.text())
        self.assertIn("Open", self.elevator2_UI.door_label.text())

        await asyncio.sleep(self.controller.config.door_stay_duration + self.controller.config.door_move_duration * 2)
        await asyncio.sleep(0.02)
        self.assertFalse(self.elevator1.state.is_door_open())
        self.assertFalse(self.elevator2.state.is_door_open())
        self.assertIn("Closed", self.elevator1_UI.door_label.text())
        self.assertIn("Closed", self.elevator2_UI.door_label.text())

    async def test_open_door_after_close_button(self):  # User clicks open door
        self.elevator1_UI.open_door_button.click()
        await asyncio.sleep(0.02)  # Give the elevator state machine time to react
        # Check if the door is open
        self.assertTrue(self.elevator1.state.is_door_open())
        self.assertIn("Open", self.elevator1_UI.door_label.text())

        await asyncio.sleep(self.controller.config.door_stay_duration + self.controller.config.door_move_duration)
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state, ElevatorState.CLOSING_DOOR)

        self.elevator1_UI.open_door_button.click()
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state, ElevatorState.OPENING_DOOR)

    async def test_open_door_on_arrival_and_autoclose(self):
        """UC1-b: Elevator arrives at target floor -> door opens automatically"""
        self.building.down_buttons["2"].click()
        await asyncio.sleep(0.02)
        await asyncio.sleep(self.controller.config.floor_travel_duration)
        await asyncio.sleep(0.02)  # Assert elevator has arrived at floor 2
        self.assertEqual(self.elevator1.current_floor, Floor("2"))
        # Door should open automatically
        self.assertEqual(self.elevator1.state, ElevatorState.OPENING_DOOR)
        self.assertIn("Open", self.elevator1_UI.door_label.text())
        await asyncio.sleep(0.02)
        await asyncio.sleep(self.controller.config.door_stay_duration + self.controller.config.door_move_duration)
        # Door should close automatically after stay duration
        self.assertEqual(self.elevator1.state, ElevatorState.CLOSING_DOOR)
        self.building.down_buttons["2"].click()

        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state, ElevatorState.OPENING_DOOR)

    async def test_close_door_by_button(self):
        """UC2-a: Manually press close door when open -> door starts closing"""
        self.assertFalse(self.elevator1.state.is_door_open())

        # Simulate clicking the "Open Door" button
        self.elevator1_UI.open_door_button.click()
        self.elevator2_UI.open_door_button.click()
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.OPENING)
        self.assertEqual(self.elevator2.state.get_door_state(), DoorState.OPENING)

        # Click the "Close Door" button
        self.elevator1_UI.close_door_button.click()
        self.elevator2_UI.close_door_button.click()
        await asyncio.sleep(0.02)
        await asyncio.sleep(self.controller.config.door_move_duration + self.controller.config.door_stay_duration)

        # Check tasks in the controller
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.CLOSING)
        self.assertEqual(self.elevator2.state.get_door_state(), DoorState.CLOSING)

    async def test_auto_close_moved(self):
        """UC2-c: Elevator moving, door keeps closed."""
        # Request elevator from 1 → 3
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.02)

        moving_duration = self.elevator1.calculate_duration(n_floors=2, n_stops=0)

        # Sample elevator status multiple times during movement
        interval = 0.2
        steps = int(moving_duration // interval) + 1
        for _ in range(steps):
            state = self.elevator1.state
            if state.is_moving():
                self.assertFalse(state.is_door_open())
            await asyncio.sleep(interval)

        # Should finally arrive at floor 3 with door open
        await asyncio.sleep(0.02)
        self.assertEqual(self.controller.elevators[1].current_floor, Floor("3"))
        self.assertTrue(self.controller.elevators[1].state.is_door_open())

    async def test_select_one_floor(self):
        """UC3-a: Select one floor inside elevator"""
        self.elevator1_UI.floor_buttons["2"].click()
        self.elevator2_UI.floor_buttons["2"].click()
        await asyncio.sleep(0.02)

        # Controller tasks should be registered
        self.assertIn("select_floor@2#1", self.controller.message_tasks)
        self.assertIn("select_floor@2#2", self.controller.message_tasks)

        # Wait for elevator operation to complete
        duration = self.elevator1.calculate_duration(n_floors=1, n_stops=0)
        await asyncio.sleep(duration)
        await asyncio.sleep(0.02)

        # Elevator should reach target floor and open door
        self.assertEqual(self.elevator1.current_floor, 2)
        self.assertEqual(self.elevator2.current_floor, 2)
        self.assertTrue(self.elevator1.state.is_door_open())
        self.assertTrue(self.elevator2.state.is_door_open())
        self.assertIn("2", self.elevator1_UI.floor_label.text())

        await asyncio.sleep(self.controller.config.door_stay_duration + self.controller.config.door_move_duration * 2)
        self.assertFalse(self.elevator1.state.is_moving())
        self.assertFalse(self.elevator2.state.is_moving())

    async def test_select_multiple_floors(self):
        """UC3-b: Select multiple floors in sequence"""
        self.elevator1_UI.floor_buttons["2"].click()
        self.elevator2_UI.floor_buttons["1"].click()
        await asyncio.sleep(0.02)
        self.elevator1_UI.floor_buttons["3"].click()
        self.elevator2_UI.floor_buttons["-1"].click()
        await asyncio.sleep(0.02)

        # Controller tasks should include two targets
        self.assertIn("select_floor@2#1", self.controller.message_tasks)
        self.assertIn("select_floor@3#1", self.controller.message_tasks)
        self.assertIn("select_floor@1#2", self.controller.message_tasks)
        self.assertIn("select_floor@-1#2", self.controller.message_tasks)

        # Wait for elevator to complete two runs
        duration = self.elevator1.calculate_duration(4, 1)
        await asyncio.sleep(duration + 1.0)

        # Elevator finally arrives
        self.assertEqual(self.elevator1.current_floor, Floor("3"))
        self.assertEqual(self.elevator2.current_floor, Floor("-1"))

    async def test_select_current_floor(self):
        """UC3-c: Select current floor (no movement, door opens)"""
        self.elevator1_UI.floor_buttons["1"].click()
        self.elevator2_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.2)

        self.assertEqual(self.elevator1.current_floor, 1)
        self.assertTrue(self.elevator1.state.is_door_open())

        self.assertEqual(self.elevator2.current_floor, 3)
        self.assertTrue(self.elevator2.state.is_door_open())

    async def test_cancel_one_of_multiple_floors(self):
        """UC4: Select two floors, cancel one"""
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.02)
        self.elevator1_UI.floor_buttons["2"].click()
        await asyncio.sleep(0.02)

        self.assertTrue(self.elevator1_UI.floor_buttons["3"].isChecked())
        self.assertTrue(self.elevator1_UI.floor_buttons["2"].isChecked())

        # Cancel one of the floors
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.02)

        # Check UI status
        self.assertFalse(self.elevator1_UI.floor_buttons["3"].isChecked())
        self.assertTrue(self.elevator1_UI.floor_buttons["2"].isChecked())

        # Wait for operation to complete, should only go to floor 2
        await asyncio.sleep(self.elevator1.calculate_duration(1, 0) + 0.5)
        self.assertEqual(self.elevator1.current_floor, Floor("2"))

    async def test_call_elevator_up_button(self):
        """UC5: Press 'up' button on floor 2 → elevator 1 responds and door opens"""
        # User presses "up" button on floor 2
        self.building.up_buttons["2"].click()
        await asyncio.sleep(0.02)

        # Controller tasks should include this request
        self.assertIn("call_up@2", self.controller.message_tasks)

        # Wait for elevator 1 to reach target floor
        move_duration = self.elevator1.calculate_duration(n_floors=1, n_stops=0)
        await asyncio.sleep(move_duration + 0.5)

        # Elevator should be at target floor
        self.assertEqual(self.elevator1.current_floor, 2)

        # Floor label should be correct
        self.assertIn("2", self.window.elevator_panels[1].floor_label.text())

    async def test_display_info_inside_and_outside(self):
        """UC6: Comprehensive UI display verification during elevator run"""
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.02)

        # UC6-a: Floor 3 button should light up
        self.assertTrue(self.elevator1_UI.floor_buttons["3"].isChecked(), "Floor 3 button should be checked")

        # Check elevator information display during operation
        move_duration = self.elevator1.calculate_duration(2, 1)
        sample_interval = 0.3
        steps = int(move_duration / sample_interval)

        for _ in range(steps):
            state = self.controller.elevators[1].state
            current_floor = self.controller.elevators[1].current_floor  # UC6-b: Current floor display update
            self.assertIn(str(current_floor), self.elevator1_UI.floor_label.text())
            # UC6-c: Door should be closed
            if state.is_moving():
                self.assertIn("Closed", self.elevator1_UI.door_label.text())

                # UC6-d: Display direction (UP / DOWN)
                dir_text = self.elevator1_UI.direction_label.text()
                self.assertIn("UP", dir_text.upper())
            else:
                dir_text = self.elevator1_UI.direction_label.text()
                self.assertIn("IDLE", dir_text.upper())

            await asyncio.sleep(sample_interval)

        # After reaching target floor:
        await asyncio.sleep(0.02)

        # UC6-a: Button should be unchecked
        self.assertFalse(self.elevator1_UI.floor_buttons["3"].isChecked())

        # UC6-b/c: Floor should be 3, door should be Open
        self.assertEqual(self.elevator1.current_floor, Floor("3"))
        self.assertIn("3", self.elevator1_UI.floor_label.text())

        # UC6-e: External button should respond to arrival
        # User presses external button (simulating someone calling)
        self.building.down_buttons["2"].click()
        await asyncio.sleep(0.02)

        # External button should light up (isChecked)
        self.assertTrue(self.building.down_buttons["2"].isChecked())

        # After elevator completes door opening, button should turn off
        await asyncio.sleep(self.controller.config.floor_travel_duration + self.controller.config.door_stay_duration)
        await asyncio.sleep(0.02)
        self.assertFalse(self.building.down_buttons["2"].isChecked())

    async def test_multiple_calls_outside(self):
        """EM1: Multiple floors press external call buttons → elevators dispatched correctly"""

        # Press multiple external buttons
        self.building.down_buttons["2"].click()
        self.building.up_buttons["2"].click()
        await asyncio.sleep(0.02)

        # System should record multiple tasks
        self.assertIn("call_down@2", self.controller.message_tasks)
        self.assertIn("call_up@2", self.controller.message_tasks)

        # Wait for elevator response and operation
        await asyncio.sleep(self.elevator1.calculate_duration(1, 0))
        await asyncio.sleep(0.02)

        # Elevator 2 should reach floor 3, door should open
        await asyncio.sleep(0.02)
        self.assertEqual(self.elevator2.current_floor, Floor("2"))
        self.assertTrue(self.elevator2.state.is_door_open())

        # Elevator 1 should reach floor 2
        self.assertEqual(self.elevator1.current_floor, Floor("2"))
        self.assertTrue(self.elevator1.state.is_door_open())

    async def test_dispatch_efficiency(self):
        """EM2: Efficient elevator assignment - nearest elevator handles the call"""
        self.elevator1.current_floor = Floor("-1")
        self.elevator1_UI.update_elevator_status(self.elevator2.current_floor, self.elevator2.state.get_door_state(), self.elevator2.state.get_moving_direction())

        # Simulate pressing up button on floor 2 (closer to elevator 2)
        self.window.building_panel.up_buttons["2"].click()
        await asyncio.sleep(0.02)

        # Record elevator position, wait for response
        await asyncio.sleep(self.elevator1.calculate_duration(1, 0))
        await asyncio.sleep(0.02)

        # Elevator 2 should respond to the request
        self.assertEqual(self.elevator2.current_floor, Floor("2"))
        self.assertTrue(self.elevator2.state.is_door_open())

        # Elevator 1 should not move
        self.assertEqual(self.elevator1.current_floor, Floor("-1"))


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
