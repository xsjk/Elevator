import asyncio
import unittest

from common import DoorState, Floor, GUIAsyncioTestCase


class ElevatorUITest(GUIAsyncioTestCase):
    async def test_open_door_button(self):
        """Test the internal open door button of Elevator 1."""
        self.assertFalse(self.elevator1.state.is_door_open())

        # 模拟点击“Open Door”按钮
        self.elevator1_UI.open_door_button.click()

        self.assertIn("open_door#1", self.controller.message_tasks)

        await asyncio.sleep(0.5)
        self.assertTrue(self.elevator1.state.is_door_open())  # Door is opening or opened
        self.assertIn("开", self.elevator1_UI.door_label.text())

        await asyncio.sleep(5)
        self.assertFalse(self.elevator1.state.is_door_open())
        self.assertIn("关", self.elevator1_UI.door_label.text())

    async def test_close_door_button(self):
        """Test the internal close door button of Elevator 1."""
        self.assertFalse(self.elevator1.state.is_door_open())

        # 模拟点击“Open Door”按钮
        self.elevator1_UI.open_door_button.click()
        await asyncio.sleep(0.1)
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.OPENING)

        # 点击“Close Door”按钮
        self.elevator1_UI.close_door_button.click()
        await asyncio.sleep(4)

        # 检查 controller 中的任务
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.CLOSING)

    async def test_select_floor_and_move(self):
        """Test selecting a floor button triggers elevator movement."""
        target_floor_up = Floor("3")

        # 模拟点击内部楼层按钮（3层按钮）
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.1)  # 等待 controller 启动任务

        # 控制器应收到该命令
        self.assertIn("select_floor@3#1", self.controller.message_tasks)
        # 楼层按钮应变为选中
        self.assertTrue(self.elevator1_UI.floor_buttons["3"].isChecked())

        # 等待电梯运动完成（包括加速、行程、开门）
        duration = self.controller.calculate_duration(
            n_floors=2,  # 从 1 层到 3 层
            n_stops=0,
        )
        await asyncio.sleep(duration + 1.0)

        # 电梯应到达目标楼层
        self.assertEqual(self.elevator1.current_floor, target_floor_up)
        # UI 中的楼层指示应变为 3
        self.assertIn("3", self.elevator1_UI.floor_label.text())
        # 按钮应取消选中
        self.assertFalse(self.elevator1_UI.floor_buttons["3"].isChecked())


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
