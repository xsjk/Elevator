import asyncio
import unittest
from math import comb

from common import Direction, Elevators, FloorAction


class TestElevators(unittest.IsolatedAsyncioTestCase):
    """Test cases for the Elevators class"""

    async def asyncSetUp(self):
        """Set up test environment before each test"""
        self.queue = asyncio.Queue()
        self.elevator_count = 3
        self.elevators = Elevators(
            count=self.elevator_count,
            queue=self.queue,
            floor_travel_duration=1.0,
            accelerate_duration=1.0,
            door_move_duration=3.0,
            door_stay_duration=3.0,
        )

        # Start all elevators
        for elevator in self.elevators.values():
            elevator.start()

    async def asyncTearDown(self):
        """Clean up after each test"""
        for elevator in self.elevators.values():
            await elevator.stop()

    async def test_initialization(self):
        """Test that Elevators initializes correctly"""
        # Check the number of elevators
        self.assertEqual(len(self.elevators), self.elevator_count)

        # Check that IDs are assigned correctly
        self.assertEqual(set(self.elevators.keys()), set(range(1, self.elevator_count + 1)))

        # Check that eid2request and request2eid are initialized correctly
        self.assertEqual(len(self.elevators.eid2request), self.elevator_count)
        self.assertEqual(len(self.elevators.request2eid), 0)

        # Check elevator parameters
        for elevator in self.elevators.values():
            self.assertEqual(elevator.floor_travel_duration, 1.0)
            self.assertEqual(elevator.accelerate_duration, 1.0)
            self.assertEqual(elevator.door_move_duration, 3.0)
            self.assertEqual(elevator.door_stay_duration, 3.0)
            self.assertEqual(elevator.queue, self.queue)

    async def test_commit_floor(self):
        """Test committing a floor to an elevator"""
        eid = 1
        request = FloorAction(3, Direction.UP)

        # Commit the request
        event = self.elevators.commit_floor(eid, request)

        # Check that the request was properly assigned
        self.assertEqual(self.elevators.request2eid[request], eid)
        self.assertIn(request, self.elevators.eid2request[eid])

        # Check that the event is created
        self.assertIsInstance(event, asyncio.Event)
        self.assertFalse(event.is_set())

        # Check that the elevator has the request
        self.assertIn(request, self.elevators[eid].target_floor_chains)

    async def test_cancel_commit(self):
        """Test canceling a committed floor request"""
        eid = 2
        request = FloorAction(4, Direction.DOWN)

        # Commit the request then cancel it
        self.elevators.commit_floor(eid, request)
        event = self.elevators.cancel_commit(request)

        # Check that the request was properly removed
        self.assertNotIn(request, self.elevators.request2eid)
        self.assertNotIn(request, self.elevators.eid2request[eid])

        # Check that the event is returned
        self.assertIsInstance(event, asyncio.Event)

        # Check that the elevator no longer has the request
        self.assertNotIn(request, self.elevators[eid].target_floor_chains)

    async def test_requests_property(self):
        """Test the requests property"""
        # Initially no requests
        self.assertEqual(len(self.elevators.requests), 0)

        # Add some requests
        request1 = FloorAction(2, Direction.UP)
        request2 = FloorAction(5, Direction.DOWN)

        self.elevators.commit_floor(1, request1)
        self.elevators.commit_floor(2, request2)

        # Check that requests property returns both requests
        self.assertEqual(self.elevators.requests, {request1, request2})

    async def test_eids_property(self):
        """Test the eids property"""
        # Check that eids property returns all elevator IDs
        self.assertEqual(self.elevators.eids, set(range(1, self.elevator_count + 1)))

    async def test_copy(self):
        """Test the copy method"""
        # Add some requests to make state more complex
        self.elevators.commit_floor(1, FloorAction(2, Direction.UP))
        self.elevators.commit_floor(2, FloorAction(3, Direction.DOWN))

        # Make a copy
        copied_elevators = self.elevators.copy()

        # Verify it's a different object
        self.assertIsNot(copied_elevators, self.elevators)

        # Verify the state was copied
        self.assertEqual(copied_elevators.request2eid, self.elevators.request2eid)
        self.assertEqual(len(copied_elevators.eid2request), len(self.elevators.eid2request))
        for eid in self.elevators.eid2request:
            self.assertEqual(copied_elevators.eid2request[eid], self.elevators.eid2request[eid])

    async def test_plan_to_assignment(self):
        """Test the _plan_to_assignment method"""
        # Add some requests
        request1 = FloorAction(2, Direction.UP)
        request2 = FloorAction(3, Direction.DOWN)

        self.elevators.commit_floor(1, request1)
        self.elevators.commit_floor(2, request2)

        # Create a plan (reassign both requests to elevator 3)
        plan = (3, 3)

        # Convert to assignment
        assignment = self.elevators._plan_to_assignment(plan)

        # Check assignment structure
        self.assertEqual(len(assignment), self.elevator_count)
        self.assertEqual(assignment[3], {request1, request2})
        self.assertEqual(assignment[1], set())
        self.assertEqual(assignment[2], set())

    async def test_apply_assignment(self):
        """Test applying a new assignment of requests"""
        # Set up initial state
        request1 = FloorAction(2, Direction.UP)
        request2 = FloorAction(3, Direction.DOWN)
        request3 = FloorAction(4, Direction.UP)

        self.elevators.commit_floor(2, request1)
        self.elevators.commit_floor(2, request2)
        self.elevators.commit_floor(2, request3)

        # Create a new assignment: move request1 to elevator 3, keep request2 at elevator 2, add request3 to elevator 1
        new_assignment = {1: {request3}, 2: {request2}, 3: {request1}}

        # Apply the assignment
        self.elevators.reassign(new_assignment)

        # Check that the assignment was applied correctly
        self.assertEqual(self.elevators.eid2request, new_assignment)
        self.assertEqual(self.elevators.request2eid[request1], 3)
        self.assertEqual(self.elevators.request2eid[request2], 2)
        self.assertEqual(self.elevators.request2eid[request3], 1)

        # Check that each elevator has the correct requests
        self.assertIn(request3, self.elevators[1].target_floor_chains)
        self.assertIn(request2, self.elevators[2].target_floor_chains)
        self.assertIn(request1, self.elevators[3].target_floor_chains)

        self.assertNotIn(request1, self.elevators[1].target_floor_chains)

    async def test_optimal_elevator_selection(self):
        """Test that the system selects the optimal elevator for a request based on estimated duration."""
        # Setup elevators in different positions
        self.elevators[1].current_floor = 1
        self.elevators[2].current_floor = 5
        self.elevators[3].current_floor = 10

        # Request to floor 3 - elevator 1 should be closest
        request = FloorAction(3, Direction.UP)
        eid, duration = self.elevators.estimate_total_duration(request)
        self.assertEqual(eid, 1)  # Elevator 1 should be selected

        # Add existing requests to elevator 1 to make it busy
        self.elevators.commit_floor(1, FloorAction(10, Direction.UP))

        # Now elevator 2 should be the optimal choice for floor 3
        eid, _ = self.elevators.estimate_total_duration(request)
        self.assertEqual(eid, 2)  # Elevator 2 should now be selected

    async def test_concurrent_requests(self):
        """Test handling multiple concurrent requests efficiently."""
        # Setup initial state
        self.elevators[1].current_floor = 1
        self.elevators[2].current_floor = 5
        self.elevators[3].current_floor = 9

        # Create several requests
        requests = [
            FloorAction(3, Direction.UP),
            FloorAction(6, Direction.DOWN),
            FloorAction(8, Direction.UP),
            FloorAction(2, Direction.DOWN),
        ]

        # Commit each request to the optimal elevator
        for request in requests:
            eid, _ = self.elevators.estimate_total_duration(request)
            self.elevators.commit_floor(eid, request)

        # Verify distribution - each elevator should have at least one request
        request_counts = [len(self.elevators.eid2request[eid]) for eid in self.elevators.eids]
        self.assertTrue(all(count > 0 for count in request_counts))

        # Verify total requests match
        self.assertEqual(sum(request_counts), len(requests))

    async def test_complex_request_patterns(self):
        """Test handling complex patterns of requests like those in peak hours."""
        # Setup elevators at different floors
        self.elevators[1].current_floor = 1
        self.elevators[2].current_floor = 5
        self.elevators[3].current_floor = 10

        # Create a complex pattern of requests (simulating peak hour)
        up_requests = [FloorAction(i, Direction.UP) for i in range(1, 5)]
        down_requests = [FloorAction(i, Direction.DOWN) for i in range(6, 11)]

        # Commit all requests
        all_requests = up_requests + down_requests
        for request in all_requests:
            eid, _ = self.elevators.estimate_total_duration(request)
            self.elevators.commit_floor(eid, request)

        # Verify all requests were assigned
        self.assertEqual(len(self.elevators.requests), len(all_requests))

        # Check assignment distribution
        up_counts = {eid: sum(1 for r in self.elevators.eid2request[eid] if r.direction == Direction.UP) for eid in self.elevators.eids}
        down_counts = {eid: sum(1 for r in self.elevators.eid2request[eid] if r.direction == Direction.DOWN) for eid in self.elevators.eids}

        # Verify reasonable distribution - up requests should go to lower elevators
        # and down requests to higher elevators for efficiency
        self.assertTrue(up_counts[1] >= up_counts[3])
        self.assertTrue(down_counts[3] >= down_counts[1])

    async def test_handle_request_cancellation(self):
        """Test handling request cancellations correctly."""
        # Add several requests
        request1 = FloorAction(2, Direction.UP)
        request2 = FloorAction(5, Direction.DOWN)
        request3 = FloorAction(8, Direction.UP)

        self.elevators.commit_floor(1, request1)
        self.elevators.commit_floor(2, request2)
        self.elevators.commit_floor(3, request3)

        # Initial state check
        self.assertEqual(len(self.elevators.requests), 3)

        # Cancel the middle request
        event = self.elevators.cancel_commit(request2)
        self.assertIsNotNone(event)
        assert event is not None

        # Verify the request was removed
        self.assertEqual(len(self.elevators.requests), 2)
        self.assertNotIn(request2, self.elevators.request2eid)
        self.assertNotIn(request2, self.elevators.eid2request[2])

        # Verify the event was returned and not set
        self.assertIsInstance(event, asyncio.Event)
        self.assertFalse(event.is_set())

        # Verify other requests are still there
        self.assertIn(request1, self.elevators.request2eid)
        self.assertIn(request3, self.elevators.request2eid)

    async def test_assignment_event_handling(self):
        """Test that events are properly maintained during reassignment."""
        # Create requests and commit them
        request1 = FloorAction(3, Direction.UP)
        request2 = FloorAction(7, Direction.DOWN)

        event1 = self.elevators.commit_floor(1, request1)
        event2 = self.elevators.commit_floor(2, request2)

        # Create a new assignment swapping the requests
        new_assignment = {1: {request2}, 2: {request1}, 3: set()}

        # Apply the reassignment
        self.elevators.reassign(new_assignment)

        # Complete request1 on elevator 2
        self.elevators[2].pop_target()

        # Verify the event was set
        self.assertTrue(event1.is_set())

        # Complete request2 on elevator 1
        self.elevators[1].pop_target()

        # Verify the event was set
        self.assertTrue(event2.is_set())

    async def test_all_possible_assignments(self):
        """Test generating all possible request-to-elevator assignments."""
        # Create some requests
        request1 = FloorAction(2, Direction.UP)
        request2 = FloorAction(5, Direction.DOWN)
        request3 = FloorAction(8, Direction.UP)

        # Commit them to elevators
        self.elevators.commit_floor(1, request1)
        self.elevators.commit_floor(2, request2)
        self.elevators.commit_floor(1, request3)

        # Get all possible assignments
        assignments = list(self.elevators.all_possible_assignments)

        # With 3 elevators and 2 requests, there should be 3^2 = 9 possible assignments

        n_elevators = len(self.elevators)
        n_requests = len(self.elevators.requests)
        n_assignments = len(assignments)
        self.assertEqual(n_assignments, comb(n_elevators + n_requests - 1, n_requests))

    async def test_elevator_parameters(self):
        """Test that elevator parameters are correctly passed to all elevators."""
        # Create a new Elevators instance with custom parameters
        custom_elevators = Elevators(
            count=2,
            queue=asyncio.Queue(),
            floor_travel_duration=2.0,
            accelerate_duration=0.5,
            door_move_duration=1.5,
            door_stay_duration=2.5,
        )

        # Verify parameters were passed to all elevators
        for elevator in custom_elevators.values():
            self.assertEqual(elevator.floor_travel_duration, 2.0)
            self.assertEqual(elevator.accelerate_duration, 0.5)
            self.assertEqual(elevator.door_move_duration, 1.5)
            self.assertEqual(elevator.door_stay_duration, 2.5)

        # Clean up
        for elevator in custom_elevators.values():
            elevator.start()
            await elevator.stop()


if __name__ == "__main__":
    unittest.main()
