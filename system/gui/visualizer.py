import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame

from ..utils.common import Direction, ElevatorId, Floor


class ElevatorVisualizer(QFrame):
    """
    2D visualization of elevator movement
    Shows real-time position and status of elevators in the building
    Supports dynamic number of elevators based on configuration
    """

    # Floor heights in pixels
    FLOOR_HEIGHT = 80
    # Building dimensions
    BUILDING_WIDTH = 300  # Elevator dimensions
    ELEVATOR_WIDTH = 60
    ELEVATOR_HEIGHT = 70
    # Horizontal spacing between elevators
    ELEVATOR_SPACING = 40

    def __init__(self, floors, elevators=None, elevator_count=2):
        """Initialize the elevator visualizer

        Args:
            floors: List of Floor objects representing building floors
            elevators: Optional dictionary of elevator configurations
            elevator_count: Number of elevators to display (used when elevators is None)
        """
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

        # Ensure floors are in the correct order from bottom to top
        if "-1" in self.floors and self.floors.index("-1") != 0:
            # Reorder floors to ensure -1 is at the bottom
            self.floors.remove("-1")
            self.floors.insert(0, "-1")

        self.floor_positions = self._calculate_floor_positions()

        # Elevator configuration - create elevators dynamically based on elevator_count
        if elevators is None:
            self.elevators = {}
            for elevator_id in range(1, elevator_count + 1):
                self.elevators[elevator_id] = {"current_floor": "1", "current_position": 0, "door_open": False, "direction": "idle"}
        else:
            self.elevators = elevators

        # Subscribe to position updates
        # event_bus.subscribe(Event.ELEVATOR_UPDATED, self._on_elevator_position_updated)

        # Cache theme colors
        self._update_theme_colors()

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

    def update_elevator_status(self, elevator_id: ElevatorId, floor: Floor, door_open: bool, direction: Direction):
        """Update the state of an elevator"""
        if elevator_id not in self.elevators:
            logging.warning(f"Invalid elevator ID: {elevator_id}")
            return

        # Log state change for debugging
        logging.debug(f"Updating elevator {elevator_id} visualization: floor={floor}, door_open={door_open}, direction={direction}")

        # Update elevator state
        self.elevators[elevator_id]["current_floor"] = floor
        self.elevators[elevator_id]["door_open"] = door_open
        self.elevators[elevator_id]["direction"] = direction

        # Update position directly
        if floor in self.floor_positions:
            self.elevators[elevator_id]["current_position"] = self.floor_positions[floor]
            logging.debug(f"Set elevator {elevator_id} position to {self.floor_positions[floor]} for floor {floor}")
        else:
            logging.warning(f"Floor {floor} not found in floor positions map. Available floors: {list(self.floor_positions.keys())}")

        # Request repaint
        self.update()

    def paintEvent(self, event):
        """Draw the building and elevators"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get widget dimensions
        width = self.width()
        height = self.height()

        # Draw building
        self._draw_building(painter, width, height)

        # Draw elevators
        self._draw_elevators(painter, width, height)

    def _draw_building(self, painter: QPainter, width, height):
        """Draw the building structure"""
        # Building outline
        building_x = (width - self.BUILDING_WIDTH) / 2

        # Draw floors
        for floor, y_pos in self.floor_positions.items():
            # Draw floor line with theme-aware color
            painter.setPen(QPen(self.floor_line_color, 2))
            painter.drawLine(int(building_x), int(y_pos + self.FLOOR_HEIGHT), int(building_x + self.BUILDING_WIDTH), int(y_pos + self.FLOOR_HEIGHT))  # Draw floor label with theme-aware color
            painter.setPen(self.window_text_color)
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.drawText(int(building_x - 40), int(y_pos + self.FLOOR_HEIGHT - 10), f"Floor {floor}")

    def _draw_elevators(self, painter, width, height):
        """
        Draw all elevators with dynamic positioning based on elevator count
        Supports any number of elevators configured in the system
        """
        building_x = (width - self.BUILDING_WIDTH) / 2

        # Calculate starting position for first elevator - centers all elevators in building
        total_elevator_width = len(self.elevators) * self.ELEVATOR_WIDTH + (len(self.elevators) - 1) * self.ELEVATOR_SPACING
        elevator_start_x = building_x + (self.BUILDING_WIDTH - total_elevator_width) / 2

        # Draw each elevator
        for elevator_id, elevator in self.elevators.items():
            # Calculate elevator position
            x = elevator_start_x + (elevator_id - 1) * (self.ELEVATOR_WIDTH + self.ELEVATOR_SPACING)
            y = elevator["current_position"]

            # Set elevator color based on direction
            if elevator["direction"] == "up":
                color = self.up_color  # Green for up
            elif elevator["direction"] == "down":
                color = self.down_color  # Red for down
            else:
                color = self.idle_color  # Gray for idle

            # Draw elevator shaft
            painter.setPen(QPen(Qt.GlobalColor.black, 1, Qt.PenStyle.DashLine))
            shaft_x = x + self.ELEVATOR_WIDTH / 2

            # Get the highest and lowest floor positions
            lowest_floor = self.floors[0]  # First floor in the list (now -1)
            highest_floor = self.floors[-1]  # Last floor in the list (now 3)

            shaft_top = self.floor_positions[highest_floor]
            shaft_bottom = self.floor_positions[lowest_floor] + self.FLOOR_HEIGHT

            painter.drawLine(int(shaft_x), int(shaft_top), int(shaft_x), int(shaft_bottom))

            # Draw elevator
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.setBrush(QBrush(color))

            elevator_rect = QRectF(x, y, self.ELEVATOR_WIDTH, self.ELEVATOR_HEIGHT)
            painter.drawRect(elevator_rect)

            # Draw elevator ID
            painter.setPen(self.text_color)
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.drawText(elevator_rect, Qt.AlignmentFlag.AlignCenter, f"E{elevator_id}")

            # Draw doors if open or partially open
            door_percentage = elevator.get("door_percentage", 0.0)
            if elevator["door_open"] or door_percentage > 0:
                door_width = self.ELEVATOR_WIDTH / 2 - 4
                door_height = self.ELEVATOR_HEIGHT - 8

                # Calculate door offset based on door percentage
                left_door_offset = (door_width / 2) * door_percentage
                right_door_offset = (door_width / 2) * door_percentage

                # Left door
                painter.setPen(QPen(Qt.GlobalColor.black, 1))
                painter.setBrush(QBrush(self.door_color))
                painter.drawRect(QRectF(x + 4 - left_door_offset, y + 4, door_width, door_height))

                # Right door
                painter.drawRect(QRectF(x + self.ELEVATOR_WIDTH / 2 + right_door_offset, y + 4, door_width, door_height))

                # Draw open space (visible when doors are fully or partially open)
                if door_percentage > 0:
                    open_width = self.ELEVATOR_WIDTH - 8 - (door_width - left_door_offset) - (door_width - right_door_offset)
                    if open_width > 0:
                        painter.setBrush(QBrush(self.door_open_color))
                        painter.drawRect(QRectF(x + 4 + door_width - left_door_offset, y + 4, open_width, door_height))

    def _draw_elevators_text(self, painter, width, height):
        """Draw the elevators"""
        building_x = (width - self.BUILDING_WIDTH) / 2

        # Calculate starting position for first elevator
        elevator_start_x = building_x + (self.BUILDING_WIDTH - (len(self.elevators) * self.ELEVATOR_WIDTH + (len(self.elevators) - 1) * self.ELEVATOR_SPACING)) / 2

        # Draw each elevator
        for elevator_id, elevator in self.elevators.items():
            # Calculate elevator position
            x = elevator_start_x + (elevator_id - 1) * (self.ELEVATOR_WIDTH + self.ELEVATOR_SPACING)
            y = elevator["current_position"]

            # Draw current floor
            text_rect = QRectF(x, y + self.ELEVATOR_HEIGHT, self.ELEVATOR_WIDTH, 20)
            painter.setPen(self.text_color)
            painter.setFont(QFont("Arial", 8))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"Floor: {elevator['current_floor']}")
