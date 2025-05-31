import unittest
from unittest.mock import MagicMock, patch
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from system.gui.visualizer import ElevatorVisualizer  
from system.utils.common import Floor, Direction, ElevatorId


app = QApplication(sys.argv)  # Qt 应用上下文

class TestElevatorVisualizer(unittest.TestCase):
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

    # TestCase 1
    def test_update_theme_colors_dark_mode(self):
        # Patch palette and QColor.lightness() to simulate dark mode
        with patch.object(self.visualizer, 'palette') as mock_palette:
            dark_color = MagicMock(spec=QColor)
            dark_color.lightness.return_value = 50  # simulate dark mode
            mock_palette.return_value.color.return_value = dark_color

            self.visualizer._update_theme_colors()

            # Check that up_color is bright green (dark mode expected)
            self.assertEqual(self.visualizer.up_color, QColor(0, 255, 100))
            self.assertEqual(self.visualizer.down_color, QColor(255, 100, 100))
            self.assertEqual(self.visualizer.idle_color, QColor(150, 150, 150))
            self.assertEqual(self.visualizer.door_color, QColor(220, 220, 220))
            self.assertEqual(self.visualizer.door_open_color, QColor(80, 80, 80))

    # TestCase 2
    def test_update_theme_colors_light_mode(self):
        # Patch palette and QColor.lightness() to simulate light mode
        with patch.object(self.visualizer, 'palette') as mock_palette:
            light_color = MagicMock(spec=QColor)
            light_color.lightness.return_value = 200  # simulate light mode
            mock_palette.return_value.color.return_value = light_color

            self.visualizer._update_theme_colors()

            # Check that up_color is standard green (light mode expected)
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
        self.visualizer.changeEvent(event)  # 仅测试是否正常调用
    
    def test_calculate_floor_positions(self):
        # 设置控件尺寸以确保 height 可用
        self.visualizer.resize(200, 400)  # 宽度无关紧要，关键是高度
        self.visualizer._calculate_floor_positions()

        floor_positions = self.visualizer.floor_positions
        expected_floors = sorted(self.floors, reverse=True)

        # 检查所有楼层都在 floor_positions 中
        self.assertEqual(set(floor_positions.keys()), set(self.floors))

        # 检查楼层越高，位置越靠上（Y 值越小）
        for i in range(len(expected_floors) - 1):
            upper = expected_floors[i]
            lower = expected_floors[i + 1]
            self.assertLess(floor_positions[upper], floor_positions[lower],
                            msg=f"Floor {upper} (Y={floor_positions[upper]}) should be above Floor {lower} (Y={floor_positions[lower]})")

    # TestCase 1
    def test_update_elevator_status_valid(self):
        self.visualizer.update_elevator_status(ElevatorId(1), Floor(2), True, Direction.UP)
        status = self.visualizer.elevator_status[1]
        self.assertEqual(status["current_floor"], 2)
        self.assertEqual(status["door_open"], True)
        self.assertEqual(status["direction"], Direction.UP)
        self.assertEqual(status["current_position"], self.visualizer.floor_positions[2])

    # TestCase 2
    def test_update_elevator_status_invalid_id(self):
        from unittest.mock import patch
        with patch('logging.warning') as mock_log:
            self.visualizer.update_elevator_status(ElevatorId(99), Floor(2), False, Direction.IDLE)
            mock_log.assert_called_once()

    # TestCase 3
    def test_update_elevator_status_invalid_floor(self):
        from unittest.mock import patch
        with patch('logging.warning') as mock_log:
            self.visualizer.update_elevator_status(ElevatorId(1), Floor(99), False, Direction.IDLE)
            self.assertIn("not found in floor positions", mock_log.call_args[0][0])

    def test_paint_event_callable(self):
        from PySide6.QtGui import QPaintEvent
        event = QPaintEvent(self.visualizer.rect())
        try:
            self.visualizer.paintEvent(event)
        except Exception as e:
            self.fail(f"paintEvent raised exception: {e}")

if __name__ == "__main__":
    unittest.main()
