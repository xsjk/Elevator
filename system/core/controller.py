import asyncio
import inspect
from dataclasses import dataclass, field
from typing import AsyncGenerator

from ..utils.common import Direction, DoorDirection, ElevatorId, Event, Floor, FloorAction, FloorLike, Strategy
from ..utils.event_bus import event_bus
from .elevator import Elevator, Elevators, logger


@dataclass
class Config:
    floor_travel_duration: float = 3.0  # Time for elevator to travel between floors when running at max speed
    accelerate_duration: float = 3.0  # Time for elevator to accelerate (seconds)
    door_move_duration: float = 1.0  # Time for elevator door to move (seconds)
    door_stay_duration: float = 3.0  # Time elevator door remains open (seconds)
    floors: tuple[str, ...] = ("-1", "1", "2", "3")  # Floors in the building
    default_floor: Floor = Floor(1)  # Default floor to start from
    elevator_count: int = 2  # Number of elevators in the building
    strategy: Strategy = Strategy.OPTIMAL


type assignmentType = dict[ElevatorId, set[FloorAction]]  # Type alias for assignment dictionary


@dataclass
class Controller:
    config: Config = field(default_factory=Config)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Event queue for inter-component communication
    message_tasks: dict[str, asyncio.Task] = field(default_factory=dict)  # Tasks for handling messages, each task should handle asyncio.CancelledError in its implementation
    _started: bool = False  # Flag to indicate if the controller has been started

    def __post_init__(self):
        self.elevators = Elevators(
            count=self.config.elevator_count,
            queue=self.queue,
            floor_travel_duration=self.config.floor_travel_duration,
            accelerate_duration=self.config.accelerate_duration,
            door_move_duration=self.config.door_move_duration,
            door_stay_duration=self.config.door_stay_duration,
        )

    def set_config(self, **kwargs):
        for key, value in kwargs.items():
            # Special handling for elevator count
            if key == "elevator_count":
                self.set_elevator_count(value)
                continue

            # Other configuration keys
            if hasattr(Config, key):
                if getattr(self.config, key) == value:
                    continue
                setattr(self.config, key, value)
                if hasattr(Elevator, key):
                    for elevator in self.elevators.values():
                        setattr(elevator, key, value)
            else:
                raise ValueError(f"Controller: Invalid configuration key '{key}'")

    def set_elevator_count(self, count: int):
        if count < 1:
            raise ValueError("Controller: Elevator count must be at least 1")

        # keep the existing elevators if count is less than current
        if count < len(self.elevators):
            for i in range(count + 1, len(self.elevators) + 1):
                e = self.elevators.pop(i)
                requests = self.elevators.eid2request.pop(e.id)
                # TODO: call elevators
                logger.warning(f"Requests {requests} for elevator {e.id} will be lost, elevator will be stopped")
                if e.started:
                    self.event_loop.create_task(e.stop(), name=f"StopElevator-{e.id} {__file__}:{inspect.stack()[0].lineno}")

        # add new elevators if count is more than current
        elif count > len(self.elevators):
            for i in range(len(self.elevators) + 1, count + 1):
                self.elevators[i] = Elevator(
                    id=i,
                    queue=self.queue,
                    floor_travel_duration=self.config.floor_travel_duration,
                    accelerate_duration=self.config.accelerate_duration,
                    door_move_duration=self.config.door_move_duration,
                    door_stay_duration=self.config.door_stay_duration,
                )
                self.elevators.eid2request[i] = set()
                if self._started:
                    self.elevators[i].start()

        self.config.elevator_count = count

    @property
    def started(self) -> bool:
        for e in self.elevators.values():
            assert e.started == self._started, f"Controller: Elevator {e.id} started state mismatch: {e.started} != {self._started}"
        return self._started

    async def reset(self):
        await self.stop()

        assert len(self.elevators.requests) == 0
        for actions in self.elevators.eid2request.values():
            assert len(actions) == 0

        # Empty the queue
        while not self.queue.empty():
            self.queue.get_nowait()

        # Reset elevators
        self.__post_init__()

        self.start()

        logger.info("Controller: Elevator system has been reset")

    def start(self, tg: asyncio.TaskGroup | asyncio.AbstractEventLoop | None = None):
        if isinstance(tg, asyncio.AbstractEventLoop):
            self.event_loop = tg
        elif isinstance(tg, asyncio.TaskGroup) and tg._loop is not None:
            self.event_loop = tg._loop
        else:
            self.event_loop = asyncio.get_event_loop()

        if self._started:
            logger.warning("Controller: Already started, ignoring start request")
            return

        for e in self.elevators.values():
            e.start(tg)

        self._started = True

    async def stop(self):
        if not self._started:
            logger.warning("Controller: Not started, ignoring stop request")
            return

        current_task = asyncio.current_task()
        tasks = [t for t in self.message_tasks.values() if t is not current_task]

        for t in tasks:
            t.cancel()

        await asyncio.wait(tasks + [asyncio.create_task(e.stop()) for e in self.elevators.values()])

        assert len(self.elevators.requests) == 0
        for e in self.elevators.values():
            assert len(e.selected_floors) == 0

        self._started = False

    def handle_message_task(self, message: str) -> asyncio.Task:
        if message in self.message_tasks:
            logger.debug(f"Controller: Message task for '{message}' already exists, reusing it")
            return self.message_tasks[message]

        logger.debug(f"Controller: Existing tasks: {list(self.message_tasks)}")

        async def wrapper():
            task = asyncio.current_task()
            assert task is not None
            try:
                await self.handle_message(message)
            except asyncio.CancelledError as e:
                logger.debug(f"Controller: Message task for '{message}' cancelled")
                if task.uncancel() > 0:
                    raise asyncio.CancelledError from e
            except Exception as e:
                logger.error(f"Controller: Error while handling message '{message}': {e}")
                raise e
            finally:
                self.message_tasks.pop(message)

        self.message_tasks[message] = self.event_loop.create_task(wrapper(), name=f"HandleMessage-{message} {__file__}:{inspect.stack()[0].lineno}")
        return self.message_tasks[message]

    async def handle_message(self, message: str):
        if message == "reset":
            await self.reset()

        elif message.startswith("call_up@") or message.startswith("call_down@"):
            direction = Direction.UP if message.startswith("call_up") else Direction.DOWN
            floor = Floor(message.split("@")[1])
            await self.call_elevator(floor, direction)

        elif message.startswith("select_floor@"):
            parts = message.split("@")[1].split("#")
            floor = Floor(parts[0])
            elevator_id = int(parts[1])
            await self.select_floor(floor, elevator_id)

        elif message.startswith("open_door#"):
            elevator_id = int(message.split("#")[1])
            elevator = self.elevators[elevator_id]
            await self.open_door(elevator)

        elif message.startswith("close_door#"):
            elevator_id = int(message.split("#")[1])
            elevator = self.elevators[elevator_id]
            await self.close_door(elevator)

        elif message.startswith("deselect_floor@"):
            parts = message.split("@")[1].split("#")
            floor = Floor(parts[0])
            elevator_id = int(parts[1])
            await self.deselect_floor(floor, elevator_id)

        elif message.startswith("cancel_call_up@") or message.startswith("cancel_call_down@"):
            direction = Direction.UP if message.startswith("cancel_call_up") else Direction.DOWN
            floor = Floor(message.split("@")[1])
            await self.cancel_call(floor, direction)

        else:
            logger.warning(f"Controller: Unrecognized message '{message}'")

    async def get_event_message(self) -> str:
        return await self.queue.get()

    async def messages(self) -> AsyncGenerator[str, None]:
        while True:
            yield await self.get_event_message()

    def optimal_reassign(self, request: FloorAction) -> ElevatorId:
        """
        Find the optimal assignment of elevators to floor requests.
        Uses a combinatorial approach to evaluate different assignments.

        Args:
            directed_target: The new floor request to be considered
        """

        # Create a copy of elevators for simulation
        elevators = self.elevators.copy()

        # Find the best assignment plan by evaluating all possible combinations
        (_, best_elevator_id), _, best_assignment = min(
            (
                (
                    elevators.reassign(assignment).estimate_total_duration(request),
                    i,  # in case the duration is the same, we will use the former assignment
                    assignment,
                )
                for i, assignment in enumerate(self.elevators.most_possible_assignments)
            ),
        )

        # Check if current assignment is already optimal
        if best_assignment == self.elevators.eid2request:
            logger.debug("Controller: Current assignment is already optimal")
        else:
            # Apply changes to real elevators
            self.elevators.reassign(best_assignment)
            logger.debug(f"Controller: Optimized elevator assignments: {best_assignment}")

        return best_elevator_id

    def assign_elevators(self, request: FloorAction) -> ElevatorId:
        match self.config.strategy:
            case Strategy.GREEDY:
                return min(self.elevators, key=lambda i: self.elevators[i].estimate_total_duration(request))
            case Strategy.OPTIMAL:
                # Optimal strategy: reassign elevators based on the optimal assignment
                return self.optimal_reassign(request)

            case _:
                raise ValueError(f"Controller: Invalid strategy {self.config.strategy}")

    async def call_elevator(self, call_floor: FloorLike, call_direction: Direction):
        call_floor = Floor(call_floor)
        assert call_direction in (Direction.UP, Direction.DOWN)
        directed_target = FloorAction(call_floor, call_direction)

        # Check if the call direction is already requested
        if (call_floor, call_direction) in self.elevators.requests:
            logger.info(f"Controller: Floor {call_floor} already requested {call_direction.name.lower()}")
            return

        logger.info(f"Controller: Calling elevator: Floor {call_floor}, Direction {call_direction.name.lower()}")

        eid = self.assign_elevators(directed_target)
        logger.info(f"Controller: Elevator {eid} selected for call at Floor {call_floor} going {call_direction.name.lower()}")

        try:
            await self.elevators.commit_floor(eid, directed_target).wait()
            event_bus.publish(Event.CALL_COMPLETED, call_floor, call_direction)
        except asyncio.CancelledError as e:
            if str(e) != "cancel":
                raise asyncio.CancelledError from e
        finally:
            self.elevators.cancel_commit(directed_target)

    async def cancel_call(self, call_floor: FloorLike, call_direction: Direction):
        call_floor = Floor(call_floor)
        assert call_direction in (Direction.UP, Direction.DOWN)

        directed_target_floor = FloorAction(call_floor, call_direction)
        key = f"call_{call_direction.name.lower()}@{call_floor}"
        assert directed_target_floor in self.elevators.requests
        assert key in self.message_tasks

        # Cancel the task associated with the elevator call
        t = self.message_tasks[key]
        t.cancel("cancel")
        await t
        assert directed_target_floor not in self.elevators.requests

    async def select_floor(self, floor: FloorLike, elevator_id: ElevatorId):
        floor = Floor(floor)

        elevator = self.elevators[elevator_id]
        if elevator.started is False:
            logger.warning(f"Controller: Elevator {elevator_id} is not enabled, cannot select floor {floor}")
            return

        # Check if the floor is already selected
        if floor in elevator.selected_floors:
            logger.info(f"Controller: Floor {floor} already selected for elevator {elevator_id}")
            return

        try:
            elevator.selected_floors.add(floor)
            await elevator.commit_floor(floor, Direction.IDLE).wait()
            event_bus.publish(Event.FLOOR_ARRIVED, floor, elevator_id)
        except asyncio.CancelledError as e:
            if str(e) != "deselect":
                raise asyncio.CancelledError from e
        finally:
            elevator.selected_floors.remove(floor)
            elevator.cancel_commit(floor, Direction.IDLE)

    async def deselect_floor(self, floor: FloorLike, elevator_id: ElevatorId):
        floor = Floor(floor)

        elevator = self.elevators[elevator_id]

        # Check if the floor is already selected
        key = f"select_floor@{floor}#{elevator_id}"
        assert floor in elevator.selected_floors
        assert key in self.message_tasks

        # Cancel the task associated with the floor selection and wait for it to finishs
        t = self.message_tasks[key]
        t.cancel("deselect")
        await t
        assert floor not in elevator.selected_floors

    async def open_door(self, elevator: Elevator):
        await elevator.commit_door(DoorDirection.OPEN)

    async def close_door(self, elevator: Elevator):
        await elevator.commit_door(DoorDirection.CLOSE)


if __name__ == "__main__":

    async def main():
        try:
            async with asyncio.TaskGroup() as tg:
                c = Controller()
                c.start(tg)

                await asyncio.sleep(1)
                c.handle_message_task("call_up@1")

                while True:
                    msg = await c.get_event_message()
                    logger.info(msg)

        except asyncio.CancelledError:
            pass

    asyncio.run(main())
