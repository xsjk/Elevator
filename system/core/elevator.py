import asyncio
import bisect
import inspect
from copy import copy
from dataclasses import dataclass, field
from itertools import chain
from typing import Iterator, Self, SupportsIndex

from ..utils.common import (
    Direction,
    DoorDirection,
    DoorState,
    ElevatorId,
    ElevatorState,
    Event,
    Floor,
    FloorAction,
    FloorLike,
)
from ..utils.event_bus import event_bus
from .logger import logger


class TargetFloors(list[FloorAction]):
    """
    Actions is a list of tuples (floor, direction) that represents the actions of the elevator.
    The direction is either UP or DOWN.
    The list is sorted based on the direction and floor number.
    """

    def __init__(self, direction: Direction):
        super().__init__()
        self.direction = direction
        self.nonemptyEvent = asyncio.Event()

    def add(self, floor: FloorLike, direction: Direction):
        assert direction in (Direction.IDLE, self.direction), f"Direction of requested action {direction.name} does not match the chain direction {self.direction.name}"
        bisect.insort(self, FloorAction(floor, direction), key=self.key)
        if not self.is_empty():
            self.nonemptyEvent.set()

    def remove(self, action: FloorAction):
        super().remove(action)
        if len(self) == 0:
            self.nonemptyEvent.clear()

    def pop(self, index: SupportsIndex = -1) -> FloorAction:
        action = super().pop(index)
        if len(self) == 0:
            self.nonemptyEvent.clear()
        return action

    def is_empty(self) -> bool:
        return len(self) == 0

    def copy(self) -> Self:
        new_copy = self.__class__(self.direction)
        new_copy.extend(self)
        new_copy.nonemptyEvent = asyncio.Event()
        if not self.is_empty():
            new_copy.nonemptyEvent.set()
        return new_copy

    @property
    def direction(self) -> Direction:
        return self._direction

    @direction.setter
    def direction(self, new_direction: Direction):
        if new_direction == getattr(self, "_direction", None):
            return
        assert all(d == Direction.IDLE for _, d in self)
        self._direction = new_direction

        match new_direction:
            case Direction.UP:
                self.key = lambda x: (x[0], x[1])
            case Direction.DOWN:
                self.key = lambda x: (-x[0], -x[1])
            case Direction.IDLE:
                self.key = None


class TargetFloorChains:
    def __init__(
        self,
        event_loop: asyncio.AbstractEventLoop | asyncio.TaskGroup | None = None,
        exit_event: asyncio.Event | None = None,
    ):
        self.current_chain = TargetFloors(Direction.IDLE)
        self.next_chain = TargetFloors(Direction.IDLE)
        self.future_chain = TargetFloors(Direction.IDLE)
        self.swap_event = asyncio.Event()
        if event_loop is None:
            self.event_loop = asyncio.get_event_loop()
        else:
            self.event_loop = event_loop
        if exit_event is None:
            self.exit_event = asyncio.Event()
        else:
            self.exit_event = exit_event

    @property
    def direction(self) -> Direction:
        return self.current_chain.direction

    @direction.setter
    def direction(self, new_direction: Direction):
        self.current_chain.direction = new_direction
        self.next_chain.direction = -new_direction
        self.future_chain.direction = new_direction

    @property
    def nonemptyEvent(self) -> asyncio.Event:
        return self.current_chain.nonemptyEvent

    def _swap_chains(self):
        """
        Swap the current chain with the next chain and the next chain with the future chain.
        This is used when the current chain is empty and we need to move to the next chain.
        """
        self.swap_event.set()
        self.current_chain, self.next_chain, self.future_chain = self.next_chain, self.future_chain, TargetFloors(-self.future_chain.direction)
        assert self.current_chain.direction == -self.next_chain.direction == self.future_chain.direction, f"Direction mismatch after swap: {self.current_chain.direction}, {self.next_chain.direction}, {self.future_chain.direction}"

    def pop(self) -> FloorAction:
        try:
            if len(self.current_chain) > 0:
                a = self.current_chain.pop(0)

                if a.direction != Direction.IDLE:
                    # do not swap the chains if the action is not IDLE
                    # this is to allow IDLE actions to be added to current_chain
                    return a

                elif len(self) > 0:
                    while len(self.current_chain) == 0:
                        # If the current chain is empty, we need to swap the next and future chains
                        self._swap_chains()
                return a
            elif len(self) > 0:
                while len(self.current_chain) == 0:
                    # If the current chain is empty, we need to swap the next and future chains
                    self._swap_chains()
                return self.pop()

            raise IndexError("No actions in the current chain")
        finally:
            if len(self) == 0:
                self.direction = Direction.IDLE

    def top(self) -> FloorAction:
        return next(iter(self))

    async def _wait_event(self, e: asyncio.Event):
        if isinstance(self.event_loop, asyncio.AbstractEventLoop):
            try:
                running_loop = asyncio.events.get_running_loop()
            except RuntimeError:
                pass
            else:
                assert running_loop is self.event_loop, "The event loop is not the same as the one used in this TargetFloorChains instance"
                await e.wait()

        elif isinstance(self.event_loop, asyncio.TaskGroup):
            await e.wait()

        else:
            raise TypeError(f"Unsupported event loop type: {type(self.event_loop)}")

    async def get(self) -> FloorAction:
        wait_tasks = []
        try:
            while self.is_empty():
                for name, e in zip(
                    [
                        "current_chain.nonemptyEvent",
                        "next_chain.nonemptyEvent",
                        "future_chain.nonemptyEvent",
                        "swap_event",
                    ],
                    [
                        self.current_chain.nonemptyEvent,
                        self.next_chain.nonemptyEvent,
                        self.future_chain.nonemptyEvent,
                        self.swap_event,
                        self.exit_event,
                    ],
                ):
                    wait_tasks.append(self.event_loop.create_task(self._wait_event(e), name=f"wait {name} {__file__}:{inspect.stack()[0].lineno}"))

                await asyncio.wait(
                    wait_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if self.exit_event.is_set():
                    raise asyncio.CancelledError()

                # If swap_event is set, reset it and continue the loop
                if self.swap_event.is_set():
                    self.swap_event.clear()
                    continue

            return self.top()

        finally:
            for task in wait_tasks:
                if not task.done():
                    task.cancel("exit")
                    try:
                        await task
                    except asyncio.CancelledError as e:
                        if str(e) != "exit":
                            raise e
                    finally:
                        assert task.cancelled() or task.done()

    def remove(self, item: FloorAction):
        if item in self.current_chain:
            self.current_chain.remove(item)
            if not self.is_empty():
                while self.current_chain.is_empty():
                    self._swap_chains()
            else:
                self.direction = Direction.IDLE
            return

        if item in self.next_chain:
            self.next_chain.remove(item)
            return

        if item in self.future_chain:
            self.future_chain.remove(item)
            return

        raise ValueError(f"FloorAction {item} not found in any chain")

    def is_empty(self) -> bool:
        return len(self) == 0

    def clear(self):
        self.current_chain.clear()
        self.next_chain.clear()
        self.future_chain.clear()

    def __copy__(self) -> Self:
        c = self.__class__(event_loop=self.event_loop)
        c.current_chain = self.current_chain.copy()
        c.next_chain = self.next_chain.copy()
        c.future_chain = self.future_chain.copy()
        return c

    def __len__(self) -> int:
        return len(self.current_chain) + len(self.next_chain) + len(self.future_chain)

    def __iter__(self) -> Iterator[FloorAction]:
        return chain(self.current_chain, self.next_chain, self.future_chain)

    def __contains__(self, item: FloorAction) -> bool:
        return any(item in chain for chain in (self.current_chain, self.next_chain, self.future_chain))

    def __getitem__(self, index: int) -> FloorAction:
        if index < 0:
            index += len(self.current_chain) + len(self.next_chain) + len(self.future_chain)
        if index < len(self.current_chain):
            return self.current_chain[index]
        index -= len(self.current_chain)
        if index < len(self.next_chain):
            return self.next_chain[index]
        index -= len(self.next_chain)
        if index < len(self.future_chain):
            return self.future_chain[index]
        raise IndexError("Index out of range")

    def __repr__(self) -> str:
        return f"ElevatorActionChains(direction={self.direction.name}, current_chain={self.current_chain}, next_chain={self.next_chain}, future_chain={self.future_chain})"


@dataclass
class Elevator:
    # Attributes
    id: ElevatorId

    floor_travel_duration: float = 1.0
    accelerate_duration: float = 1.0
    door_move_duration: float = 3.0
    door_stay_duration: float = 3.0

    @property
    def accelerate_distance(self) -> float:
        return 0.5 / self.floor_travel_duration * self.accelerate_duration

    @property
    def max_speed(self) -> float:
        return 1.0 / self.floor_travel_duration

    @property
    def acceleration(self) -> float:
        return self.max_speed / self.accelerate_duration

    queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # the queue to put events in
    door_idle_event: asyncio.Event = field(default_factory=asyncio.Event)  # exclusive lock for move and door

    _current_floor: Floor = Floor(1)  # Initial floor
    _state: ElevatorState = ElevatorState.STOPPED_DOOR_CLOSED
    selected_floors: set[Floor] = field(default_factory=set)  # Internal button target floors

    # Internal state

    # Floors that the elevator will go to one by one, direction is the requested going direction after the elevator arrives at the floor.
    ## For example, if the elevator is at floor 1 and the user selects floor 3 and 4, the commited floors can be:
    ## [(3, IDLE), (4, IDLE), (5, DOWN), (4, DOWN), (2, DOWN), (3, UP), (4, UP)]
    ## After the elevator arrives at floor 5 and user selects floor 1, 2, 4 and 6, the commited floors will be:
    ## [(4, IDLE), (4, DOWN), (2, IDLE), (2, DOWN), (1, IDLE), (3, UP), (4, UP)]
    # e.g. []
    events: dict[FloorAction, asyncio.Event] = field(default_factory=dict)

    _moving_timestamp: float | None = None  # Timestamp when movement starts
    _moving_speed: float | None = None  # Speed of the elevator during movement, None if not moving
    _door_last_state_change_time: float | None = None  # Timestamp when door movement starts

    door_loop_started: bool = False
    move_loop_started: bool = False

    door_action_queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Queue for actions to be executed
    door_action_processed: asyncio.Event = field(default_factory=asyncio.Event)

    def copy(self) -> Self:
        c = copy(self)
        c.target_floor_chains = copy(self.target_floor_chains)
        c.events = {k: asyncio.Event() for k in self.events}
        c.door_action_queue = asyncio.Queue()
        return c

    async def commit_door(self, door_state: DoorDirection):
        if not self.door_loop_started:
            logger.warning(f"door_loop of elevator {self.id} was not started yet.")
        self.door_action_queue.put_nowait(door_state)  # the queue is consumed at door_loop
        self.door_action_processed.clear()
        await self.door_action_processed.wait()

    def commit_floor(self, floor: FloorLike, requested_direction: Direction = Direction.IDLE) -> asyncio.Event:
        """
        Commit a floor to the elevator's list of target floors.

        Args:
            floor (Floor): The floor to commit. Must be an instance of Floor.
            requested_direction (Direction): The direction the elevator should take after arriving at the floor. If Direction.IDLE, it is a call inside the elevator

        Returns:
            asyncio.Event: An event that will be set when the elevator arrives at the committed floor.

        """
        floor = Floor(floor)

        if not self.move_loop_started:
            logger.warning(f"move_loop of elevator {self.id} was not started yet.")

        logger.debug(f"Elevator {self.id}: Committing floor {floor} with direction {requested_direction.name}")

        directed_floor = FloorAction(floor, requested_direction)
        if directed_floor in self.target_floor_chains:
            raise ValueError(f"Floor {floor} already in the action chain with direction {requested_direction.name}")

        assert isinstance(requested_direction, Direction)

        target_direction = self.direction_to(floor)

        # arrive immediately if the elevator is already at the floor
        if target_direction == Direction.IDLE:  # same floor
            if requested_direction == self.target_floor_chains.direction:  # same direction
                msg = f"floor_arrived@{self.current_floor}#{self.id}"
                match requested_direction:
                    case Direction.UP:
                        self.queue.put_nowait(f"up_{msg}")
                    case Direction.DOWN:
                        self.queue.put_nowait(f"down_{msg}")
                    case Direction.IDLE:
                        self.queue.put_nowait(msg)

                e = asyncio.Event()

                async def open_door():
                    await self.commit_door(DoorDirection.OPEN)
                    e.set()

                asyncio.create_task(open_door(), name=f"open_door_elevator_{self.id}_floor_{floor} {__file__}:{inspect.stack()[0].lineno}")
                logger.debug(f"Elevator {self.id}: Arrived at floor {floor} immediately, opening door")
                return e

        # Determine the chain to add the action to and process later in the move_loop
        match self.target_floor_chains.direction:
            case Direction.IDLE:
                # Use the current chain
                chain = self.target_floor_chains.current_chain
                # Initialize the direction of the chain
                self.target_floor_chains.direction = requested_direction if requested_direction != Direction.IDLE else target_direction
            case Direction.UP | Direction.DOWN:
                match requested_direction:
                    case Direction.IDLE:
                        if target_direction in (self.target_floor_chains.direction, Direction.IDLE):
                            chain = self.target_floor_chains.current_chain
                        else:
                            chain = self.target_floor_chains.next_chain

                    case Direction.UP | Direction.DOWN:
                        if requested_direction == self.target_floor_chains.direction:
                            if target_direction in (self.target_floor_chains.direction, Direction.IDLE):
                                # We can directly reuse the current plan since the all directions are the same
                                chain = self.target_floor_chains.current_chain
                            else:
                                # The floor has missed although the requested direction is the same as the current direction
                                # We need to add it to the last plan
                                chain = self.target_floor_chains.future_chain
                        else:
                            # Add the floor to the next plan since it is in the opposite direction
                            chain = self.target_floor_chains.next_chain

        # Add the action to the chain
        chain.add(floor, requested_direction)
        logger.debug(f"Elevator {self.id}: {self.target_floor_chains}")

        self.events[directed_floor] = asyncio.Event()
        return self.events[directed_floor]

    def cancel_commit(self, floor: FloorLike, requested_direction: Direction = Direction.IDLE):
        floor = Floor(floor)
        directed_floor = FloorAction(floor, requested_direction)
        # Remove the action from the chain
        logger.debug(f"Elevator {self.id}: Cancelling floor {floor} with direction {requested_direction.name}")
        logger.debug(f"Elevator {self.id}: {self.target_floor_chains}")
        if directed_floor in self.target_floor_chains:
            self.target_floor_chains.remove(directed_floor)
            assert directed_floor in self.events
            self.events.pop(directed_floor).set()
            logger.debug(f"Elevator {self.id}: {self.target_floor_chains}")

    def arrival_summary(self, floor: FloorLike, requested_direction: Direction) -> tuple[float, int]:
        floor = Floor(floor)
        directed_floor = FloorAction(floor, requested_direction)
        if directed_floor not in self.target_floor_chains:
            raise ValueError(f"Floor {floor} not in action chain")

        current_floor = self.current_position

        n_floors = 0.0
        n_stops = 0
        for a in iter(self.target_floor_chains):
            n_floors += abs(a.floor - current_floor)
            if a.floor == floor and a.direction in (requested_direction, Direction.IDLE):
                break
            n_stops += 1

            current_floor = a.floor

        return n_floors, n_stops

    def estimate_door_close_time(self) -> float:
        """
        Estimate the time until the door finally closes.

        Returns:
            float: Estimated time in seconds until the door is fully closed.
        """
        duration: float = 0.0
        if self._door_last_state_change_time is None:
            return duration
        passed = self.event_loop.time() - self._door_last_state_change_time

        match self.state:
            case ElevatorState.OPENING_DOOR:
                duration = self.door_move_duration - passed + self.door_stay_duration + self.door_move_duration
            case ElevatorState.STOPPED_DOOR_OPENED:
                duration = self.door_stay_duration - passed + self.door_move_duration
            case ElevatorState.CLOSING_DOOR:
                duration = self.door_move_duration - passed
        if duration < 0:
            duration = 0.0
        return duration

    def estimate_door_open_time(self) -> float:
        """
        Estimate the time until the door fully opened (including the stay duration).

        Returns:
            float: Estimated time in seconds until the door is fully closed.
        """
        duration: float = self.door_move_duration + self.door_stay_duration + self.door_move_duration
        if self._door_last_state_change_time is None:
            return duration
        passed = self.event_loop.time() - self._door_last_state_change_time

        match self.state:
            case ElevatorState.OPENING_DOOR:
                duration = self.door_move_duration - passed + self.door_stay_duration
            case ElevatorState.STOPPED_DOOR_OPENED:
                duration = self.door_stay_duration - passed
            case ElevatorState.CLOSING_DOOR:
                duration = passed + self.door_stay_duration
        if duration < 0:
            duration = 0.0
        return duration

    def pop_target(self) -> FloorAction:
        """
        Pop the next action from the elevator's list of target floors.
        """
        if self.target_floor_chains.is_empty():
            raise IndexError("No actions in the current chain")

        directed_floor = self.target_floor_chains.pop()
        event = self.events.pop(directed_floor)
        event.set()
        logger.debug(f"Elevator {self.id}: Action popped: {directed_floor}")
        logger.debug(f"Elevator {self.id}: {self.target_floor_chains}")
        return directed_floor

    async def _move_loop(self):
        """
        Main loop for the elevator. This function will be called in a separate async task.

        It really updates `self.current_floor`.
        It should also trigger the update of the animation of the elevator.
        """
        try:
            self.move_loop_started = True
            while True:
                # Get the target floor from the plan
                target_floor, direction = await self.target_floor_chains.get()

                # Wait for the door not open or moving
                await self.door_idle_event.wait()

                # Start the elevator movement (move from current floor to target floor)
                self._moving_timestamp = self.event_loop.time()
                self._moving_speed = self.max_speed

                if self.current_floor < target_floor:
                    self.state = ElevatorState.MOVING_UP
                    # TODO trigger animation
                    await asyncio.sleep(self.floor_travel_duration)
                    self.current_floor += 1

                    if self.target_floor_chains.is_empty():
                        # target floor deselected
                        self.state = ElevatorState.STOPPED_DOOR_CLOSED

                elif self.current_floor > target_floor:
                    self.state = ElevatorState.MOVING_DOWN
                    # TODO trigger animation
                    await asyncio.sleep(self.floor_travel_duration)
                    self.current_floor -= 1

                    if self.target_floor_chains.is_empty():
                        # target floor deselected
                        self.state = ElevatorState.STOPPED_DOOR_CLOSED

                else:
                    self.state = ElevatorState.STOPPED_DOOR_CLOSED
                    await self.commit_door(DoorDirection.OPEN)
                    assert not self.door_idle_event.is_set()

                    committed_direction = direction
                    while True:
                        self.pop_target()
                        msg = f"floor_arrived@{self.current_floor}#{self.id}"
                        if self.target_floor_chains.is_empty():
                            match direction:
                                case Direction.IDLE:
                                    self.queue.put_nowait(msg)
                                case Direction.UP:
                                    self.queue.put_nowait(f"up_{msg}")
                                case Direction.DOWN:
                                    self.queue.put_nowait(f"down_{msg}")
                        else:
                            next_target_floor, next_direction = self.target_floor_chains.top()
                            if next_target_floor == self.current_floor:
                                # get commited direction
                                assert next_direction != direction
                                if direction == Direction.IDLE:
                                    committed_direction = next_direction
                                assert committed_direction != Direction.IDLE

                                if next_direction == -committed_direction:
                                    match committed_direction:
                                        case Direction.UP:
                                            self.queue.put_nowait(f"up_{msg}")
                                        case Direction.DOWN:
                                            self.queue.put_nowait(f"down_{msg}")
                                    break  # we are going to the opposite direction, so we can stop here
                                # otherwise, we can continue to the next target floor
                                logger.warning(f"Target floor {next_target_floor} is the same as current floor {self.current_floor}, skipping")
                                continue

                            elif next_target_floor > self.current_floor:
                                self.queue.put_nowait(f"up_{msg}")
                            else:  # target_floor < self.current_floor
                                self.queue.put_nowait(f"down_{msg}")
                        break

                    logger.debug(f"Elevator {self.id}: Waiting for door to close")
                    await self.door_idle_event.wait()  # wait for the door to close

                self._moving_timestamp = None

                # Signal that the floor as arrived
        except asyncio.CancelledError:
            logger.debug(f"Elevator {self.id}: Move loop cancelled")
            pass
        except RuntimeError:
            # current running loop was stopped, e.g. by the program exit
            logger.warning(f"Elevator {self.id}: Move loop cancelled due to RuntimeError")
            pass
        finally:
            self.move_loop_started = False
            pass

    async def _door_loop(self):
        async def open_door(duration=self.door_move_duration):
            try:
                assert not self.door_idle_event.is_set()

                self.state = ElevatorState.OPENING_DOOR
                self._door_last_state_change_time = self.event_loop.time() - (self.door_move_duration - duration)
                await asyncio.sleep(duration)
                self.state = ElevatorState.STOPPED_DOOR_OPENED
                self._door_last_state_change_time = self.event_loop.time()
                self.queue.put_nowait(f"door_opened#{self.id}")

                await asyncio.sleep(self.door_stay_duration)
                await close_door()

            except asyncio.CancelledError as e:
                if len(e.args) == 0:  # no message provided
                    raise e  # the task was cancelled because of the program exit
                match self.state:
                    case ElevatorState.OPENING_DOOR:
                        logger.debug(f"Elevator {self.id}: Door opening cancelled")
                    case ElevatorState.STOPPED_DOOR_OPENED:
                        logger.debug(f"Elevator {self.id}: Door stay cancelled")

        async def close_door(duration=self.door_move_duration):
            try:
                # Close door
                assert not self.door_idle_event.is_set()

                self.state = ElevatorState.CLOSING_DOOR
                self._door_last_state_change_time = self.event_loop.time()

                await asyncio.sleep(duration)

                self.state = ElevatorState.STOPPED_DOOR_CLOSED
                self.queue.put_nowait(f"door_closed#{self.id}")

                # notify the move_loop
                self.door_idle_event.set()
                assert self.door_idle_event.is_set()

            except asyncio.CancelledError as e:
                if len(e.args) == 0:
                    raise e
                logger.debug(f"Elevator {self.id}: Door closing cancelled")

        task: asyncio.Task | None = None

        try:
            self.door_loop_started = True
            while True:
                logger.debug(f"Elevator {self.id}: Wait for door action queue")
                action = await self.door_action_queue.get()
                match self.state:
                    case ElevatorState.MOVING_UP | ElevatorState.MOVING_DOWN:
                        logger.info("Cannot commit door state while the elevator is moving or opening")
                    case ElevatorState.OPENING_DOOR:
                        pass
                    case ElevatorState.STOPPED_DOOR_CLOSED:
                        if action == DoorDirection.OPEN:
                            self.door_idle_event.clear()
                            task = asyncio.create_task(open_door(), name=f"open_door_{__file__}:{inspect.stack()[0].lineno}")
                    case ElevatorState.CLOSING_DOOR:
                        assert task is not None
                        assert self._door_last_state_change_time is not None

                        if action == DoorDirection.OPEN:
                            task.cancel("request door open")
                            await task
                            assert task.cancelled() or task.done()
                            duration = self.event_loop.time() - self._door_last_state_change_time
                            logger.info(f"Door closing is interrupted after {duration}")

                            self.door_idle_event.clear()
                            task = asyncio.create_task(open_door(duration), name=f"open_door_{__file__}:{inspect.stack()[0].lineno}")

                    case ElevatorState.STOPPED_DOOR_OPENED:
                        assert task is not None
                        if action == DoorDirection.CLOSE:
                            assert not self.door_idle_event.is_set()
                            task.cancel("request door close")  # cancel the stay duration if it is running
                            await task
                            assert task.cancelled() or task.done()
                            task = asyncio.create_task(close_door(), name=f"close_door_{__file__}:{inspect.stack()[0].lineno}")

                self.door_action_processed.set()

        except asyncio.CancelledError:
            logger.debug(f"Elevator {self.id}: Door loop cancelled")
            pass
        finally:
            if task is not None and not task.done():
                task.cancel("exit")
                await task
                assert task.cancelled() or task.done()
            self.door_loop_started = False

    @property
    def started(self) -> bool:
        return self.move_loop_started and self.door_loop_started

    def start(self, tg: asyncio.AbstractEventLoop | asyncio.TaskGroup | None = None):
        if tg is None:
            tg = asyncio.get_event_loop()

        if isinstance(tg, asyncio.AbstractEventLoop):
            self.event_loop = tg
        elif isinstance(tg, asyncio.TaskGroup) and tg._loop is not None:
            self.event_loop = tg._loop
        else:
            self.event_loop = asyncio.get_event_loop()

        self.exit_event = asyncio.Event()
        self.target_floor_chains = TargetFloorChains(event_loop=self.event_loop, exit_event=self.exit_event)
        self.door_idle_event.set()
        if not self.started:
            self.door_loop_task = tg.create_task(self._door_loop(), name=f"door_loop_elevator_{self.id} {__file__}:{inspect.stack()[0].lineno}")
            self.move_loop_task = tg.create_task(self._move_loop(), name=f"move_loop_elevator_{self.id} {__file__}:{inspect.stack()[0].lineno}")

    async def stop(self):
        if not self.started:
            return

        self.exit_event.set()

        tasks = (self.door_loop_task, self.move_loop_task)
        for t in tasks:
            t.cancel()

        for t in tasks:
            await t

    @property
    def moving_direction(self) -> Direction:
        return self.state.get_moving_direction()

    @property
    def door_open(self) -> bool:
        return self.state.is_door_open()

    @property
    def state(self) -> ElevatorState:
        return self._state

    @property
    def next_target_floor(self) -> Floor | None:
        if self.target_floor_chains.is_empty():
            return None
        return self.target_floor_chains.top().floor

    @state.setter
    def state(self, new_state: ElevatorState):
        old_state = self._state
        self._state = new_state

        # # Log state change
        # logger.debug(f"Elevator {self.id} state changed to {new_state.name}, door_open={self.door_open}, direction={self.committed_direction}")

        # Publish event for state change
        if old_state != new_state:
            event_bus.publish(Event.ELEVATOR_STATE_CHANGED, self.id, self.current_floor, self.door_state, self.moving_direction)

    @property
    def current_floor(self) -> Floor:
        return self._current_floor

    @current_floor.setter
    def current_floor(self, new_floor: FloorLike):
        new_floor = Floor(new_floor)
        if self._current_floor != new_floor:
            self._current_floor = new_floor

            # Log floor change
            logger.debug(f"Elevator {self.id}: floor changed to {new_floor}")

            # Publish event for floor change
            event_bus.publish(Event.ELEVATOR_FLOOR_CHANGED, self.id, self.current_floor, self.door_state, self.moving_direction)

    @property
    def current_position(self) -> float:
        match self.moving_direction:
            case Direction.UP:
                return self._current_floor + self.position_percentage
            case Direction.DOWN:
                return self._current_floor - self.position_percentage

        return self._current_floor

    def direction_to(self, target_floor: FloorLike) -> Direction:
        target_floor = Floor(target_floor)
        if target_floor > self.current_position:
            return Direction.UP
        elif target_floor < self.current_position:
            return Direction.DOWN
        else:
            return Direction.IDLE

    @property
    def position_percentage(self) -> float:
        if self._moving_timestamp is None:
            return 0.0
        duration = self.event_loop.time() - self._moving_timestamp
        assert duration >= 0, "Moving timestamp is in the future"
        assert self._moving_speed is not None
        p = duration * self._moving_speed
        if p > 1:
            p = 1.0
        assert 0 <= p <= 1, f"Position percentage {p} is out of bounds [0, 1]"
        return p

    @property
    def door_position_percentage(self) -> float:
        match self.state:
            case ElevatorState.STOPPED_DOOR_OPENED:
                p = 1.0
            case ElevatorState.OPENING_DOOR:
                assert self._door_last_state_change_time is not None
                p = (self.event_loop.time() - self._door_last_state_change_time) / self.door_move_duration
            case ElevatorState.CLOSING_DOOR:
                assert self._door_last_state_change_time is not None
                p = 1.0 - (self.event_loop.time() - self._door_last_state_change_time) / self.door_move_duration
            case ElevatorState.STOPPED_DOOR_CLOSED | ElevatorState.MOVING_UP | ElevatorState.MOVING_DOWN:
                p = 0.0
        if p > 1:
            p = 1.0
        elif p < 0:
            p = 0.0
        assert 0 <= p <= 1, f"Door position percentage {p} is out of bounds [0, 1]"
        return p

    @property
    def door_state(self) -> DoorState:
        return self.state.get_door_state()

    @property
    def committed_direction(self) -> Direction:
        return self.target_floor_chains.direction


if __name__ == "__main__":

    async def main():
        try:
            async with asyncio.TaskGroup() as tg:
                e = Elevator(id=1)
                e.start(tg)

                await asyncio.sleep(1)
                e.commit_floor(2, Direction.UP)
                e.commit_floor(2, Direction.DOWN)

                await asyncio.sleep(0.5)
                e.commit_floor(3, Direction.IDLE)
                e.commit_floor(-1, Direction.IDLE)

                while True:
                    logger.info(await e.queue.get())

        except asyncio.CancelledError:
            pass

    asyncio.run(main())
