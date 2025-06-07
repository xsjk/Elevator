import asyncio
import random
import unittest

from common import GUIAsyncioTestCase, logger, Floor
from passenger import Passenger
from itertools import combinations


class PassengerSimulationTest(GUIAsyncioTestCase):
    """Test elevator system using passenger state machine simulation"""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.passenger_msg = asyncio.Queue()
        self.message_task = asyncio.create_task(self.process_passenger_requests())

    async def asyncTearDown(self):
        if self.message_task:
            self.message_task.cancel()
            await self.message_task
        await super().asyncTearDown()

    async def process_passenger_requests(self):
        try:
            while True:
                msg = await self.passenger_msg.get()
                self.controller.handle_message_task(msg)
                self.passenger_msg.task_done()

        except asyncio.CancelledError:
            pass

    async def simulate_passengers(self, passengers: list[Passenger], timeout: float | None = None):
        """
        Simulate passenger behavior and track completion

        Args:
            passengers: List of passengers to simulate
            queue: Queue for passenger messages
            timeout: Maximum time to wait for completion (seconds)

        Returns:
            True if all passengers reached their destinations
        """
        # Setup initial data for tracking
        active = set(passengers)
        completed = 0

        # Implement timeout for the message processing loop
        async def process_controller_messages():
            nonlocal completed

            async for message in self.controller.messages():
                # Process message for each active passenger
                for passenger in list(active):
                    if passenger.handle_message(message):
                        completed += 1
                        active.remove(passenger)
                        logger.info(f"Passenger: {passenger.name} completed. \t{completed}/{len(passengers)}")

                # Test completion check
                if completed == len(passengers):
                    break

        try:
            async with asyncio.timeout(timeout):
                await process_controller_messages()
        except TimeoutError:
            self.fail(f"Simulation timed out after {timeout} seconds. Active passengers: {len(active)}")

    async def test_single_passenger_up(self):
        passenger = Passenger(1, 3, "P1", queue=self.passenger_msg)
        await self.simulate_passengers([passenger], timeout=5 + 2 * 3 + 1 + 0.5)

    async def test_single_passenger_down(self):
        passenger = Passenger(3, 1, "P2", queue=self.passenger_msg)
        await self.simulate_passengers([passenger], timeout=2 * 3 + 5 + 2 * 3 + 1 + 0.7)

    async def test_multiple_passengers_same_elevator(self):
        p1 = Passenger(1, 3, "P1", queue=self.passenger_msg)
        p2 = Passenger(2, 3, "P2", queue=self.passenger_msg)
        await self.simulate_passengers([p1, p2], timeout=5 + 2 * 3 + 1 + 0.5)

    async def test_multiple_passengers_different_directions(self):
        p1 = Passenger(1, 3, "P1", queue=self.passenger_msg)
        p2 = Passenger(3, -1, "P2", queue=self.passenger_msg)
        await self.simulate_passengers([p1, p2], timeout=2 * 3 + 5 + 3 * 3 + 1 + 0.8)

    async def test_complex_passenger_scenario_1(self):
        p1 = Passenger(-1, 3, "P1", queue=self.passenger_msg)
        p2 = Passenger(3, 1, "P2", queue=self.passenger_msg)
        await self.simulate_passengers([p1, p2], timeout=2 * 3 + 5 + 2 * 3 + 1 + 0.7)

    async def test_complex_passenger_scenario_2(self):
        p1 = Passenger(1, 3, "P1", queue=self.passenger_msg)
        p2 = Passenger(2, 3, "P2", queue=self.passenger_msg)
        p3 = Passenger(2, -1, "P3", queue=self.passenger_msg)
        await self.simulate_passengers([p1, p2, p3], timeout=5 + 3 + 5 + 3 + 1 + 0.8)

    async def test_complete_condition(self):
        await self.controller.set_elevator_count(1)
        ps = []
        for start_floor, end_floor in combinations([Floor(i) for i in (-1, 1, 2, 3)], 2):
            ps.append(Passenger(start_floor, end_floor, f"P({start_floor}, {end_floor})", queue=self.passenger_msg))
            ps.append(Passenger(end_floor, start_floor, f"P({end_floor}, {start_floor})", queue=self.passenger_msg))

        await self.simulate_passengers(ps)

    async def test_complete_condition_reversed(self):
        await self.controller.set_elevator_count(1)
        ps = []
        for start_floor, end_floor in combinations([Floor(i) for i in (3, 2, 1, -1)], 2):
            ps.append(Passenger(start_floor, end_floor, f"P({start_floor}, {end_floor})", queue=self.passenger_msg))
            ps.append(Passenger(end_floor, start_floor, f"P({end_floor}, {start_floor})", queue=self.passenger_msg))

        await self.simulate_passengers(ps)

    async def test_random_passengers(self):
        self.controller.set_config(
            floor_travel_duration=0.1,
            door_stay_duration=0.1,
            door_move_duration=0.1,
        )

        passenger_configs = []
        for c in combinations([Floor(i) for i in (-1, 1, 2, 3)], 2):
            passenger_configs.extend([c, c[::-1]])

        for i in range(1, 7):
            await self.controller.set_elevator_count(i)

            random.shuffle(passenger_configs)
            ps = [Passenger(start, end, f"P({start}, {end})", queue=self.passenger_msg) for start, end in passenger_configs]
            await self.simulate_passengers(ps, timeout=30)


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
