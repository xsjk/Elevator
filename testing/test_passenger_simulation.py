import asyncio
import unittest

from common import Controller
from passenger import Passenger, generate_passengers


class PassengerSimulationTest(unittest.IsolatedAsyncioTestCase):
    """Test elevator system using passenger state machine simulation"""

    async def asyncSetUp(self):
        self.controller = Controller()
        self.controller.start()
        self.queue = asyncio.Queue()
        self.message_task = asyncio.create_task(self.process_passenger_requests())

    async def asyncTearDown(self):
        if self.message_task:
            self.message_task.cancel()
            await self.message_task
        await self.controller.stop()

    async def process_passenger_requests(self):
        try:
            while True:
                msg = await self.queue.get()
                self.controller.handle_message_task(msg)
                self.queue.task_done()

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

                # Test completion check
                if completed == len(passengers):
                    break

        try:
            async with asyncio.timeout(timeout):
                await process_controller_messages()
        except asyncio.TimeoutError:
            self.fail(f"Simulation timed out after {timeout} seconds. Active passengers: {len(active)}")

    async def test_single_passenger_up(self):
        passenger = Passenger(1, 3, "P1", queue=self.queue)
        await self.simulate_passengers([passenger], timeout=5 + 2 * 3 + 1 + 0.5)

    async def test_single_passenger_down(self):
        passenger = Passenger(3, 1, "P2", queue=self.queue)
        await self.simulate_passengers([passenger], timeout=2 * 3 + 5 + 2 * 3 + 1 + 0.5)

    async def test_multiple_passengers_same_elevator(self):
        p1 = Passenger(1, 3, "P1", queue=self.queue)
        p2 = Passenger(2, 3, "P2", queue=self.queue)
        await self.simulate_passengers([p1, p2], timeout=5 + 2 * 3 + 1 + 0.5)

    async def test_multiple_passengers_different_directions(self):
        p1 = Passenger(1, 3, "P1", queue=self.queue)
        p2 = Passenger(3, -1, "P2", queue=self.queue)
        await self.simulate_passengers([p1, p2], timeout=2 * 3 + 5 + 3 * 3 + 1 + 0.5)

    async def test_complex_passenger_scenario_1(self):
        p1 = Passenger(-1, 3, "P1", queue=self.queue)
        p2 = Passenger(3, 1, "P2", queue=self.queue)
        await self.simulate_passengers([p1, p2], timeout=2 * 3 + 5 + 2 * 3 + 1 + 0.5)

    async def test_complex_passenger_scenario_2(self):
        p1 = Passenger(1, 3, "P1", queue=self.queue)
        p2 = Passenger(2, 3, "P2", queue=self.queue)
        p3 = Passenger(2, -1, "P3", queue=self.queue)
        await self.simulate_passengers([p1, p2, p3], timeout=5 + 3 + 5 + 3 + 1 + 0.5)

    # async def test_generate_passengers_function(self):
    #     count = 10
    #     ps = generate_passengers(10, self.queue)
    #     self.assertEqual(len(ps), count)
    #     await self.simulate_passengers(ps, timeout=100.0)


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
