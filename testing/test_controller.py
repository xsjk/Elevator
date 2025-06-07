import asyncio
import unittest

from common import Controller, Direction, Floor


class TestController(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = Controller()
        self.controller.start()
        await asyncio.sleep(0.1)

    async def asyncTearDown(self):
        await self.controller.stop()

    async def test_reset(self):
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

        self.assertEqual(len(self.controller.elevators.requests), 1)

        await self.controller.handle_message("cancel_call_up@2")
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.controller.elevators.requests), 0)
        self.assertNotIn("call_up@2", self.controller.message_tasks)

    async def test_handle_cancel_call_down(self):
        task = self.controller.handle_message_task("call_down@3")
        await asyncio.sleep(0.05)

        self.assertEqual(len(self.controller.elevators.requests), 1)

        await self.controller.handle_message("cancel_call_down@3")
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.controller.elevators.requests), 0)
        self.assertNotIn("call_down@3", self.controller.message_tasks)

    async def test_handle_select_floor(self):
        await self.controller.handle_message("select_floor@2#1")
        self.assertEqual(self.controller.elevators[1].current_floor, Floor("2"))

    async def test_handle_deselect_floor(self):
        # Simulate selecting and deselecting a floor without waiting for the task to complete
        self.controller.handle_message_task("select_floor@2#1")
        await asyncio.sleep(0.05)

        # Ensure the floor is selected
        elevator = self.controller.elevators[1]
        self.assertIn(Floor("2"), elevator.selected_floors)

        # Now deselect the floor
        await self.controller.handle_message("deselect_floor@2#1")
        await asyncio.sleep(0.05)

        # Verify the floor is deselected
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

    async def test_call_elevator(self):
        await self.controller.call_elevator(Floor("2"), Direction.UP)
        self.assertEqual(self.controller.elevators[1].current_floor, 2)
        self.assertNotIn((Floor("2"), Direction.UP), self.controller.elevators.requests)

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


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
