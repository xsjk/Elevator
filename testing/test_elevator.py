import asyncio
import unittest

from common import Direction, DoorDirection, Elevator, ElevatorState, FloorAction


class TestElevator(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.elevator = Elevator(id=1)
        self.elevator.start()

    async def asyncTearDown(self):
        await self.elevator.stop()

    async def test_accelerate_distance(self):
        self.assertEqual(self.elevator.accelerate_distance, 0.5)

    async def test_max_speed(self):
        self.assertEqual(self.elevator.max_speed, 1.0)

    async def test_acceleration(self):
        self.assertEqual(self.elevator.acceleration, 1.0)

    async def test_commit_door(self):
        await self.elevator.commit_door(DoorDirection.OPEN)
        self.assertTrue(self.elevator.door_open)

    # test_commit_floor
    # target_direction = IDLE
    # TestCase 1
    async def test_commit_floor_case1(self):
        self.elevator.current_floor = 2
        self.elevator.target_floor_chains.clear()
        event = self.elevator.commit_floor(2, Direction.IDLE)
        await event.wait()
        self.assertTrue(self.elevator.door_open)
        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "floor_arrived@2#1")

    # TestCase 2
    async def test_commit_floor_case2(self):
        self.elevator.current_floor = 2
        self.elevator.target_floor_chains.direction = Direction.UP
        event = self.elevator.commit_floor(2, Direction.UP)
        await event.wait()
        self.assertTrue(self.elevator.door_open)
        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "up_floor_arrived@2#1")

    # TestCase 3
    async def test_commit_floor_case3(self):
        self.elevator.current_floor = 2
        self.elevator.target_floor_chains.direction = Direction.DOWN
        event = self.elevator.commit_floor(2, Direction.DOWN)
        await event.wait()
        self.assertTrue(self.elevator.door_open)
        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "down_floor_arrived@2#1")

    # target_floor_chains.direction
    # TestCase 4: IDLE
    async def test_commit_floor_case4(self):
        self.elevator.current_floor = 1
        self.elevator.target_floor_chains.direction = Direction.IDLE
        event = self.elevator.commit_floor(3, Direction.DOWN)
        self.assertEqual(self.elevator.target_floor_chains.direction, Direction.DOWN)
        self.assertIn(FloorAction(3, Direction.DOWN), self.elevator.target_floor_chains.current_chain)

    # TestCase 5: UP   if-if
    async def test_commit_floor_case5(self):
        self.elevator.current_floor = 2
        self.elevator.target_floor_chains.direction = Direction.UP
        event = self.elevator.commit_floor(3, Direction.UP)
        self.assertIn(FloorAction(3, Direction.UP), self.elevator.target_floor_chains.current_chain)

    # TestCase 6: UP   if-else
    async def test_commit_floor_case6(self):
        self.elevator.current_floor = 2
        self.elevator.target_floor_chains.direction = Direction.UP
        event = self.elevator.commit_floor(1, Direction.UP)
        self.assertIn(FloorAction(1, Direction.UP), self.elevator.target_floor_chains.future_chain)

    # TestCase 7: DOWN else
    async def test_commit_floor_case7(self):
        self.elevator.current_floor = 2
        self.elevator.target_floor_chains.direction = Direction.DOWN
        event = self.elevator.commit_floor(1, Direction.UP)
        self.assertIn(FloorAction(1, Direction.UP), self.elevator.target_floor_chains.next_chain)

    async def test_cancel_commit(self):
        event = self.elevator.commit_floor(4, Direction.UP)
        self.elevator.cancel_commit(4, Direction.UP)
        await event.wait()
        self.assertTrue(event.is_set())

    async def test_arrival_summary(self):
        self.elevator.current_floor = 1
        self.elevator.commit_floor(5, Direction.UP)
        n_floors, n_stops = self.elevator.arrival_summary(5, Direction.UP)
        self.assertEqual(n_floors, 4.0)
        self.assertEqual(n_stops, 0)

    def test_estimate_door_close_time_precise(self):
        self.elevator._door_last_state_change_time = self.elevator.event_loop.time() - 1.0

        # TestCase 1
        self.elevator.state = ElevatorState.OPENING_DOOR
        close_time_1 = self.elevator.estimate_door_close_time()
        self.assertAlmostEqual(close_time_1, 8.0, delta=0.1)

        # TestCase 2
        self.elevator.state = ElevatorState.STOPPED_DOOR_OPENED
        close_time_2 = self.elevator.estimate_door_close_time()
        self.assertAlmostEqual(close_time_2, 5.0, delta=0.1)

        # TestCase 3
        self.elevator.state = ElevatorState.CLOSING_DOOR
        close_time_2 = self.elevator.estimate_door_close_time()
        self.assertAlmostEqual(close_time_2, 2.0, delta=0.1)

    def test_estimate_door_open_time_precise(self):
        self.elevator._door_last_state_change_time = self.elevator.event_loop.time() - 1.0

        # TestCase 1
        self.elevator.state = ElevatorState.OPENING_DOOR
        open_time_1 = self.elevator.estimate_door_open_time()
        self.assertAlmostEqual(open_time_1, 5.0, delta=0.1)

        # TestCase 2
        self.elevator.state = ElevatorState.STOPPED_DOOR_OPENED
        open_time_2 = self.elevator.estimate_door_open_time()
        self.assertAlmostEqual(open_time_2, 2.0, delta=0.1)

        # TestCase 3
        self.elevator.state = ElevatorState.CLOSING_DOOR
        close_time_2 = self.elevator.estimate_door_open_time()
        self.assertAlmostEqual(close_time_2, 4.0, delta=0.1)

    async def test_pop_target(self):
        # TestCase 1
        with self.assertRaises(IndexError):
            target = self.elevator.pop_target()

        # TestCase 2
        event = self.elevator.commit_floor(3, Direction.IDLE)
        await asyncio.sleep(0.1)
        target = self.elevator.pop_target()
        self.assertEqual(target, FloorAction(3, Direction.IDLE))
        self.assertTrue(event.is_set())

    # TestCase 1 self.current_floor < target_floor
    async def test_move_loop_case1(self):
        event1 = self.elevator.commit_floor(3, Direction.IDLE)
        await asyncio.sleep(2.0)
        self.assertEqual(self.elevator.state, ElevatorState.MOVING_UP)
        self.assertEqual(self.elevator.current_floor, 2)

        await event1.wait()

    # TestCase 2
    async def test_move_loop_case2(self):
        self.elevator.current_floor = 3
        event2 = self.elevator.commit_floor(1, Direction.UP)
        await asyncio.sleep(2.0)
        self.assertEqual(self.elevator.state, ElevatorState.MOVING_DOWN)
        self.assertEqual(self.elevator.current_floor, 2)

        await event2.wait()

    # self.current_floor = target_floor
    # if empty(Case 3, 4, 5)
    # TestCase 3
    async def test_move_loop_case3(self):
        self.elevator.current_floor = 1
        event3 = self.elevator.commit_floor(2, Direction.IDLE)

        await event3.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "floor_arrived@2#1")

    # TestCase 4
    async def test_move_loop_case4(self):
        event4 = self.elevator.commit_floor(2, Direction.UP)

        await event4.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "up_floor_arrived@2#1")

    # TestCase 5
    async def test_move_loop_case5(self):
        event5 = self.elevator.commit_floor(2, Direction.DOWN)

        await event5.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "down_floor_arrived@2#1")

    # else (Case 6, 7, 8, 9, 10)
    # TestCase 6: next_target_floor > self.current_floor
    async def test_move_loop_case6(self):
        event6 = self.elevator.commit_floor(2, Direction.UP)
        event7 = self.elevator.commit_floor(3, Direction.DOWN)

        await event6.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "up_floor_arrived@2#1")

    # TestCase 7: next_target_floor < self.current_floor
    async def test_move_loop_case7(self):
        event7 = self.elevator.commit_floor(3, Direction.DOWN)
        event8 = self.elevator.commit_floor(2, Direction.IDLE)

        await event7.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "down_floor_arrived@3#1")

    # next_target_floor = self.current_floor
    # TestCase 8: direction == Direction.IDLE
    async def test_move_loop_case8(self):
        event8 = self.elevator.commit_floor(2, Direction.IDLE)
        event9 = self.elevator.commit_floor(2, Direction.DOWN)

        await event8.wait()

    # TestCase 9: next_direction == -commited_direction
    async def test_move_loop_case9(self):
        self.elevator.current_floor = 2
        event9 = self.elevator.commit_floor(2, Direction.DOWN)
        event10 = self.elevator.commit_floor(2, Direction.UP)

        await event9.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "down_floor_arrived@2#1")

    # TestCase 10: next_direction == -commited_direction
    async def test_move_loop_case10(self):
        event10 = self.elevator.commit_floor(2, Direction.UP)
        event11 = self.elevator.commit_floor(2, Direction.DOWN)

        await event10.wait()

        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "up_floor_arrived@2#1")

    async def test_door_loop_open(self):
        # TestCase 1
        self.elevator.state = ElevatorState.MOVING_UP
        await self.elevator.commit_door(DoorDirection.OPEN)

        # TestCase 2
        self.elevator.state = ElevatorState.OPENING_DOOR
        await self.elevator.commit_door(DoorDirection.OPEN)

        # TestCase 3
        self.elevator.state = ElevatorState.STOPPED_DOOR_CLOSED
        await self.elevator.commit_door(DoorDirection.OPEN)
        self.assertFalse(self.elevator.door_idle_event.is_set())

        # TestCase 4
        self.elevator.state = ElevatorState.CLOSING_DOOR
        await self.elevator.commit_door(DoorDirection.OPEN)
        await asyncio.sleep(1)
        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "door_opened#1")

        # TestCase 5
        self.elevator.state = ElevatorState.STOPPED_DOOR_OPENED
        await self.elevator.commit_door(DoorDirection.CLOSE)
        await asyncio.sleep(1)
        msg = await self.elevator.queue.get()
        self.assertEqual(msg, "door_closed#1")

    async def test_moving_direction(self):
        self.elevator.state = ElevatorState.MOVING_DOWN
        self.assertEqual(self.elevator.moving_direction, Direction.DOWN)

    async def test_door_open(self):
        # Test Case1
        self.elevator.state = ElevatorState.STOPPED_DOOR_OPENED
        self.assertTrue(self.elevator.door_open)

        # Test Case2
        self.elevator.state = ElevatorState.STOPPED_DOOR_CLOSED
        self.assertFalse(self.elevator.door_open)

    async def test_state(self):
        self.elevator.state = ElevatorState.MOVING_UP
        self.assertEqual(self.elevator.state, ElevatorState.MOVING_UP)

    async def test_next_target_floor(self):
        self.elevator.commit_floor(3, Direction.UP)
        self.assertEqual(self.elevator.next_target_floor, 3)

    async def test_current_floor(self):
        self.elevator.current_floor = 5
        self.assertEqual(self.elevator.current_floor, 5)

    async def test_current_position(self):
        # TestCase 1
        self.elevator.state = ElevatorState.MOVING_UP
        self.assertAlmostEqual(self.elevator.current_position, 1.0, delta=0.1)

        # TestCase 2
        self.elevator.state = ElevatorState.MOVING_DOWN
        self.assertAlmostEqual(self.elevator.current_position, 1.0, delta=0.1)

    async def test_direction_to(self):
        self.elevator.current_floor = 2
        # Test Case1
        self.assertEqual(self.elevator.direction_to(3), Direction.UP)

        # Test Case2
        self.assertEqual(self.elevator.direction_to(2), Direction.IDLE)

        # Test Case3
        self.assertEqual(self.elevator.direction_to(1), Direction.DOWN)

    async def test_position_percentage(self):
        self.elevator._moving_timestamp = self.elevator.event_loop.time() - 1.5
        self.elevator._moving_speed = 1
        self.elevator.state = ElevatorState.MOVING_UP
        p = self.elevator.position_percentage
        self.assertAlmostEqual(p, 1.0, delta=0.2)

    async def test_door_position_percentage(self):
        self.elevator._door_last_state_change_time = self.elevator.event_loop.time() - 1.0

        # TestCase 1
        self.elevator.state = ElevatorState.STOPPED_DOOR_OPENED
        self.assertAlmostEqual(self.elevator.door_position_percentage, 1.0, delta=0.2)

        # TestCase 2
        self.elevator.state = ElevatorState.OPENING_DOOR
        self.assertAlmostEqual(self.elevator.door_position_percentage, 0.5, delta=0.2)

        # TestCase 3
        self.elevator.state = ElevatorState.CLOSING_DOOR
        self.assertAlmostEqual(self.elevator.door_position_percentage, 0.5, delta=0.2)

        # TestCase 4
        self.elevator.state = ElevatorState.STOPPED_DOOR_CLOSED
        self.assertAlmostEqual(self.elevator.door_position_percentage, 0.0, delta=0.2)

    async def test_door_state(self):
        self.elevator.state = ElevatorState.CLOSING_DOOR
        state = self.elevator.door_state
        self.assertEqual(state.name, "CLOSING")

    async def test_commited_direction(self):
        self.elevator.target_floor_chains.direction = Direction.UP
        self.assertEqual(self.elevator.committed_direction, Direction.UP)


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
