import asyncio
import logging

from PySide6.QtCore import QCoreApplication

from controller import Config, Controller, Floor
from gui.main_window import MainWindow
from utils.common import Direction, DoorState, ElevatorId, Event
from utils.event_bus import event_bus

logger = logging.getLogger(__name__)


class GUIController(Controller):
    """
    Extended elevator controller that integrates with the GUI
    Handles logging of commands to the console
    """

    def __init__(self, main_window: MainWindow | None = None):
        super().__init__(Config())
        self.main_window = main_window

        # Subscribe to elevator events
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Set up event handlers for elevator state changes"""
        event_bus.subscribe(Event.ELEVATOR_STATE_CHANGED, self._on_elevator_state_changed)
        event_bus.subscribe(Event.ELEVATOR_FLOOR_CHANGED, self._on_elevator_state_changed)
        event_bus.subscribe(Event.CALL_COMPLETED, self._on_call_completed)
        event_bus.subscribe(Event.FLOOR_ARRIVED, self._on_floor_arrived)

    def _on_elevator_state_changed(self, elevator_id: ElevatorId, floor: Floor, door_state: DoorState, direction: Direction):
        """Handle elevator state change events"""
        if not self.main_window:
            return

        try:
            self.main_window.elevator_panels[elevator_id].update_elevator_status(floor, door_state, direction)
            # Update parent window's visualizer if available
            if hasattr(self.main_window, "elevator_visualizer"):
                self.main_window.elevator_visualizer.update_elevator_status(elevator_id, floor, door_open=door_state.is_open(), direction=direction)

            logging.debug(f"Updated UI for elevator {elevator_id}: floor={floor}, door={door_state}, direction={direction}")
        except Exception as e:
            logging.error(f"Error updating elevator UI: {e}")
            raise e

    def _on_call_completed(self, floor: Floor, direction: Direction):
        if self.main_window:
            self.main_window.building_panel.clear_call_button(floor, direction)

    def _on_floor_arrived(self, floor: Floor, elevator_id: ElevatorId):
        if self.main_window:
            self.main_window.elevator_panels[elevator_id].clear_floor_button(str(floor))

    async def _update_position(self):
        assert self.main_window is not None
        v = self.main_window.elevator_visualizer
        while True:
            await asyncio.sleep(0.02)

            for eid, elevator in self.elevators.items():
                v.elevators[eid]["current_position"] = v.FLOOR_HEIGHT * (len(self.config.floors) - elevator.current_position - 1)
                v.elevators[eid]["door_percentage"] = elevator.door_position_percentage

            v.update()

    def set_main_window(self, main_window: MainWindow):
        """Set the main window reference for UI updates"""
        self.main_window = main_window

        # Initialize UI with current elevator states
        for elevator_id, elevator in self.elevators.items():
            self._on_elevator_state_changed(elevator_id, elevator.current_floor, elevator.door_state, elevator.commited_direction)

    async def handle_message(self, message: str):
        """
        Handle incoming messages and log them to the console
        Then delegate to the parent class for actual processing
        """
        # Log message to console
        if self.main_window:
            # Using QCoreApplication.translate for translation
            translated_text = QCoreApplication.translate("Console", "Processing command:")
            self.main_window.console_widget.log_message(f"{translated_text} {message}")
            logging.info(f"Processing command: {message}")

        # Call parent class handler
        await super().handle_message(message)

    async def control_loop(self):
        asyncio.create_task(self._update_position())
        return await super().control_loop()

    def reset(self):
        super().reset()
        if self.main_window:
            self.main_window.reset()
