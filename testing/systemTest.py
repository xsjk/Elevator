import unittest
import asyncio
from PySide6.QtWidgets import QApplication
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from system.gui.gui_controller import GUIController
from system.utils.common import ElevatorState, Floor, Direction, DoorState


class SystemTestOpenDoor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if QApplication.instance() is None:
            self.app = QApplication([])

        self.controller = GUIController()
        self.controller.start()
        # self.controller.window.hide()
        self.window = self.controller.window

        self.building = self.window.building_panel

        self.elevator1_UI = self.window.elevator_panels[1]
        self.elevator2_UI = self.window.elevator_panels[2]
        self.elevator1 = self.controller.elevators[1]
        self.elevator2 = self.controller.elevators[2]

        self.elevator2.current_floor = Floor("3")
        self.elevator2_UI.update_elevator_status(
            self.elevator2.current_floor,
            self.elevator2._state.get_door_state(),
            self.elevator2._state.get_moving_direction()
        )

    async def asyncTearDown(self):
        await self.controller.stop()

    async def test_open_door_by_button_and_autoclose(self):
        """UC1-a: Static press open door button -> door opens"""
        """UC2-b: Door auto-closes after stay duration if no action"""
        # 用户点击 open door
        self.elevator1_UI.open_door_button.click()
        self.elevator2_UI.open_door_button.click()
        await asyncio.sleep(0.5)  # 给电梯状态机反应时间

        # 检查门是否已打开
        self.assertTrue(self.elevator1._state.is_door_open())
        self.assertTrue(self.elevator2._state.is_door_open())
        self.assertIn("Open", self.elevator1_UI.door_label.text())
        self.assertIn("Open", self.elevator2_UI.door_label.text())

        await asyncio.sleep(5)
        self.assertFalse(self.elevator1.state.is_door_open())
        self.assertFalse(self.elevator2.state.is_door_open())
        self.assertIn("Closed", self.elevator1_UI.door_label.text())
        self.assertIn("Closed", self.elevator2_UI.door_label.text())

    async def test_open_door_on_arrival_and_autoclose(self):
        """UC1-b: Elevator arrives at target floor -> door opens automatically"""
        self.building.down_buttons["2"].click()
        await asyncio.sleep(self.controller.calculate_duration(1, 0) + 0.1)

        # 检查是否到达目标楼层
        self.assertEqual(self.elevator1.current_floor, Floor("2"))

        # 检查门是否自动打开
        self.assertTrue(self.elevator1._state.is_door_open())
        self.assertIn("Open", self.elevator1_UI.door_label.text())

        await asyncio.sleep(self.controller.config.door_stay_duration + self.controller.config.door_move_duration + 3)
        # 门应自动关闭
        self.assertFalse(self.elevator1._state.is_door_open())
        self.assertIn("Closed", self.elevator1_UI.door_label.text())

    async def test_close_door_by_button(self):
        """UC2-a: Manually press close door when open -> door starts closing"""
        self.assertFalse(self.elevator1.state.is_door_open())

        # 模拟点击“Open Door”按钮
        self.elevator1_UI.open_door_button.click()
        self.elevator2_UI.open_door_button.click()
        await asyncio.sleep(0.1)
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.OPENING)
        self.assertEqual(self.elevator2.state.get_door_state(), DoorState.OPENING)

        # 点击“Close Door”按钮
        self.elevator1_UI.close_door_button.click()
        self.elevator2_UI.close_door_button.click()
        await asyncio.sleep(4)  

        # 检查 controller 中的任务
        self.assertEqual(self.elevator1.state.get_door_state(), DoorState.CLOSING)
        self.assertEqual(self.elevator2.state.get_door_state(), DoorState.CLOSING)

    async def test_auto_close_moved(self):
        """UC2-c: Elevator moving, door keeps closed."""
        # 请求电梯从 1 → 3
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.1)

        moving_duration = self.controller.calculate_duration(n_floors=2, n_stops=0)

        # 在移动过程中多次采样 elevator 状态
        interval = 0.2
        steps = int(moving_duration // interval) + 1
        for _ in range(steps):
            state = self.elevator1._state
            if state.is_moving():
                self.assertFalse(state.is_door_open())
            await asyncio.sleep(interval)
        
        await asyncio.sleep(1.0)
        # 最终应到达 3 层且门打开
        self.assertEqual(self.controller.elevators[1].current_floor, Floor("3"))
        self.assertTrue(self.controller.elevators[1]._state.is_door_open())

    async def test_select_one_floor(self):
        """UC3-a: Select one floor inside elevator"""
        self.elevator1_UI.floor_buttons["2"].click()
        self.elevator2_UI.floor_buttons["2"].click()
        await asyncio.sleep(0.1)

        # 控制器任务应注册
        self.assertIn("select_floor@2#1", self.controller.message_tasks)
        self.assertIn("select_floor@2#2", self.controller.message_tasks)

        # 等待电梯运行完成
        duration = self.controller.calculate_duration(n_floors=1, n_stops=0)
        await asyncio.sleep(duration + 0.5)

        # 电梯应到达目标楼层并开门
        self.assertEqual(self.elevator1.current_floor, 2)
        self.assertEqual(self.elevator2.current_floor, 2)
        self.assertTrue(self.elevator1._state.is_door_open())
        self.assertTrue(self.elevator2._state.is_door_open())
        self.assertIn("2", self.elevator1_UI.floor_label.text())

        await asyncio.sleep(5)
        self.assertFalse(self.elevator1.state.is_moving())
        self.assertFalse(self.elevator2.state.is_moving())

    async def test_select_multiple_floors(self):
        """UC3-b: Select multiple floors in sequence"""
        self.elevator1_UI.floor_buttons["2"].click()
        self.elevator2_UI.floor_buttons["1"].click()
        await asyncio.sleep(0.1)
        self.elevator1_UI.floor_buttons["3"].click()
        self.elevator2_UI.floor_buttons["-1"].click()
        await asyncio.sleep(0.1)

        # 控制器任务应包含两个目标
        self.assertIn("select_floor@2#1", self.controller.message_tasks)
        self.assertIn("select_floor@3#1", self.controller.message_tasks)
        self.assertIn("select_floor@1#2", self.controller.message_tasks)
        self.assertIn("select_floor@-1#2", self.controller.message_tasks)

        # 等待电梯完成两段运行
        duration = self.controller.calculate_duration(4, 1)
        await asyncio.sleep(duration + 1.0)

        # 电梯最终到达 
        self.assertEqual(self.elevator1.current_floor, Floor("3"))
        self.assertEqual(self.elevator2.current_floor, Floor("-1"))

    async def test_select_current_floor(self):
        """UC3-c: Select current floor (no movement, door opens)"""
        self.elevator1_UI.floor_buttons["1"].click()
        self.elevator2_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.2)

        self.assertEqual(self.elevator1.current_floor, 1)
        self.assertTrue(self.elevator1._state.is_door_open())

        self.assertEqual(self.elevator2.current_floor, 3)
        self.assertTrue(self.elevator2._state.is_door_open())

    async def test_cancel_one_of_multiple_floors(self):
        """UC4: Select two floors, cancel one"""
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.1)
        self.elevator1_UI.floor_buttons["2"].click()
        await asyncio.sleep(0.1)

        self.assertTrue(self.elevator1_UI.floor_buttons["3"].isChecked())
        self.assertTrue(self.elevator1_UI.floor_buttons["2"].isChecked())

        # 取消其中一个楼层
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.1)

        # 检查 UI 状态
        self.assertFalse(self.elevator1_UI.floor_buttons["3"].isChecked())
        self.assertTrue(self.elevator1_UI.floor_buttons["2"].isChecked())

        # 等待运行完成，应只到 2 层
        await asyncio.sleep(self.controller.calculate_duration(1, 0) + 0.5)
        self.assertEqual(self.elevator1.current_floor, Floor("2"))

    async def test_call_elevator_up_button(self):
        """UC5: Press 'up' button on floor 2 → elevator 1 responds and door opens"""
        # 用户在 2 层按下“上”按钮
        self.building.up_buttons["2"].click()
        await asyncio.sleep(0.1)

        # 控制器任务应包含该请求
        self.assertIn("call_up@2", self.controller.message_tasks)

        # 等待 elevator 1 到达目标楼层
        move_duration = self.controller.calculate_duration(n_floors=1, n_stops=0)
        await asyncio.sleep(move_duration + 0.5)

        # 电梯应在目标楼层
        self.assertEqual(self.elevator1.current_floor, 2)

        # 楼层标签应正确
        self.assertIn("2", self.window.elevator_panels[1].floor_label.text())

    async def test_display_info_inside_and_outside(self):
        """UC6: Comprehensive UI display verification during elevator run"""
        self.elevator1_UI.floor_buttons["3"].click()
        await asyncio.sleep(0.1)

        # UC6-a: 楼层3按钮应点亮
        self.assertTrue(self.elevator1_UI.floor_buttons["3"].isChecked(), "Floor 3 button should be checked")

        #  检查电梯运行中信息显示 
        move_duration = self.controller.calculate_duration(2, 1)
        sample_interval = 0.3
        steps = int(move_duration / sample_interval)

        for _ in range(steps):
            state = self.controller.elevators[1]._state
            current_floor = self.controller.elevators[1].current_floor

            # UC6-b: 当前楼层显示更新
            self.assertIn(str(current_floor), self.elevator1_UI.floor_label.text())

            #  UC6-c: 门应关闭
            if state.is_moving():
                self.assertIn("Closed", self.elevator1_UI.door_label.text())

                # UC6-d: 显示方向（UP / DOWN）
                dir_text = self.elevator1_UI.direction_label.text()
                self.assertIn("UP", dir_text.upper())
            else:
                dir_text = self.elevator1_UI.direction_label.text()
                self.assertIn("IDLE", dir_text.upper())
                
            await asyncio.sleep(sample_interval)

        # 到达目标楼层后：
        await asyncio.sleep(0.5)

        # UC6-a: 按钮应取消选中
        self.assertFalse(self.elevator1_UI.floor_buttons["3"].isChecked())

        #  UC6-b/c: 楼层应为 3，门应 Open
        self.assertEqual(self.elevator1.current_floor, Floor("3"))
        self.assertIn("3", self.elevator1_UI.floor_label.text())

        # UC6-e: 外部按钮应响应到达
        # 用户按下外部按钮（模拟有人呼叫）
        self.building.down_buttons["2"].click()
        await asyncio.sleep(0.1)

        # 外部按钮应点亮（isChecked）
        self.assertTrue(self.building.down_buttons["2"].isChecked())

        # 等电梯完成开门后，按钮应熄灭
        await asyncio.sleep(self.controller.config.floor_travel_duration + 3.5)
        self.assertFalse(self.building.down_buttons["2"].isChecked())

    async def test_multiple_calls_outside(self):
        """EM1: Multiple floors press external call buttons → elevators dispatched correctly"""

        # 按下多个外部按钮
        self.building.down_buttons["2"].click()  
        self.building.up_buttons["2"].click()    
        await asyncio.sleep(0.2)

        # 系统应记录多个任务
        self.assertIn("call_down@2", self.controller.message_tasks)
        self.assertIn("call_up@2", self.controller.message_tasks)

        # 等待电梯响应和运行
        await asyncio.sleep(self.controller.calculate_duration(1, 0) + 1.0)

        # Elevator 2 应到达 3 层，门应打开
        self.assertEqual(self.elevator2.current_floor, Floor("2"))
        self.assertTrue(self.elevator2._state.is_door_open())

        # Elevator 1 应到达 2 层
        self.assertEqual(self.elevator1.current_floor, Floor("2"))
        self.assertTrue(self.elevator1._state.is_door_open())

    async def test_dispatch_efficiency(self):
        """EM2: Efficient elevator assignment - nearest elevator handles the call"""
        self.elevator1.current_floor = Floor("-1")
        self.elevator1_UI.update_elevator_status(
            self.elevator2.current_floor,
            self.elevator2._state.get_door_state(),
            self.elevator2._state.get_moving_direction()
        )

        # 模拟 2 层按上行按钮（距离电梯 2 更近）
        self.window.building_panel.up_buttons["2"].click()
        await asyncio.sleep(0.2)

        # 记录电梯位置，等待响应
        await asyncio.sleep(self.controller.calculate_duration(1, 0) + 1.0)

        # Elevator 2 应响应该请求
        self.assertEqual(self.elevator2.current_floor, Floor("2"))
        self.assertTrue(self.elevator2._state.is_door_open())

        # Elevator 1 应未移动
        self.assertEqual(self.elevator1.current_floor, Floor("-1"))

if __name__ == "__main__":
    unittest.main()
