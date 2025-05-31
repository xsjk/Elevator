import unittest
import asyncio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from system.core.controller import Controller, Config
from system.utils.common import Floor, Direction


class TestController(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.controller = Controller(config=Config())
        self.controller.start()
        await asyncio.sleep(0.1)

    async def asyncTearDown(self):
        await self.controller.stop()

    async def testreset(self):
        await self.controller.queue.put("test_event")

        await self.controller.reset()
        self.assertTrue(self.controller.queue.empty())

    async def test_handle_call_up(self):
        await self.controller.handle_message("call_up@2")
        self.assertEqual(self.controller.elevators[1].current_floor, 2)
     
    async def test_handle_call_down(self):
        await self.controller.handle_message("call_down@3")
        self.assertEqual(self.controller.elevators[1].current_floor, 3)

    async def test_handle_cancel_call_up(self):
        task = self.controller.handle_message_task("call_up@2")
        await asyncio.sleep(0.05)

        self.assertEqual(len(self.controller.requests), 1)

        await self.controller.handle_message("cancel_call_up@2")
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.controller.requests), 0)
        self.assertNotIn("call_up@2", self.controller.message_tasks)

    async def test_handle_cancel_call_down(self):
        task = self.controller.handle_message_task("call_down@3")
        await asyncio.sleep(0.05)

        self.assertEqual(len(self.controller.requests), 1)

        await self.controller.handle_message("cancel_call_down@3")
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.controller.requests), 0)
        self.assertNotIn("call_down@3", self.controller.message_tasks)

    async def test_handle_select_floor(self):
        await self.controller.handle_message("select_floor@2#1")
        self.assertEqual(self.controller.elevators[1].current_floor, Floor("2"))

    async def test_handle_deselect_floor(self):
        # 模拟 select_floor 并立即取消（不要等它执行完）
        task = self.controller.handle_message_task("select_floor@2#1")
        await asyncio.sleep(0.05)  # 给一点时间让任务开始执行但未完成

        # 确保 floor 被选中
        elevator = self.controller.elevators[1]
        self.assertIn(Floor("2"), elevator.selected_floors)

        # 现在取消选择
        await self.controller.handle_message("deselect_floor@2#1")
        await asyncio.sleep(0.05)

        # 验证任务被移除，楼层也被取消
        self.assertNotIn(Floor("2"), elevator.selected_floors)
        self.assertNotIn("select_floor@2#1", self.controller.message_tasks)

    async def test_handle_open_door(self):
        await self.controller.handle_message("open_door#1")
        self.assertTrue(self.controller.elevators[1].door_open)

    async def test_handle_close_door(self):
        await self.controller.handle_message("close_door#1")
        self.assertFalse(self.controller.elevators[1].door_open)

    async def test_unrecognized_message_warning(self):
        await self.controller.handle_message("foobar@unknown")

    async def test_calculate_duration(self):
        duration = self.controller.calculate_duration(3, 2)
        expected = 3 * self.controller.config.floor_travel_duration + \
                   2 * (self.controller.config.door_move_duration * 2 + self.controller.config.door_stay_duration)
        self.assertEqual(duration, expected) # 19.0

    async def test_estimate_arrival_time_cases(self):
        elevator = self.controller.elevators[1].copy()

        # Test Case 1: Same floor, IDLE
        elevator._current_floor = Floor("1")
        elevator.target_floor_chains.clear()
        time_same = self.controller.estimate_arrival_time(elevator, Floor("1"), Direction.IDLE)
        self.assertAlmostEqual(time_same, 5.0, delta=0.1)

        # Test Case 2: Target floor is above, 3 floors away, no stops
        elevator._current_floor = Floor("1")
        elevator.target_floor_chains.clear()
        time_up = self.controller.estimate_arrival_time(elevator, Floor("4"), Direction.UP)
        self.assertAlmostEqual(time_up, 13.0, delta=0.1)

        # Test Case 3: Elevator is moving
        elevator._current_floor = Floor("5")
        elevator.target_floor_chains.clear()
        elevator.commit_floor(Floor("4"), Direction.DOWN)
        time_down = self.controller.estimate_arrival_time(elevator, Floor("3"), Direction.DOWN)
        self.assertAlmostEqual(time_down, 15.0, delta=0.1)

    async def test_call_elevator(self):
        await self.controller.call_elevator(Floor("2"), Direction.UP)
        self.assertEqual(self.controller.elevators[1].current_floor, 2) 
        self.assertNotIn((Floor("2"), Direction.UP), self.controller.requests)

    async def test_select_floor(self):
        await self.controller.select_floor(Floor("3"), 1)
        self.assertEqual(self.controller.elevators[1].current_floor, Floor("3"))

    async def test_open_door(self):
        elevator = self.controller.elevators[1]
        await self.controller.open_door(elevator)
        self.assertTrue(elevator.door_open)

    async def test_close_door(self):
        elevator = self.controller.elevators[1]
        await self.controller.close_door(elevator)
        self.assertFalse(elevator.door_open)

if __name__ == '__main__':
    unittest.main()
