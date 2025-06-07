import asyncio
import unittest

from passenger import Passenger, PassengerState, generate_passengers


class TestPassenger(unittest.IsolatedAsyncioTestCase):
    async def test_initial_call_and_state(self):
        """Passenger enqueues initial call and not finished immediately"""
        queue = asyncio.Queue()
        passenger = Passenger(1, 3, "P1", queue=queue)

        self.assertFalse(passenger.finished)
        self.assertEqual(passenger.state, PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR)
        self.assertEqual(passenger.current_floor, 1)
        self.assertEqual(passenger.matching_signal, "up_floor_arrived@1")
        self.assertEqual(passenger.direction, "up")
        self.assertEqual(passenger.name, "P1")

        # should have initial call request
        message = await queue.get()
        self.assertEqual(message, "call_up@1")

    async def test_handle_full_flow(self):
        """Passenger handles arrival, board, request, and leave"""
        queue = asyncio.Queue()
        passenger = Passenger(2, 5, "P2", queue=queue)

        # consume initial call
        self.assertFalse(passenger.finished)
        await queue.get()
        self.assertEqual(passenger.state, PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR)
        self.assertEqual(passenger.current_floor, 2)

        # simulate elevator arrives at passenger start floor
        arrival_msg = f"{passenger.matching_signal}#7"
        done = passenger.handle_message(arrival_msg)
        self.assertFalse(done)

        # simulate door opens at elevator
        done = passenger.handle_message("door_opened#7")
        self.assertFalse(done)
        # passenger should have requested target floor
        select_msg = await queue.get()
        self.assertEqual(select_msg, "select_floor@5#7")

        # simulate elevator arrives at target floor
        arrival_target = "floor_arrived@5#7"
        done = passenger.handle_message(arrival_target)
        self.assertFalse(done)

        # simulate door open at target floor
        done = passenger.handle_message("door_opened#7")
        self.assertTrue(done)

    async def test_downward_travel(self):
        """Test passenger traveling downward"""
        queue = asyncio.Queue()
        passenger = Passenger(5, 2, "P3", queue=queue)

        # Check initial state
        self.assertEqual(passenger.direction, "down")
        self.assertEqual(passenger.matching_signal, "down_floor_arrived@5")
        await queue.get()  # Consume initial call

        # Elevator arrives
        passenger.handle_message("down_floor_arrived@5#3")
        # Door opens, passenger enters
        passenger.handle_message("door_opened#3")
        # Check if passenger requested floor
        request = await queue.get()
        self.assertEqual(request, "select_floor@2#3")

        # Arrival at target floor
        passenger.handle_message("floor_arrived@2#3")
        self.assertEqual(passenger.state, PassengerState.IN_ELEVATOR_AT_TARGET_FLOOR)

        # Door opens at target, passenger exits
        done = passenger.handle_message("door_opened#3")
        self.assertTrue(done)
        self.assertEqual(passenger.state, PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR)

    async def test_already_at_target(self):
        """Test passenger already at target floor"""
        queue = asyncio.Queue()
        passenger = Passenger(3, 3, "P4", queue=queue)

        self.assertTrue(passenger.finished)
        # No messages should be in queue since already at target
        self.assertEqual(queue.qsize(), 0)

    async def test_wrong_elevator_arrival(self):
        """Test passenger ignores wrong elevator"""
        queue = asyncio.Queue()
        passenger = Passenger(2, 4, "P5", queue=queue)
        await queue.get()  # Consume initial call

        # Wrong direction elevator
        passenger.handle_message("down_floor_arrived@2#5")
        self.assertEqual(passenger._elevator_code, -1)  # Should not assign elevator

        # Right direction but wrong floor
        passenger.handle_message("up_floor_arrived@3#6")
        self.assertEqual(passenger._elevator_code, -1)

        # Correct elevator arrives
        passenger.handle_message("up_floor_arrived@2#7")
        self.assertEqual(passenger._elevator_code, 7)

    async def test_multiple_state_transitions(self):
        """Test all state transitions"""
        queue = asyncio.Queue()
        passenger = Passenger(1, 3, "P6", queue=queue)
        await queue.get()  # Consume initial call

        # Initial state
        self.assertEqual(passenger.state, PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR)

        # Elevator arrives
        passenger.handle_message("up_floor_arrived@1#2")
        self.assertEqual(passenger._elevator_code, 2)

        # Door opens, passenger enters
        passenger.handle_message("door_opened#2")
        self.assertEqual(passenger.state, PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR)
        await queue.get()  # Consume floor request

        # Test floor arrival at non-target floor
        passenger.handle_message("floor_arrived@2#2")
        self.assertEqual(passenger.state, PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR)
        self.assertEqual(passenger.current_floor, 1)  # Floor shouldn't change

        # Arrival at target floor
        passenger.handle_message("floor_arrived@3#2")
        self.assertEqual(passenger.state, PassengerState.IN_ELEVATOR_AT_TARGET_FLOOR)
        self.assertEqual(passenger.current_floor, 3)

        # Door opens at target, passenger exits
        passenger.handle_message("door_opened#2")
        self.assertEqual(passenger.state, PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR)
        self.assertTrue(passenger.finished)

    async def test_door_opened_wrong_elevator(self):
        """Test passenger ignores door open from wrong elevator"""
        queue = asyncio.Queue()
        passenger = Passenger(1, 4, "P7", queue=queue)
        await queue.get()  # Consume initial call

        # Elevator arrives
        passenger.handle_message("up_floor_arrived@1#3")
        self.assertEqual(passenger._elevator_code, 3)

        # Wrong elevator door opens
        passenger.handle_message("door_opened#4")
        self.assertEqual(passenger.state, PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR)

        # Correct elevator door opens
        passenger.handle_message("door_opened#3")
        self.assertEqual(passenger.state, PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR)


class TestGeneratePassengers(unittest.TestCase):
    def test_generate_passengers_count_and_queue(self):
        """generate_passengers yields correct count and initial calls"""
        queue = asyncio.Queue()
        count = 4
        passengers = generate_passengers(count, queue)
        self.assertEqual(len(passengers), count)
        # queue should have initial call for each passenger
        self.assertEqual(queue.qsize(), count)

    def test_generate_unique_start_target(self):
        """Test generated passengers have different start and target floors"""
        queue = asyncio.Queue()
        passengers = generate_passengers(20, queue)

        for p in passengers:
            self.assertNotEqual(p.start_floor, p.target_floor)
            self.assertIn(p.start_floor, [-1, 1, 2, 3])
            self.assertIn(p.target_floor, [-1, 1, 2, 3])

    def test_passenger_names(self):
        """Test passenger names are generated correctly"""
        queue = asyncio.Queue()
        passengers = generate_passengers(5, queue)

        expected_names = ["P1", "P2", "P3", "P4", "P5"]
        names = [p.name for p in passengers]
        self.assertEqual(set(names), set(expected_names))


if __name__ == "__main__":
    unittest.main()
