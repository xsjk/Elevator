import logging

from PySide6.QtCore import QCoreApplication

from core import ElevatorController, ElevatorControllerConfig, Floor
from gui.main_window import MainWindow
from utils.common import Direction, DoorState, ElevatorId, Event
from utils.event_bus import event_bus

logger = logging.getLogger(__name__)


class GUIElevatorController(ElevatorController):
    """
    Extended elevator controller that integrates with the GUI
    Handles logging of commands to the console
    """

    def __init__(self, client, main_window: MainWindow = None):
        super().__init__(client, ElevatorControllerConfig())
        self.main_window = main_window

        # Subscribe to elevator events
        self._setup_event_handlers()

    def __del__(self):
        # Unsubscribe from elevator events
        self._unsubscribe_event_handlers()

    def _setup_event_handlers(self):
        """Set up event handlers for elevator state changes"""
        event_bus.subscribe(Event.ELEVATOR_STATE_CHANGED, self._on_elevator_state_changed)
        event_bus.subscribe(Event.ELEVATOR_FLOOR_CHANGED, self._on_elevator_state_changed)

    def _unsubscribe_event_handlers(self):
        """Unsubscribe from elevator events"""
        event_bus.unsubscribe(Event.ELEVATOR_STATE_CHANGED, self._on_elevator_state_changed)
        event_bus.unsubscribe(Event.ELEVATOR_FLOOR_CHANGED, self._on_elevator_state_changed)

    def _on_elevator_state_changed(self, elevator_id: ElevatorId, floor: Floor, door_state: DoorState, direction: Direction):
        """Handle elevator state change events"""
        if not self.main_window:
            return

        try:
            if elevator_id == 1:
                self.main_window.elevator_panels[0].update_elevator_status(floor, door_state, direction)
            elif elevator_id == 2:
                self.main_window.elevator_panels[1].update_elevator_status(floor, door_state, direction)

            # Update parent window's visualizer if available
            if hasattr(self.main_window, "elevator_visualizer"):
                self.main_window.elevator_visualizer.update_elevator_status(elevator_id, floor, door_open=door_state.is_open(), direction=direction)

            logging.debug(f"Updated UI for elevator {elevator_id}: floor={floor}, door={door_state}, direction={direction}")
        except Exception as e:
            logging.error(f"Error updating elevator UI: {e}")
            raise e

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
