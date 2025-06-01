import logging
from collections import OrderedDict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame

from ..utils.common import Direction, ElevatorId, Floor, FloorLike


class ElevatorVisualizer(QFrame):
    """
    2D visualization of elevator movement
    Shows real-time position and status of elevators in the building
    Supports dynamic number of elevators based on configuration
    """

    # Floor heights in pixels
    FLOOR_HEIGHT = 80
    # Building dimensions
    ELEVATOR_WIDTH = 60
    ELEVATOR_HEIGHT = 70
    # Horizontal spacing between elevators
    ELEVATOR_SPACING = 40

    def __init__(self, floors: list[Floor], elevator_count: int):
        """Initialize the elevator visualizer

        Args:
            floors: List of Floor objects representing building floors
            elevator_count: Number of elevators to display (used when elevators is None)
        """

        for floor in floors:
            assert isinstance(floor, Floor), f"Invalid floor type: {type(floor)}. Expected Floor instance."
        assert elevator_count > 0, "Elevator count must be greater than 0"

        super().__init__()

        # Set minimum size
        self.setMinimumHeight(400)
        self.setMinimumWidth(400)

        # Set frame style
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        # Floor configuration (from bottom to top)
        # Changed order to ensure -1 is at the bottom, followed by 1, 2, 3
        self.floors = floors
        self.floors.sort()

        self.floor_positions = self._calculate_floor_positions()

        # Elevator configuration - create elevators dynamically based on elevator_count
        self.elevator_status = OrderedDict()
        self.set_elevator_count(elevator_count)

        # Cache for drawing calculations
        self._cached_dimensions = None
        self._last_widget_size = (0, 0)

        # Subscribe to position updates
        # event_bus.subscribe(Event.ELEVATOR_UPDATED, self._on_elevator_position_updated)

        # Cache theme colors
        self._update_theme_colors()

    def set_elevator_count(self, count: int):
        if count < len(self.elevator_status):
            # Remove excess elevators
            for eid in list(self.elevator_status.keys())[count:]:
                del self.elevator_status[eid]
        elif count > len(self.elevator_status):
            # Add new elevators
            for i in range(len(self.elevator_status) + 1, count + 1):
                self.elevator_status[i] = {
                    "current_floor": "1",  # Start at ground floor
                    "current_position": 1.0,  # Start position at ground floor
                    "door_open": False,
                    "direction": "idle",  # Initial direction
                }

    def _update_theme_colors(self):
        """Retrieve current palette colors to adapt to system theme"""
        palette = self.palette()

        # Basic colors
        self.text_color = palette.color(QPalette.ColorRole.Text)
        self.window_text_color = palette.color(QPalette.ColorRole.WindowText)
        self.background_color = palette.color(QPalette.ColorRole.Window)
        self.dark_color = palette.color(QPalette.ColorRole.Dark)
        self.light_color = palette.color(QPalette.ColorRole.Light)
        self.mid_color = palette.color(QPalette.ColorRole.Mid)
        self.floor_line_color = palette.color(QPalette.ColorRole.Dark)

        # Special colors (direction indicators)
        is_dark_mode = self.background_color.lightness() < 128

        if is_dark_mode:
            # Use brighter colors for dark mode
            self.up_color = QColor(0, 255, 100)  # Bright green
            self.down_color = QColor(255, 100, 100)  # Bright red
            self.idle_color = QColor(150, 150, 150)  # Bright gray
            self.door_color = QColor(220, 220, 220)  # Bright white
            self.door_open_color = QColor(80, 80, 80)  # Dark gray
        else:
            # Use standard colors for light mode
            self.up_color = QColor(0, 200, 0)  # Green
            self.down_color = QColor(200, 0, 0)  # Red
            self.idle_color = QColor(100, 100, 100)  # Gray
            self.door_color = QColor(200, 200, 200)  # Light gray
            self.door_open_color = QColor(50, 50, 50)  # Dark gray

    def changeEvent(self, event):
        """Called when a window event occurs, including palette changes"""
        if event.type() == event.Type.PaletteChange:
            # Update colors when the palette changes (e.g., switching to dark mode)
            self._update_theme_colors()
            self.update()  # Trigger repaint
        super().changeEvent(event)

    def _calculate_floor_positions(self):
        """Calculate y-coordinates for each floor"""
        positions = {}
        # Calculate position from bottom to top
        total_height = len(self.floors) * self.FLOOR_HEIGHT
        for i, floor in enumerate(self.floors):
            # Position is measured from the top of the widget
            positions[floor] = total_height - (i + 1) * self.FLOOR_HEIGHT

        return positions

    def update_elevator_status(self, elevator_id: ElevatorId, floor: FloorLike, door_open: bool, direction: Direction):
        floor = Floor(floor)
        """Update the state of an elevator"""
        if elevator_id not in self.elevator_status:
            logging.warning(f"Invalid elevator ID: {elevator_id}")
            return

        # Log state change for debugging
        logging.debug(f"Updating elevator {elevator_id} visualization: floor={floor}, door_open={door_open}, direction={direction}")

        # Update elevator state
        self.elevator_status[elevator_id]["current_floor"] = floor
        self.elevator_status[elevator_id]["door_open"] = door_open
        self.elevator_status[elevator_id]["direction"] = direction

        # Update position directly
        if floor in self.floor_positions:
            self.elevator_status[elevator_id]["current_position"] = self.floor_positions[floor]
            logging.debug(f"Set elevator {elevator_id} position to {self.floor_positions[floor]} for floor {floor}")
        else:
            logging.warning(f"Floor {floor} not found in floor positions map. Available floors: {list(self.floor_positions.keys())}")

        # Request repaint
        self.update()

    def _update_drawing_cache(self, widget_width, widget_height):
        """Update cached drawing calculations when widget size or elevator count changes"""
        current_size = (widget_width, widget_height)
        if self._cached_dimensions is None or self._last_widget_size != current_size or len(self.elevator_status) != self._last_elevator_count:
            building_width = self.BUILDING_WIDTH
            building_height = self.BUILDING_HEIGHT

            # Calculate building position (centered)
            building_x = (widget_width - building_width) / 2
            building_y = (widget_height - building_height + self.FLOOR_HEIGHT - self.ELEVATOR_HEIGHT) / 2

            # Calculate elevator positioning
            total_elevator_width = len(self.elevator_status) * self.ELEVATOR_WIDTH + (len(self.elevator_status) - 1) * self.ELEVATOR_SPACING
            elevator_start_x = building_x + (building_width - total_elevator_width) / 2

            # Calculate floor y positions
            floor_y_positions = {}
            total_height = len(self.floors) * self.FLOOR_HEIGHT
            for i, floor in enumerate(self.floors):
                floor_y_positions[floor] = building_y + total_height - (i + 1) * self.FLOOR_HEIGHT

            self._cached_dimensions = {
                "building_x": building_x,
                "building_y": building_y,
                "building_width": building_width,
                "building_height": building_height,
                "elevator_start_x": elevator_start_x,
                "total_elevator_width": total_elevator_width,
                "floor_y_positions": floor_y_positions,
                "total_height": total_height,
            }
            self._last_widget_size = current_size
            self._last_elevator_count = len(self.elevator_status)

    def paintEvent(self, event):
        """Draw the building and elevators"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get widget dimensions and update cache
        width = self.width()
        height = self.height()
        self._update_drawing_cache(width, height)

        # Draw building and elevators using cached values
        self._draw_building(painter, width, height)
        self._draw_elevators(painter, width, height)

    @property
    def cached_dimensions(self) -> dict:
        assert self._cached_dimensions is not None
        return self._cached_dimensions

    @property
    def BUILDING_WIDTH(self):
        elevator_count = len(self.elevator_status)
        return elevator_count * self.ELEVATOR_WIDTH + (elevator_count + 1) * self.ELEVATOR_SPACING

    @property
    def BUILDING_HEIGHT(self):
        return len(self.floors) * self.FLOOR_HEIGHT

    def _draw_building(self, painter: QPainter, width, height):
        """Draw the building structure"""
        cache = self.cached_dimensions

        # Draw floor labels and shaft lines
        painter.setPen(self.text_color)
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        # Draw floors
        for i, floor in enumerate(self.floors):
            y_pos = cache["floor_y_positions"][floor]

            # Draw floor label
            painter.drawText(int(cache["building_x"]), int(y_pos + self.FLOOR_HEIGHT / 2), f"{floor}F")

        # Draw vertical elevator shafts
        painter.setPen(QPen(self.light_color, 1, Qt.PenStyle.DashLine))
        for i, floor in enumerate(self.floors):
            y_pos = cache["floor_y_positions"][floor]

            # Draw elevator shafts for this floor
            shaft_top = y_pos
            shaft_bottom = y_pos + self.ELEVATOR_HEIGHT
            for elevator_id in self.elevator_status:
                x = cache["elevator_start_x"] + (elevator_id - 1) * (self.ELEVATOR_WIDTH + self.ELEVATOR_SPACING)
                painter.drawLine(int(x), int(shaft_top), int(x), int(shaft_bottom))
                painter.drawLine(int(x + self.ELEVATOR_WIDTH), int(shaft_top), int(x + self.ELEVATOR_WIDTH), int(shaft_bottom))

        # Draw horizontal floor lines
        painter.setPen(QPen(self.light_color, 1, Qt.PenStyle.SolidLine))
        for i in range(len(self.floors) + 1):
            y_pos = cache["building_y"] + cache["total_height"] - (i + 1) * self.FLOOR_HEIGHT
            painter.drawLine(0, int(y_pos + self.ELEVATOR_HEIGHT), width, int(y_pos + self.ELEVATOR_HEIGHT))
            painter.drawLine(0, int(y_pos + self.FLOOR_HEIGHT), width, int(y_pos + self.FLOOR_HEIGHT))

    def _draw_elevators(self, painter, width, height):
        """Draw all elevators with dynamic positioning based on elevator count"""
        cache = self.cached_dimensions

        # Draw each elevator
        for elevator_id, elevator in self.elevator_status.items():
            # Calculate elevator position using cached values
            x = cache["elevator_start_x"] + (elevator_id - 1) * (self.ELEVATOR_WIDTH + self.ELEVATOR_SPACING)
            y = cache["building_y"] + elevator["current_position"]

            self._draw_single_elevator(painter, elevator_id, elevator, x, y)

    def _draw_single_elevator(self, painter, elevator_id, elevator, x, y):
        """Draw a single elevator at the specified position"""
        # Set elevator color based on direction
        direction_colors = {"up": self.up_color, "down": self.down_color}
        color = direction_colors.get(elevator["direction"], self.idle_color)

        # Draw elevator body
        painter.setPen(QPen(self.light_color, 2))
        painter.setBrush(QBrush(color))

        elevator_rect = QRectF(x, y, self.ELEVATOR_WIDTH, self.ELEVATOR_HEIGHT)
        painter.drawRect(elevator_rect)

        # Draw elevator ID
        painter.setPen(self.text_color)
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.drawText(elevator_rect, Qt.AlignmentFlag.AlignCenter, f"E{elevator_id}")

        # Draw doors if needed
        door_percentage = elevator.get("door_percentage", 0.0)
        if elevator["door_open"] or door_percentage > 0:
            self._draw_elevator_doors(painter, x, y, door_percentage)

    def _draw_elevator_doors(self, painter, x, y, door_percentage):
        """Draw elevator doors with specified opening percentage"""
        assert 0.0 <= door_percentage <= 1.0, f"Invalid door percentage: {door_percentage}"

        door_width = self.ELEVATOR_WIDTH / 2 - 4
        door_height = self.ELEVATOR_HEIGHT - 8

        # Calculate door offsets
        left_door_offset = (door_width / 2) * door_percentage
        right_door_offset = (door_width / 2) * door_percentage

        painter.setPen(QPen(self.light_color, 1))
        painter.setBrush(QBrush(self.door_color))

        # Left door
        painter.drawRect(QRectF(x + 4 - left_door_offset, y + 4, door_width, door_height))

        # Right door
        painter.drawRect(QRectF(x + self.ELEVATOR_WIDTH / 2 + right_door_offset, y + 4, door_width, door_height))

        # Draw open space if doors are open
        if door_percentage > 0:
            open_width = self.ELEVATOR_WIDTH - 8 - (door_width - left_door_offset) - (door_width - right_door_offset)
            if open_width > 0:
                painter.setBrush(QBrush(self.door_open_color))
                painter.drawRect(QRectF(x + 4 + door_width - left_door_offset, y + 4, open_width, door_height))
