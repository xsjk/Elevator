import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from common import GUIController, Direction, ElevatorId, FloorLike


class TestGUIController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = GUIController()
        self.mock_window = MagicMock()
        self.controller.window = self.mock_window

    def test_setup_event_handlers_and_unsubscribe(self):
        with (
            patch("system.gui.gui_controller.event_bus.subscribe") as subscribe_mock,
            patch("system.gui.gui_controller.event_bus.unsubscribe") as unsubscribe_mock,
        ):
            self.controller._setup_event_handlers()
            self.assertEqual(subscribe_mock.call_count, 4)

            self.controller._unsubscribe_event_handlers()
            self.assertEqual(unsubscribe_mock.call_count, 4)

    def test_on_elevator_state_changed_updates_ui(self):
        eid: ElevatorId = 1
        floor: FloorLike = 3
        door_state = MagicMock()
        door_state.is_open.return_value = True
        direction = Direction.UP

        panel = MagicMock()
        visualizer = MagicMock()

        self.controller.window.elevator_panels = {eid: panel}
        self.controller.window.elevator_visualizer = visualizer

        self.controller._on_elevator_state_changed(eid, floor, door_state, direction)
        panel.update_elevator_status.assert_called_once()
        visualizer.update_elevator_status.assert_called_once()

    def test_on_call_completed(self):
        floor: FloorLike = 2
        direction = Direction.DOWN
        building_panel = MagicMock()
        self.controller.window.building_panel = building_panel

        self.controller._on_call_completed(floor, direction)
        building_panel.clear_call_button.assert_called_once_with(floor, direction)

    def test_on_floor_arrived(self):
        eid: ElevatorId = 1
        floor: FloorLike = 5
        panel = MagicMock()
        self.controller.window.elevator_panels = {eid: panel}

        self.controller._on_floor_arrived(floor, eid)
        panel.clear_floor_button.assert_called_once_with(str(floor))

    async def test_handle_message(self):
        self.controller.window.console_widget = MagicMock()
        self.controller.window.console_widget.log_message = MagicMock()

        with patch("system.gui.gui_controller.Controller.handle_message", new_callable=AsyncMock) as super_handler:
            await self.controller.handle_message("call E1 3")
            self.controller.window.console_widget.log_message.assert_called()
            super_handler.assert_awaited()

    async def test_reset_calls_window_reset_and_super(self):
        self.controller.window.reset = MagicMock()
        with patch("system.gui.gui_controller.Controller.reset", new_callable=AsyncMock) as super_reset:
            await self.controller.reset()
            self.controller.window.reset.assert_called_once()
            super_reset.assert_awaited()

    async def test_call_elevator_sets_button_and_calls_super(self):
        floor: FloorLike = 1
        direction = Direction.UP
        button = MagicMock()
        self.controller.window.building_panel.up_buttons = {str(floor): button}

        with patch("system.gui.gui_controller.Controller.call_elevator", new_callable=AsyncMock) as super_call:
            await self.controller.call_elevator(floor, direction)
            button.setChecked.assert_called_once_with(True)
            super_call.assert_awaited()

    async def test_select_floor(self):
        floor: FloorLike = 2
        eid: ElevatorId = 1
        button = MagicMock()
        self.controller.window.elevator_panels = {eid: MagicMock()}
        self.controller.window.elevator_panels[eid].floor_buttons = {str(floor): button}

        with patch("system.gui.gui_controller.Controller.select_floor", new_callable=AsyncMock) as super_select:
            await self.controller.select_floor(floor, eid)
            button.setChecked.assert_called_once_with(True)
            super_select.assert_awaited()

    async def test_deselect_floor(self):
        floor: FloorLike = 2
        eid: ElevatorId = 1
        button = MagicMock()
        self.controller.window.elevator_panels = {eid: MagicMock()}
        self.controller.window.elevator_panels[eid].floor_buttons = {str(floor): button}

        with patch("system.gui.gui_controller.Controller.deselect_floor", new_callable=AsyncMock) as super_deselect:
            await self.controller.deselect_floor(floor, eid)
            button.setChecked.assert_called_once_with(False)
            super_deselect.assert_awaited()

    def test_set_elevator_count(self):
        self.controller.config.elevator_count = 3
        self.controller.window.set_elevator_count = MagicMock()
        with patch("system.gui.gui_controller.Controller.set_elevator_count") as super_set:
            self.controller.set_elevator_count(5)
            self.controller.window.set_elevator_count.assert_called_once_with(5)
            super_set.assert_called_once_with(5)

            # No call when count unchanged
            self.controller.window.set_elevator_count.reset_mock()
            super_set.reset_mock()
            self.controller.config.elevator_count = 5
            self.controller.set_elevator_count(5)
            self.controller.window.set_elevator_count.assert_not_called()
            super_set.assert_not_called()


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
