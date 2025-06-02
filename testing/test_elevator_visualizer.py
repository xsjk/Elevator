import sys
import unittest
from unittest.mock import patch

from .common import Direction, ElevatorVisualizer, Floor, ThemeManager, main_window
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


class TestElevatorVisualizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication(sys.argv)
        main_window.theme_manager = ThemeManager(cls.app)

    def setUp(self):
        self.floors = [Floor(-1), Floor(1), Floor(2), Floor(3)]
        self.elevator_count = 2
        self.visualizer = ElevatorVisualizer(self.floors, self.elevator_count)

    # TestCase 1
    def test_set_elevator_count_add(self):
        self.visualizer.set_elevator_count(3)
        self.assertEqual(len(self.visualizer.elevator_status), 3)
        self.assertIn(3, self.visualizer.elevator_status)

    # TestCase 2
    def test_set_elevator_count_reduce(self):
        self.visualizer.set_elevator_count(1)
        self.assertEqual(len(self.visualizer.elevator_status), 1)
        self.assertNotIn(2, self.visualizer.elevator_status)

    def test_update_theme_colors_dark_mode(self):
        # Test dark theme colors
        with patch.object(main_window.theme_manager, "get_current_theme", return_value="dark"):
            self.visualizer._update_theme_colors()

            # Verify dark theme colors
            self.assertEqual(self.visualizer.up_color, QColor(0, 255, 100))
            self.assertEqual(self.visualizer.down_color, QColor(255, 100, 100))
            self.assertEqual(self.visualizer.idle_color, QColor(150, 150, 150))
            self.assertEqual(self.visualizer.door_color, QColor(220, 220, 220))
            self.assertEqual(self.visualizer.door_open_color, QColor(80, 80, 80))

    def test_update_theme_colors_light_mode(self):
        # Test light theme colors
        with patch.object(main_window.theme_manager, "get_current_theme", return_value="light"):
            self.visualizer._update_theme_colors()

            # Verify light theme colors
            self.assertEqual(self.visualizer.up_color, QColor(0, 200, 0))
            self.assertEqual(self.visualizer.down_color, QColor(200, 0, 0))
            self.assertEqual(self.visualizer.idle_color, QColor(100, 100, 100))
            self.assertEqual(self.visualizer.door_color, QColor(200, 200, 200))
            self.assertEqual(self.visualizer.door_open_color, QColor(50, 50, 50))

    def test_floor_positions_sorted(self):
        positions = list(self.visualizer.floor_positions.keys())
        self.assertEqual(positions, sorted(self.floors))

    def test_change_event_palette(self):
        from PySide6.QtCore import QEvent

        event = QEvent(QEvent.Type.PaletteChange)
        self.visualizer.changeEvent(event)  # only to ensure no exceptions are raised

    def test_calculate_floor_positions(self):
        self.visualizer.resize(200, 400)  # width is not used, height is important
        self.visualizer._calculate_floor_positions()

        floor_positions = self.visualizer.floor_positions
        expected_floors = sorted(self.floors, reverse=True)

        # Check if all floors have positions
        self.assertEqual(set(floor_positions.keys()), set(self.floors))

        # Check if higher floors have smaller Y positions
        for i in range(len(expected_floors) - 1):
            upper = expected_floors[i]
            lower = expected_floors[i + 1]
            self.assertLess(floor_positions[upper], floor_positions[lower], msg=f"Floor {upper} (Y={floor_positions[upper]}) should be above Floor {lower} (Y={floor_positions[lower]})")

    # TestCase 1
    def test_update_elevator_status_valid(self):
        self.visualizer.update_elevator_status(1, Floor(2), True, Direction.UP)
        status = self.visualizer.elevator_status[1]
        self.assertEqual(status["current_floor"], 2)
        self.assertEqual(status["door_open"], True)
        self.assertEqual(status["direction"], Direction.UP)
        self.assertEqual(status["current_position"], self.visualizer.floor_positions[2])

    # TestCase 2
    def test_update_elevator_status_invalid_id(self):
        from unittest.mock import patch

        with patch("logging.warning") as mock_log:
            self.visualizer.update_elevator_status(99, Floor(2), False, Direction.IDLE)
            mock_log.assert_called_once()

    # TestCase 3
    def test_update_elevator_status_invalid_floor(self):
        from unittest.mock import patch

        with patch("logging.warning") as mock_log:
            self.visualizer.update_elevator_status(1, Floor(99), False, Direction.IDLE)
            self.assertIn("not found in floor positions", mock_log.call_args[0][0])

    def test_paint_event_callable(self):
        from PySide6.QtGui import QPaintEvent

        event = QPaintEvent(self.visualizer.rect())
        try:
            self.visualizer.paintEvent(event)
        except Exception as e:
            self.fail(f"paintEvent raised exception: {e}")


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
