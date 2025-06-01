import asyncio
import inspect
import logging

from ..core.controller import Config, Controller, Floor
from ..utils.common import Direction, DoorState, ElevatorId, Event, FloorLike
from ..utils.event_bus import event_bus
from .main_window import MainWindow
from .visualizer import ElevatorVisualizer
from ..core.elevator import Elevator

logger = logging.getLogger(__name__)


class GUIController(Controller):
    """
    Extended elevator controller that integrates with the GUI
    Handles logging of commands to the console
    """

    def __init__(self, config: Config = Config(), headless: bool = False):
        super().__init__(config)
        self.headless = headless

    def _setup_event_handlers(self):
        """Set up event handlers for elevator state changes"""
        event_bus.subscribe(Event.ELEVATOR_STATE_CHANGED, self._on_elevator_state_changed)
        event_bus.subscribe(Event.ELEVATOR_FLOOR_CHANGED, self._on_elevator_state_changed)
        event_bus.subscribe(Event.CALL_COMPLETED, self._on_call_completed)
        event_bus.subscribe(Event.FLOOR_ARRIVED, self._on_floor_arrived)

    def _unsubscribe_event_handlers(self):
        """Unsubscribe from event handlers to prevent memory leaks"""
        event_bus.unsubscribe(Event.ELEVATOR_STATE_CHANGED, self._on_elevator_state_changed)
        event_bus.unsubscribe(Event.ELEVATOR_FLOOR_CHANGED, self._on_elevator_state_changed)
        event_bus.unsubscribe(Event.CALL_COMPLETED, self._on_call_completed)
        event_bus.unsubscribe(Event.FLOOR_ARRIVED, self._on_floor_arrived)

    def _on_elevator_state_changed(self, elevator_id: ElevatorId, floor: FloorLike, door_state: DoorState, direction: Direction):
        """Handle elevator state change events"""
        try:
            self.window.elevator_panels[elevator_id].update_elevator_status(floor, door_state, direction)
            # Update parent window's visualizer if available
            if hasattr(self.window, "elevator_visualizer"):
                self.window.elevator_visualizer.update_elevator_status(elevator_id, floor, door_open=door_state.is_open(), direction=direction)

            logging.debug(f"Updated UI for elevator {elevator_id}: floor={floor}, door={door_state}, direction={direction}")
        except Exception as e:
            logging.error(f"Error updating elevator UI: {e}")
            raise e

    def _on_call_completed(self, floor: FloorLike, direction: Direction):
        floor = Floor(floor)
        self.window.building_panel.clear_call_button(floor, direction)

    def _on_floor_arrived(self, floor: FloorLike, elevator_id: ElevatorId):
        floor = Floor(floor)
        self.window.elevator_panels[elevator_id].clear_floor_button(str(floor))

    async def _update_position(self):
        v = self.window.elevator_visualizer
        try:
            while True:
                await asyncio.sleep(0.02)

                for eid, elevator in self.elevators.items():
                    self._update_elevator_status(v, eid, elevator)

                v.update()
        except asyncio.CancelledError:
            logger.debug("Position update loop cancelled")
            pass

    def _update_elevator_status(self, visualizer: ElevatorVisualizer, elevator_id: ElevatorId, elevator: Elevator):
        """Helper method to update elevator status in the visualizer."""
        if elevator_id in visualizer.elevator_status:
            visualizer.elevator_status[elevator_id]["current_position"] = visualizer.FLOOR_HEIGHT * (len(self.config.floors) - elevator.current_position - 1)
            visualizer.elevator_status[elevator_id]["door_percentage"] = elevator.door_position_percentage
        else:
            logger.warning(f"Elevator {elevator_id} not found in visualizer status")

    async def handle_message(self, message: str):
        """
        Handle incoming messages and log them to the console
        Then delegate to the parent class for actual processing
        """
        # Using QCoreApplication.translate for translation
        self.window.console_widget.log_message(f"🡒 {message}")
        logging.info(f"Processing command: {message}")

        # Call parent class handler
        await super().handle_message(message)

    def start(self, tg: asyncio.TaskGroup | asyncio.AbstractEventLoop | None = None):
        if not hasattr(self, "window"):
            self.window = MainWindow(self)

        if self.headless:
            self.window.hide()
        else:
            self.window.show()

        # Subscribe to elevator events
        self._setup_event_handlers()

        super().start(tg)
        self.update_position_task = (tg if tg else asyncio).create_task(self._update_position(), name=f"UpdatePositionLoop {__file__}:{inspect.stack()[0].lineno}")

    async def stop(self):
        """
        Stop the GUI controller and clean up resources
        """

        if hasattr(self, "update_position_task") and not self.update_position_task.done():
            self.update_position_task.cancel()
            await self.update_position_task
        await super().stop()

        # Unsubscribe from event handlers to prevent memory leaks
        self._unsubscribe_event_handlers()

    async def reset(self):
        self.window.reset()
        await super().reset()

    async def call_elevator(self, call_floor: FloorLike, call_direction: Direction):
        call_floor = Floor(call_floor)
        match call_direction:
            case Direction.UP:
                self.window.building_panel.up_buttons[str(call_floor)].setChecked(True)
            case Direction.DOWN:
                self.window.building_panel.down_buttons[str(call_floor)].setChecked(True)
            case _:
                raise ValueError(f"Invalid call direction: {call_direction}")

        return await super().call_elevator(call_floor, call_direction)

    async def select_floor(self, floor: FloorLike, elevator_id: ElevatorId):
        floor = Floor(floor)
        self.window.elevator_panels[elevator_id].floor_buttons[str(floor)].setChecked(True)
        return await super().select_floor(floor, elevator_id)

    async def deselect_floor(self, floor: FloorLike, elevator_id: ElevatorId):
        floor = Floor(floor)
        self.window.elevator_panels[elevator_id].floor_buttons[str(floor)].setChecked(False)
        return await super().deselect_floor(floor, elevator_id)

    def set_elevator_count(self, count: int):
        if self.config.elevator_count == count:
            return

        self.window.set_elevator_count(count)
        super().set_elevator_count(count)

    async def get_event_message(self) -> str:
        msg = await super().get_event_message()
        self.window.console_widget.log_message(f"🡐 {msg}")
        return msg
