import asyncio
import bisect
import inspect
from copy import copy
from dataclasses import dataclass, field
from itertools import chain, combinations_with_replacement, pairwise
from typing import Generator, Iterator, Self, SupportsIndex, overload

from ..utils.common import (
    Direction,
    DoorDirection,
    DoorState,
    DestinationHeuristic,
    ElevatorId,
    ElevatorState,
    Event,
    Floor,
    FloorAction,
    FloorLike,
    cancel,
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

    def add_unique(self, floor: FloorLike, direction: Direction):
        action = FloorAction(floor, direction)
        if action not in self:
            self.add(floor, direction)

    def top(self) -> FloorAction:
        return self[0]

    def bottom(self) -> FloorAction:
        return self[-1]

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
        if new_direction == Direction.IDLE:
            assert self.is_empty(), "Cannot set direction to IDLE when there are actions in the chains"
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
            # NOTE: do not set direction to IDLE here
            pass

    def top(self) -> FloorAction:
        return next(iter(self))

    def bottom(self) -> FloorAction:
        if len(self.future_chain) > 0:
            return self.future_chain.bottom()
        elif len(self.next_chain) > 0:
            return self.next_chain.bottom()
        elif len(self.current_chain) > 0:
            return self.current_chain.bottom()
        raise IndexError("No actions in the current chain")

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
        wait_tasks: list[asyncio.Task] = []
        try:
            while self.is_empty():
                wait_tasks.clear()

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

                _, pending = await asyncio.wait(
                    wait_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if self.exit_event.is_set():
                    raise asyncio.CancelledError("exit")

                # If swap_event is set, reset it and continue the loop
                if self.swap_event.is_set():
                    self.swap_event.clear()

                # stop all pending tasks
                await cancel(pending)

                if self.exit_event.is_set():
                    raise asyncio.CancelledError("exit")

            return self.top()

        finally:
            await cancel(wait_tasks)

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
        self.direction = Direction.IDLE

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

    def select_chain(self, requested_direction: Direction, target_direction: Direction) -> TargetFloors:
        """
        Select the appropriate target-floor chain for adding a new action.
        Sets elevator direction if chains are idle.
        """
        # If idle, initialize the chains' direction
        if self.direction == Direction.IDLE:
            if requested_direction != Direction.IDLE:
                # the target is current floor
                if target_direction in (Direction.IDLE, requested_direction):
                    self.direction = requested_direction
                    return self.current_chain
                # the target opposite to requested direction
                else:
                    assert target_direction != requested_direction
                    self.direction = target_direction
                    return self.next_chain

            elif target_direction != Direction.IDLE:
                self.direction = target_direction
            return self.current_chain
        # Internal call: no requested direction
        if requested_direction == Direction.IDLE:
            if target_direction in (self.direction, Direction.IDLE):
                return self.current_chain
            else:
                return self.next_chain
        # External request in current direction
        if requested_direction == self.direction:
            if target_direction in (self.direction, Direction.IDLE):
                return self.current_chain
            else:
                return self.future_chain
        # External request in opposite direction
        return self.next_chain

    def add(self, directed_floor: FloorAction, *, target_direction: Direction):
        floor, requested_direction = directed_floor
        chain = self.select_chain(requested_direction, target_direction)
        chain.add(floor, requested_direction)
        return self.top() == directed_floor

    @property
    def chains(self) -> tuple[TargetFloors, TargetFloors, TargetFloors]:
        return self.current_chain, self.next_chain, self.future_chain

    def get_metric(self, start_pos: float, destination_heuristic: DestinationHeuristic = DestinationHeuristic.NONE) -> tuple[float, float]:
        """
        Estimate the number of floors traveled and stops needed to reach the target floor.
        This is used for calculating the travel time.
        """
        match destination_heuristic:
            case DestinationHeuristic.NONE:
                n_floors = sum(abs(f1 - f2) for f1, f2 in pairwise((start_pos,) + tuple(a.floor for a in self)))
                n_stops = len(self)
                return n_floors, n_stops
            case DestinationHeuristic.NEAREST | DestinationHeuristic.FURTHEST:
                clone = copy(self)
                for chain, clone_chain in zip(self.chains, clone.chains):
                    for action in chain:
                        match action.direction:
                            case Direction.IDLE:
                                continue
                            case Direction.UP:
                                match destination_heuristic:
                                    case DestinationHeuristic.NEAREST:
                                        clone_chain.add_unique(action.floor + 1, Direction.IDLE)
                                    case DestinationHeuristic.FURTHEST:
                                        clone_chain.add_unique(Floor.max, Direction.IDLE)
                            case Direction.DOWN:
                                match destination_heuristic:
                                    case DestinationHeuristic.NEAREST:
                                        clone_chain.add_unique(action.floor - 1, Direction.IDLE)
                                    case DestinationHeuristic.FURTHEST:
                                        clone_chain.add_unique(Floor.min, Direction.IDLE)
                return clone.get_metric(start_pos)
            case DestinationHeuristic.MEAN:
                # the mean of the nearest and furthest destinations
                nearest = self.get_metric(start_pos, DestinationHeuristic.NEAREST)
                furthest = self.get_metric(start_pos, DestinationHeuristic.FURTHEST)
                return ((nearest[0] + furthest[0]) / 2, (nearest[1] + furthest[1]) / 2)


@dataclass
class Elevator:
    # Attributes
    id: ElevatorId  # Using int for ID

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
    target_floor_arrived: dict[FloorAction, asyncio.Event] = field(default_factory=dict)

    _moving_timestamp: float | None = None  # Timestamp when movement starts
    _moving_speed: float | None = None  # Speed of the elevator during movement, None if not moving
    _door_last_state_change_time: float | None = None  # Timestamp when door movement starts

    door_loop_started: asyncio.Event = field(default_factory=asyncio.Event)  # Event to indicate that the door loop has started
    move_loop_started: asyncio.Event = field(default_factory=asyncio.Event)  # Event to indicate that the move loop has started

    door_action_queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Queue for actions to be executed
    door_action_processed: asyncio.Event = field(default_factory=asyncio.Event)

    # Update fields for time estimation
    _total_travel_time: float = 0.0  # Total travel time for all planned stops

    def copy(self) -> Self:
        c = copy(self)
        c.target_floor_chains = copy(self.target_floor_chains)
        c.target_floor_arrived = {k: asyncio.Event() for k in self.target_floor_arrived}
        for k, v in self.target_floor_arrived.items():
            if v.is_set():
                c.target_floor_arrived[k].set()
        c.door_action_queue = asyncio.Queue()
        c.door_action_processed = asyncio.Event()
        c.queue = asyncio.Queue()
        return c

    async def commit_door(self, door_state: DoorDirection):
        if not self.door_loop_started.is_set():
            logger.warning(f"door_loop of elevator {self.id} was not started yet.")
        self.door_action_queue.put_nowait(door_state)  # the queue is consumed at door_loop
        self.door_action_processed.clear()
        await self.door_action_processed.wait()

    def commit_floor(self, floor: FloorLike, requested_direction: Direction = Direction.IDLE, event: asyncio.Event | None = None) -> asyncio.Event:
        """
        Commit a floor to the elevator's list of target floors and calculate its estimated arrival time.

        This method not only adds the floor to the appropriate chain but also maintains
        an estimate of the total travel time for each committed floor.
        """
        floor = Floor(floor)

        if not self.move_loop_started.is_set():
            logger.warning(f"move_loop of elevator {self.id} was not started yet.")

        logger.debug(f"Elevator {self.id}: Committing floor {floor} with direction {requested_direction.name}")

        directed_floor = FloorAction(floor, requested_direction)
        if directed_floor in self.target_floor_chains:
            logger.debug(f"Elevator {self.id}: Floor {floor} with direction {requested_direction.name} already in the action chain")
            return self.target_floor_arrived[directed_floor]

        assert isinstance(requested_direction, Direction)

        # Determine which chain to add the action to based on current direction and request
        # This is the core of the elevator scheduling algorithm
        self.target_floor_chains.add(directed_floor, target_direction=self.direction_to(floor))

        # Create and store the event that will be triggered when floor is reached
        self.target_floor_arrived[directed_floor] = asyncio.Event() if event is None else event
        return self.target_floor_arrived[directed_floor]

    def cancel_commit(self, floor: FloorLike, requested_direction: Direction = Direction.IDLE) -> asyncio.Event | None:
        floor = Floor(floor)
        directed_floor = FloorAction(floor, requested_direction)

        # Remove the action from the chain
        logger.debug(f"Elevator {self.id}: Cancelling floor {floor} with direction {requested_direction.name}")
        logger.debug(f"Elevator {self.id}: {self.target_floor_chains}")

        if directed_floor in self.target_floor_chains:
            self.target_floor_chains.remove(directed_floor)

            assert directed_floor in self.target_floor_arrived
            return self.target_floor_arrived.pop(directed_floor)  # .set()

    def estimate_door_close_time(self) -> float:
        """
        Estimate the time until the door finally closes.
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
        Estimate the time until the door fully opened.
        """
        duration: float = self.door_move_duration
        if self._door_last_state_change_time is None:
            assert self.state == ElevatorState.STOPPED_DOOR_CLOSED
            return duration

        passed = self.event_loop.time() - self._door_last_state_change_time
        match self.state:
            case ElevatorState.OPENING_DOOR:
                duration = self.door_move_duration - passed  # the time remaining to open the door
            case ElevatorState.STOPPED_DOOR_OPENED:
                duration = 0  # the door is already open
            case ElevatorState.CLOSING_DOOR:
                duration = passed  # the time to reopen the door from current state
            case ElevatorState.STOPPED_DOOR_CLOSED:
                duration = self.door_move_duration
            case _:
                logger.error(f"Invalid elevator state {self.state.name} for estimating door open time")
                raise ValueError(f"Invalid elevator state {self.state.name} for estimating door open time")
        if duration < 0:
            duration = 0.0
        return duration

    def calculate_duration(self, n_floors: float, n_stops: int | float) -> float:
        """
        Calculate travel duration based on floors and stops.
        """
        return n_floors * self.floor_travel_duration + n_stops * (self.door_move_duration * 2 + self.door_stay_duration)

    def _calculate_travel_parameters(self, target_floor: FloorLike, requested_direction: Direction) -> tuple[float, int]:
        """
        Calculate floors traveled and stops needed to reach target floor.
        """
        target_floor = Floor(target_floor)
        current_pos = self.current_position

        # Create a simulated plan by copying chains and adding target floor
        chains_copy = copy(self.target_floor_chains)
        target_direction = self.direction_to(target_floor)

        # Determine which chain to add the target floor to
        if chains_copy.direction == Direction.IDLE:
            chain = chains_copy.current_chain
            chains_copy.direction = requested_direction if requested_direction != Direction.IDLE else target_direction
        else:
            if requested_direction == Direction.IDLE:
                if target_direction in (chains_copy.direction, Direction.IDLE):
                    chain = chains_copy.current_chain
                else:
                    chain = chains_copy.next_chain
            else:
                if requested_direction == chains_copy.direction:
                    if target_direction in (chains_copy.direction, Direction.IDLE):
                        chain = chains_copy.current_chain
                    else:
                        chain = chains_copy.future_chain
                else:
                    chain = chains_copy.next_chain

        # Add target floor to simulated chain
        chain.add(target_floor, requested_direction)

        # Calculate travel parameters
        n_floors = 0.0
        n_stops = 0

        for action in chains_copy:
            n_floors += abs(action.floor - current_pos)
            if action.floor == target_floor and action.direction in (requested_direction, Direction.IDLE):
                break
            n_stops += 1
            current_pos = action.floor

        return n_floors, n_stops

    def pop_target(self) -> FloorAction:
        """
        Pop the next action from the elevator's list of target floors.
        Also removes its arrival time estimate.
        """
        if self.target_floor_chains.is_empty():
            raise IndexError("No actions in the current chain")

        directed_floor = self.target_floor_chains.pop()

        event = self.target_floor_arrived.pop(directed_floor)
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
            self.move_loop_started.set()
            while True:
                # Get the target floor from the plan
                logger.debug(f"Elevator {self.id}: Waiting for target floor")
                target_floor, direction = directed_floor = await self.target_floor_chains.get()
                logger.debug(f"Elevator {self.id}: Target floor received: {target_floor} with direction {direction.name}")

                if not self.door_idle_event.is_set():
                    # Got target floor while door is not idle, waiting for door to close or may interrupt door closing
                    if self.directed_floor == directed_floor:
                        match self.state:
                            case ElevatorState.CLOSING_DOOR:
                                # Interrupt door closing if necessary
                                await self.commit_door(DoorDirection.OPEN)
                                continue
                            case ElevatorState.OPENING_DOOR | ElevatorState.STOPPED_DOOR_OPENED:
                                # Ignoring target floor while door is opening
                                self.pop_target()
                                continue
                            case _:
                                raise RuntimeError(f"Invalid elevator state {self.state.name} while waiting for door to close")

                # Wait for the door not open or moving
                if not self.door_idle_event.is_set():
                    logger.debug(f"Elevator {self.id}: Waiting for door to close before moving")
                    await self.door_idle_event.wait()

                    if directed_floor != self.target_floor_chains.top():
                        # Some other action was added while waiting for the door
                        continue

                # Start the elevator movement (move from current floor to target floor)
                self._moving_timestamp = self.event_loop.time()
                self._moving_speed = self.max_speed

                if self.current_floor < target_floor:
                    self.state = ElevatorState.MOVING_UP
                    await asyncio.sleep(self.floor_travel_duration)
                    self.current_floor += 1

                    if self.target_floor_chains.is_empty():
                        # target floor deselected
                        self.state = ElevatorState.STOPPED_DOOR_CLOSED

                elif self.current_floor > target_floor:
                    self.state = ElevatorState.MOVING_DOWN
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
                        directed_floor = self.pop_target()  # NOTE: do not reset direction here, instead, reset the direction when door is closed if no other actions are in the chain
                        msg = f"floor_arrived@{self.current_floor}#{self.id}"
                        if self.target_floor_chains.is_empty():
                            if direction == Direction.IDLE:
                                direction = directed_floor.direction
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
                                logger.info(f"Target floor {next_target_floor} is the same as current floor {self.current_floor}, skipping")
                                continue

                            elif next_target_floor > self.current_floor:
                                self.queue.put_nowait(f"up_{msg}")
                            else:  # target_floor < self.current_floor
                                self.queue.put_nowait(f"down_{msg}")
                        break

                    # logger.debug(f"Elevator {self.id}: Waiting for door to close")
                    # await self.door_idle_event.wait()  # wait for the door to close

                self._moving_timestamp = None

                # Signal that the floor as arrived
        except asyncio.CancelledError as e:
            logger.debug(f"Elevator {self.id}: Move loop cancelled")
            if str(e) != "exit":
                raise e
        except RuntimeError:
            # current running loop was stopped, e.g. by the program exit
            logger.warning(f"Elevator {self.id}: Move loop cancelled due to RuntimeError")
            pass
        except Exception as e:
            logger.error(f"Elevator {self.id}: Move loop encountered an error: {type(e).__name__}: {e}")
            raise e
        finally:
            self.move_loop_started.clear()
            pass

    async def _door_loop(self):
        async def open_door(duration: float | None = None):
            if duration is None:
                duration = self.door_move_duration
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
                assert task is not None
                if task.uncancel() > 0:  # the task was cancelled because of the program exit
                    raise asyncio.CancelledError from e
                match self.state:
                    case ElevatorState.OPENING_DOOR:
                        logger.debug(f"Elevator {self.id}: Door opening cancelled")
                    case ElevatorState.STOPPED_DOOR_OPENED:
                        logger.debug(f"Elevator {self.id}: Door stay cancelled")

        async def close_door(duration: float | None = None):
            if duration is None:
                duration = self.door_move_duration
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
                if self.target_floor_chains.is_empty():
                    logger.debug(f"Elevator {self.id}: No target floors, setting direction to IDLE")
                    self.committed_direction = Direction.IDLE

            except asyncio.CancelledError as e:
                if len(e.args) == 0:
                    raise e
                logger.debug(f"Elevator {self.id}: Door closing cancelled")

        task: asyncio.Task | None = None

        try:
            self.door_loop_started.set()
            while True:
                logger.debug(f"Elevator {self.id}: Wait for door action queue")
                action = await self.door_action_queue.get()
                logger.debug(f"Elevator {self.id}: Door action received: {action.name}")
                match self.state:
                    case ElevatorState.MOVING_UP | ElevatorState.MOVING_DOWN:
                        logger.info("Cannot commit door state while the elevator is moving or opening")
                    case ElevatorState.OPENING_DOOR:
                        pass
                    case ElevatorState.STOPPED_DOOR_CLOSED:
                        if action == DoorDirection.OPEN:
                            self.door_idle_event.clear()
                            task = self.event_loop.create_task(open_door(), name=f"open_door_{__file__}:{inspect.stack()[0].lineno}")
                    case ElevatorState.CLOSING_DOOR:
                        assert task is not None
                        assert self._door_last_state_change_time is not None

                        if action == DoorDirection.OPEN:
                            task.cancel("request door open")
                            await task
                            assert task.done()
                            duration = self.event_loop.time() - self._door_last_state_change_time
                            logger.info(f"Door closing is interrupted after {duration}")

                            self.door_idle_event.clear()
                            task = self.event_loop.create_task(open_door(duration), name=f"open_door_{__file__}:{inspect.stack()[0].lineno}")

                    case ElevatorState.STOPPED_DOOR_OPENED:
                        assert task is not None
                        if action == DoorDirection.CLOSE:
                            assert not self.door_idle_event.is_set()
                            task.cancel("request door close")  # cancel the stay duration if it is running
                            await task
                            assert task.done()
                            task = self.event_loop.create_task(close_door(), name=f"close_door_{__file__}:{inspect.stack()[0].lineno}")

                self.door_action_processed.set()

        except asyncio.CancelledError:
            logger.debug(f"Elevator {self.id}: Door loop cancelled")
            pass
        finally:
            if task is not None and not task.done():
                task.cancel("exit")
                await task
                assert task.done()
            self.door_loop_started.clear()

    @property
    def is_started(self) -> bool:
        return self.move_loop_started.is_set() or self.door_loop_started.is_set()

    async def start(self, tg: asyncio.AbstractEventLoop | asyncio.TaskGroup | None = None):
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
        if not self.is_started:
            self.door_loop_task = tg.create_task(self._door_loop(), name=f"door_loop_elevator_{self.id} {__file__}:{inspect.stack()[0].lineno}")
            self.move_loop_task = tg.create_task(self._move_loop(), name=f"move_loop_elevator_{self.id} {__file__}:{inspect.stack()[0].lineno}")

        await self.move_loop_started.wait()
        await self.door_loop_started.wait()

    async def stop(self):
        if not self.is_started:
            assert self.exit_event.is_set()
            return

        self.exit_event.set()
        await cancel((self.door_loop_task, self.move_loop_task))

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
    def next_target(self) -> FloorAction | None:
        if self.target_floor_chains.is_empty():
            return None
        return self.target_floor_chains.top()

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

    @committed_direction.setter
    def committed_direction(self, new_direction: Direction):
        self.target_floor_chains.direction = new_direction

    @property
    def directed_floor(self) -> FloorAction:
        return FloorAction(self.current_floor, self.committed_direction)

    def estimate_total_duration(self, directed_request: FloorAction | None = None, *, destination_heuristic: DestinationHeuristic = DestinationHeuristic.NONE) -> float:
        """
        Estimate the total duration to reach the target floor, including door operations and travel time.
        If `directed_request` is None, it estimates the duration for the current target floor chain.
        If `directed_request` is provided, it estimates the duration to reach that floor.

        Args:
            directed_request (FloorAction | None): The floor action to estimate duration for, or None for current target.
            destination_heuristic (DestinationHeuristic): Heuristic to use for estimating the target floor chain.
        Returns:
            float: Estimated duration in seconds.
        """

        duration = 0.0
        if directed_request is None:
            if not self.state.is_moving():
                duration += self.estimate_door_close_time()

            n_floors, n_stops = self.target_floor_chains.get_metric(self.current_position, destination_heuristic)
            duration += self.calculate_duration(n_floors, n_stops)
            return duration

        assert isinstance(directed_request, FloorAction)
        target_floor, requested_direction = directed_request

        # Special case: Already at requested floor
        if target_floor == self.current_floor and self.committed_direction in (requested_direction, Direction.IDLE) and not self.state.is_moving():
            duration += self.estimate_door_open_time() + self.door_stay_duration + self.door_move_duration

            if self.target_floor_chains.is_empty():
                # No further actions, just return the door open time
                return duration

            n_floors, n_stops = self.target_floor_chains.get_metric(self.current_position, destination_heuristic)
            duration += self.calculate_duration(n_floors, n_stops)
            return duration

        # If not at requested floor, add the target floor to the chain
        target_direction = self.direction_to(target_floor)
        chain_copy = copy(self.target_floor_chains)
        chain_copy.add(directed_request, target_direction=target_direction)

        # If not at requested floor, estimate time to reach it
        if not self.state.is_moving():
            duration += self.estimate_door_close_time()

        n_floors, n_stops = chain_copy.get_metric(self.current_position, destination_heuristic)

        # Add travel time for all floors and stops
        duration += self.calculate_duration(n_floors, n_stops)
        return duration


class Elevators(dict[ElevatorId, Elevator]):
    """
    A collection of elevators, indexed by their IDs.
    Provides methods to manage and interact with multiple elevators.
    """

    def __init__(
        self,
        count: int,
        queue: asyncio.Queue,
        floor_travel_duration: float,
        accelerate_duration: float,
        door_move_duration: float,
        door_stay_duration: float,
    ):
        self.update({
            i: Elevator(
                id=i,
                queue=queue,
                floor_travel_duration=floor_travel_duration,
                accelerate_duration=accelerate_duration,
                door_move_duration=door_move_duration,
                door_stay_duration=door_stay_duration,
            )
            for i in range(1, count + 1)
        })
        self.eid2request: dict[ElevatorId, set[FloorAction]] = {e.id: set() for e in self.values()}
        self.request2eid: dict[FloorAction, ElevatorId] = {}
        self.request2event: dict[FloorAction, asyncio.Event] = {}

    def reassign(self, assignment: dict[ElevatorId, set[FloorAction]], strict: bool = False) -> Self:
        """
        Apply a new assignment of requests to elevators.
        """
        events = {}

        # Step 1: Cancel all requests in current assignment that are not in new assignment
        for eid, requests_set in self.eid2request.items():
            for request in requests_set:
                if request not in assignment[eid]:
                    event = self.request2event[request]
                    self[eid].cancel_commit(*request)
                    events[request] = event

        # Step 2: Commit new requests to elevators
        for eid, requests_set in assignment.items():
            for request in requests_set:
                if request not in self.eid2request[eid]:
                    self[eid].commit_floor(*request, event=events.pop(request))

        # Ensure all events were properly handled
        assert len(events) == 0

        self.eid2request.update(assignment)
        self.request2eid = {request: eid for eid, requests in self.eid2request.items() for request in requests}

        return self

    def copy(self) -> Self:
        c = self.__new__(self.__class__)
        c.update({eid: elevator.copy() for eid, elevator in self.items()})
        c.eid2request = self.eid2request.copy()
        c.request2eid = self.request2eid.copy()
        c.request2event = self.request2event.copy()
        return c

    def commit_floor(self, eid: ElevatorId, request: FloorAction, event: asyncio.Event | None = None) -> asyncio.Event:
        event = self[eid].commit_floor(*request, event=event)
        assert event is not None
        self.request2eid[request] = eid
        self.request2event[request] = event
        assert event is self[eid].target_floor_arrived[request]
        self.eid2request[eid].add(request)
        return event

    def cancel_commit(self, request: FloorAction) -> asyncio.Event:
        eid = self.request2eid.pop(request)
        event = self.request2event.pop(request)
        self.eid2request[eid].remove(request)
        self[eid].cancel_commit(*request)
        return event

    @property
    def requests(self) -> set[FloorAction]:
        return set(self.request2eid.keys())

    @property
    def eids(self) -> set[ElevatorId]:
        return set(self.keys())

    @property
    def most_possible_assignments(self) -> Generator[dict[ElevatorId, set[FloorAction]], None, None]:
        request_count = len(self.request2eid)
        max_eid_count = min(len(self.eids), request_count)
        for plan in combinations_with_replacement(self.eids, request_count):
            # maximize the number of elevators used
            if len(set(plan)) < max_eid_count:
                continue

            # Convert the plan to an assignment
            assert len(plan) == request_count
            assert len(set(plan)) == max_eid_count

            assignment: dict[ElevatorId, set[FloorAction]] = {eid: set() for eid in self.eids}
            for eid, request in zip(plan, self.request2eid.keys()):
                assignment[eid].add(request)
            yield assignment

    @overload
    def estimate_total_duration(self, *, destination_heuristic: DestinationHeuristic = DestinationHeuristic.NONE) -> float:
        """
        Estimate the total time for all actions in all elevators.
        """
        ...

    @overload
    def estimate_total_duration(self, directed_request: FloorAction, *, destination_heuristic: DestinationHeuristic = DestinationHeuristic.NONE) -> tuple[float, ElevatorId]:
        """
        Estimate the total time for all actions in all elevators after adding a new directed request.
        Returns a tuple of estimated duration and the best elevator ID to handle the request.
        """
        ...

    def estimate_total_duration(self, directed_request: FloorAction | None = None, *, destination_heuristic: DestinationHeuristic = DestinationHeuristic.NONE):
        durations = {eid: elevator.estimate_total_duration(destination_heuristic=destination_heuristic) for eid, elevator in self.items()}
        if directed_request is None:
            return max(durations.values())
        durations = {target_eid: max(e.estimate_total_duration(directed_request, destination_heuristic=destination_heuristic) if e.id == target_eid else durations[e.id] for e in self.values()) for target_eid in self.eids}
        best_eid = min(durations, key=lambda eid: durations[eid])
        return durations[best_eid], best_eid

    def pop(self, eid: ElevatorId, default=None) -> Elevator:
        try:
            e = super().pop(eid)
            requests = self.eid2request.pop(e.id)
            for request in requests:
                del self.request2eid[request]
            return e
        except KeyError:
            if default is not None:
                return default
            raise

    def __setitem__(self, eid: ElevatorId, value: Elevator):
        super().__setitem__(eid, value)
        self.eid2request[eid] = set()


if __name__ == "__main__":

    async def main():
        try:
            async with asyncio.TaskGroup() as tg:
                e = Elevator(id=1)
                await e.start(tg)

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
