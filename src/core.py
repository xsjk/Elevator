import asyncio
import bisect
import logging
from dataclasses import dataclass, field
from itertools import chain
from typing import Self, SupportsIndex
from copy import copy


from utils.event_bus import event_bus
from utils.common import (
    FloorAction,
    Direction,
    DoorState,
    ElevatorId,
    ElevatorState,
    Event,
    Floor,
    DoorDirection,
)

logger = logging.getLogger(__name__)


class TargetFloors(list):
    """
    Actions is a list of tuples (floor, direction) that represents the actions of the elevator.
    The direction is either UP or DOWN.
    The list is sorted based on the direction and floor number.
    """

    def __init__(self, direction: Direction):
        super().__init__()
        self.direction = direction
        self.nonemptyEvent = asyncio.Event()

    def add(self, floor: Floor, direction: Direction):
        assert direction in (Direction.IDLE, self.direction), "Direction of requested action is not the same as the chain direction"
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
    def __init__(self, direction: Direction = Direction.IDLE):
        self.current_chain = TargetFloors(direction)
        self.next_chain = TargetFloors(-direction)
        self.future_chain = TargetFloors(direction)

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

    def pop(self) -> FloorAction:
        if len(self.current_chain) > 0:
            a = self.current_chain.pop(0)
            if len(self) > 0:
                while len(self.current_chain) == 0:
                    # If the current chain is empty, we need to swap the next and future chains
                    self.current_chain = self.next_chain
                    self.next_chain = self.future_chain
                    self.future_chain = TargetFloors(self.direction)
            else:
                self.direction = Direction.IDLE
            return a
        raise IndexError("No actions in the current chain")

    def top(self) -> FloorAction:
        if len(self.current_chain) > 0:
            return self.current_chain[0]
        raise IndexError("No actions in the current chain")

    async def get(self) -> FloorAction:
        await self.current_chain.nonemptyEvent.wait()
        assert len(self.current_chain) > 0
        return self.current_chain[0]

    def is_empty(self) -> bool:
        return self.current_chain.is_empty()

    def clear(self):
        self.current_chain.clear()
        self.next_chain.clear()
        self.future_chain.clear()

    def __copy__(self) -> Self:
        c = self.__class__(self.direction)
        c.current_chain = self.current_chain.copy()
        c.next_chain = self.next_chain.copy()
        c.future_chain = self.future_chain.copy()
        return c

    def __len__(self) -> int:
        return len(self.current_chain) + len(self.next_chain) + len(self.future_chain)

    def __iter__(self) -> FloorAction:
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

    queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # the queue to put events in

    _current_floor: Floor = Floor("1")  # Initial floor
    _state: ElevatorState = ElevatorState.STOPPED_DOOR_CLOSED
    selected_floors: set[Floor] = field(default_factory=set)  # Internal button target floors

    # Internal state

    # Floors that the elevator will go to one by one, direction is the requested going direction after the elevator arrives at the floor.
    ## For example, if the elevator is at floor 1 and the user selects floor 3 and 4, the commited floors can be:
    ## [(3, IDLE), (4, IDLE), (5, DOWN), (4, DOWN), (2, DOWN), (3, UP), (4, UP)]
    ## After the elevator arrives at floor 5 and user selects floor 1, 2, 4 and 6, the commited floors will be:
    ## [(4, IDLE), (4, DOWN), (2, IDLE), (2, DOWN), (1, IDLE), (3, UP), (4, UP)]
    # e.g. []
    target_floor_chains: TargetFloorChains = field(default_factory=TargetFloorChains)  # Planned actions including current, next and future plans
    events: dict[FloorAction, asyncio.Event] = field(default_factory=dict)

    _moving_timestamp: float = 0.0  # Timestamp when movement starts
    _position_percentage: float = 0.0  # Position between floors
    _door_position_percentage: float = 0.0  # Door position

    door_loop_started: bool = False
    move_loop_started: bool = False

    door_action_queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Queue for actions to be executed

    def copy(self) -> Self:
        c = copy(self)
        c.target_floor_chains = copy(self.target_floor_chains)
        c.events = {k: asyncio.Event() for k in self.events}
        c.door_action_queue = asyncio.Queue()
        return c

    def commit_door(self, door_state: DoorDirection):
        if not self.door_loop_started:
            logger.warning(f"door_loop of elevator {self.id} was not started yet.")

        self.door_action_queue.put_nowait(door_state)  # the queue is consumed at door_loop

    def commit_floor(self, floor: Floor, requested_direction: Direction = Direction.IDLE) -> asyncio.Event:
        """
        Commit a floor to the elevator's list of target floors.

        Args:
            floor (Floor): The floor to commit.
            direction (Direction): The requested direction when the elevator arrives at the floor.
                - When it is IDLE, it means the request is from the internal button selected by the user.
                - When it is UP or DOWN, it means the request is from the external call up/down button.
        """

        if not self.move_loop_started:
            logger.warning(f"move_loop of elevator {self.id} was not started yet.")

        logger.debug(f"Committing floor {floor} with direction {requested_direction.name}")

        directed_floor = FloorAction(floor, requested_direction)
        if directed_floor in self.target_floor_chains:
            raise ValueError(f"Floor {floor} already in the action chain with direction {requested_direction.name}")

        assert isinstance(floor, Floor)
        assert isinstance(requested_direction, Direction)

        target_direction = self.direction_to(floor)

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
        logger.debug(self.target_floor_chains)

        self.events[directed_floor] = asyncio.Event()
        return self.events[directed_floor]

    def cancel_commit(self, floor: Floor, requested_direction: Direction = Direction.IDLE):
        directed_floor = FloorAction(floor, requested_direction)
        # Remove the action from the chain
        for floor_chain in (self.target_floor_chains.current_chain, self.target_floor_chains.next_chain, self.target_floor_chains.future_chain):
            if directed_floor in floor_chain:
                floor_chain.remove(directed_floor)
                event = self.events.pop(directed_floor)
                event.set()
                return

        raise ValueError(f"Floor {floor} not in action chain")

    def arrival_summary(self, floor: Floor, requested_direction: Direction) -> tuple[float, int]:
        directed_floor = FloorAction(floor, requested_direction)
        if directed_floor not in self.target_floor_chains:
            raise ValueError(f"Floor {floor} not in action chain")

        current_floor = self.current_position

        n_floors = 0.0
        n_stops = 0
        for a in iter(self.target_floor_chains):
            n_floors += abs(a.floor - current_floor)
            if a == directed_floor:
                break
            n_stops += 1

            current_floor = a.floor

        return n_floors, n_stops

    def pop_target(self) -> FloorAction:
        """
        Pop the next action from the elevator's list of target floors.
        """
        if self.target_floor_chains.is_empty():
            raise IndexError("No actions in the current chain")

        directed_floor = self.target_floor_chains.pop()
        event = self.events.pop(directed_floor)
        event.set()
        logger.debug(f"Action popped: {directed_floor}")
        logger.debug(self.target_floor_chains)
        return directed_floor

    async def move_loop(self):
        """
        Main loop for the elevator. This function will be called in a separate async task.

        It really updates `self.current_floor` and `self.door_state` attributes.
        It should also trigger the update of the animation of the elevator.
        """
        try:
            self.move_loop_started = True
            while True:
                # Wait the elevator to be idle so that it can move
                logger.debug("Wait for target floor chains")

                target_floor, direction = await self.target_floor_chains.get()

                # Start the elevator movement (move from current floor to target floor)
                if self.current_floor < target_floor:
                    self.state = ElevatorState.MOVING_UP
                    # TODO trigger animation
                    await asyncio.sleep(self.floor_travel_duration)
                    self.current_floor += 1
                elif self.current_floor > target_floor:
                    self.state = ElevatorState.MOVING_DOWN
                    # TODO trigger animation
                    await asyncio.sleep(self.floor_travel_duration)
                    self.current_floor -= 1
                else:
                    self.state = ElevatorState.STOPPED_DOOR_CLOSED
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
                        target_floor, direction = self.target_floor_chains.top()
                        assert target_floor != self.current_floor
                        if target_floor > self.current_floor:
                            self.queue.put_nowait(f"up_{msg}")
                        else:  # target_floor < self.current_floor
                            self.queue.put_nowait(f"down_{msg}")

                    # Open the door
                    self.commit_door(DoorDirection.OPEN)

                # Signal that the floor as arrived
        except asyncio.CancelledError:
            logger.debug("Move loop cancelled")
            pass

        finally:
            self.move_loop_started = False
            pass

    async def door_loop(self):
        async def close_door(duration=self.door_move_duration):
            nonlocal door_last_close_start
            try:
                door_last_close_start = asyncio.get_event_loop().time()
                self.state = ElevatorState.CLOSING_DOOR
                await asyncio.sleep(duration)
                self.state = ElevatorState.STOPPED_DOOR_CLOSED
                self.queue.put_nowait(f"door_closed#{self.id}")
            except asyncio.CancelledError:
                pass

        async def open_door(duration=self.door_move_duration):
            self.state = ElevatorState.OPENING_DOOR
            await asyncio.sleep(duration)
            self.state = ElevatorState.STOPPED_DOOR_OPENED
            self.queue.put_nowait(f"door_opened#{self.id}")
            await asyncio.sleep(self.door_stay_duration)
            await close_door()

        door_last_close_start: float | None = None
        task: asyncio.Task | None = None

        try:
            self.door_loop_started = True
            while True:
                # TODO: Implement door state commit
                # 1. Door opening cannot be interrupted by door close
                # 2. Door closing can be interrupted by door open
                # 3. Door cannot commit when the elevator is moving

                logger.debug("Wait for door action queue")
                action = await self.door_action_queue.get()
                match self.state:
                    case ElevatorState.MOVING_UP | ElevatorState.MOVING_DOWN | ElevatorState.OPENING_DOOR:
                        logger.info("Cannot commit door state while the elevator is moving or opening")
                    case ElevatorState.STOPPED_DOOR_CLOSED:
                        if action == DoorDirection.OPEN:
                            task = asyncio.create_task(open_door())
                    case ElevatorState.CLOSING_DOOR:
                        assert task is not None
                        assert door_last_close_start is not None

                        if action == DoorDirection.OPEN:
                            task.cancel()
                            await task
                            assert task.cancelled() or task.done()
                            duration = asyncio.get_event_loop().time() - door_last_close_start
                            logger.info(f"Door closing is interrupted after {duration}")
                            task = asyncio.create_task(open_door(duration))

                    case ElevatorState.STOPPED_DOOR_OPENED:
                        assert task is not None
                        if action == DoorDirection.CLOSE:
                            task = asyncio.create_task(close_door())
        except asyncio.CancelledError:
            logger.debug("Door loop cancelled")
            pass
        finally:
            self.door_loop_started = False

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

        # Log state change
        logger.debug(f"Elevator {self.id} state changed to {new_state.name}, door_open={self.door_open}, direction={self.commited_direction}")

        # Publish event for state change
        if old_state != new_state:
            event_bus.publish(Event.ELEVATOR_STATE_CHANGED, self.id, self.current_floor, self.door_state, self.commited_direction)

    @property
    def current_floor(self) -> Floor:
        return self._current_floor

    @current_floor.setter
    def current_floor(self, new_floor: Floor):
        if self._current_floor != new_floor:
            self._current_floor = new_floor

            # Log floor change
            logger.debug(f"Elevator {self.id} floor changed to {new_floor}")

            # Publish event for floor change
            event_bus.publish(Event.ELEVATOR_FLOOR_CHANGED, self.id, self.current_floor, self.door_state, self.commited_direction)

    @property
    def current_position(self) -> float:
        # Calculate the real current floor based on the position percentage
        return self._current_floor + self._position_percentage

    def direction_to(self, target_floor: Floor) -> Direction:
        if target_floor > self.current_position:
            return Direction.UP
        elif target_floor < self.current_position:
            return Direction.DOWN
        else:
            return Direction.IDLE

    @property
    def position_percentage(self) -> float:
        return self._position_percentage

    @position_percentage.setter
    def position_percentage(self, new_percentage: float):
        if self._position_percentage != new_percentage:
            self._position_percentage = new_percentage
            event_bus.publish(Event.ELEVATOR_UPDATED, self.id, self.current_floor, self.commited_direction, self.position_percentage, self.door_state, self.door_position_percentage)

    @property
    def door_position_percentage(self) -> float:
        return self._door_position_percentage

    @door_position_percentage.setter
    def door_position_percentage(self, new_percentage: float):
        if self._door_position_percentage != new_percentage:
            self._door_position_percentage = new_percentage
            event_bus.publish(Event.ELEVATOR_UPDATED, self.id, self.current_floor, self.commited_direction, self.position_percentage, self.door_state, self.door_position_percentage)

    @property
    def door_state(self) -> DoorState:
        return self.state.get_door_state()

    @door_state.setter
    def door_state(self, new_state: DoorState):
        raise NotImplementedError("Door state cannot be set directly.")

    @property
    def commited_direction(self) -> Direction:
        if self.target_floor_chains.is_empty():
            return Direction.IDLE
        return self.target_floor_chains.direction


@dataclass
class ElevatorControllerConfig:
    floor_travel_duration: float = 3.0  # Time for elevator to travel between floors when running at max speed
    accelerate_duration: float = 1.0  # Time for elevator to accelerate (seconds)
    door_move_duration: float = 1.0  # Time for elevator door to move (seconds)
    door_stay_duration: float = 3.0  # Time elevator door remains open (seconds)
    floors: tuple[str, ...] = ("-1", "1", "2", "3")  # Floors in the building
    elevator_count: int = 2  # Number of elevators in the building


@dataclass
class ElevatorController:
    config: ElevatorControllerConfig = field(default_factory=ElevatorControllerConfig)
    requests: set[FloorAction] = field(default_factory=set)  # External requests
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Event queue

    def __post_init__(self):
        self.reset()

    def reset(self):
        if getattr(self, "task", None) is not None:
            self.task.cancel()

        # Empty the queue
        while not self.queue.empty():
            self.queue.get_nowait()

        self.elevators = {
            i: Elevator(
                id=i,
                queue=self.queue,
                floor_travel_duration=self.config.floor_travel_duration,
                accelerate_duration=self.config.accelerate_duration,
                door_move_duration=self.config.door_move_duration,
                door_stay_duration=self.config.door_stay_duration,
            )
            for i in range(1, self.config.elevator_count + 1)
        }
        self.task = asyncio.create_task(self.control_loop())

    async def control_loop(self):
        try:
            logger.debug("Control loop started")
            async with asyncio.TaskGroup() as tg:
                for e in self.elevators.values():
                    tg.create_task(e.door_loop())
                    tg.create_task(e.move_loop())
        except asyncio.CancelledError:
            logger.debug("Control loop cancelled")

    def handle_message_task(self, message: str):
        asyncio.create_task(self.handle_message(message))

    async def handle_message(self, message: str):
        if message == "reset":
            self.__post_init__()
            logger.info("Elevator system has been reset")

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
            self.open_door(elevator)

        elif message.startswith("close_door#"):
            elevator_id = int(message.split("#")[1])
            elevator = self.elevators[elevator_id]
            self.close_door(elevator)

    def calculate_duration(self, n_floors: float, n_stops: int) -> float:
        return n_floors * self.config.floor_travel_duration + n_stops * (self.config.door_move_duration * 2 + self.config.door_stay_duration)

    def estimate_arrival_time(self, elevator: Elevator, target_floor: Floor, requested_direction: Direction) -> float:
        logger.setLevel(logging.CRITICAL)
        elevator = elevator.copy()
        elevator.commit_floor(target_floor, requested_direction)
        n_floors, n_stops = elevator.arrival_summary(target_floor, requested_direction)
        duration = self.calculate_duration(n_floors, n_stops)
        logger.setLevel(logging.DEBUG)
        return duration

    async def call_elevator(self, call_floor: Floor, call_direction: Direction):
        assert isinstance(call_floor, Floor)
        assert call_direction in (Direction.UP, Direction.DOWN)

        # Check if the call direction is already requested
        if (call_floor, call_direction) in self.requests:
            logger.info(f"Floor {call_floor} already requested {call_direction.name.lower()}")
            return

        logger.info(f"Calling elevator: Floor {call_floor}, Direction {call_direction}")

        # Choose the best elevator (always choose the one that takes the shorter arrival time)
        elevator = min(self.elevators.values(), key=lambda e: self.estimate_arrival_time(e, call_floor, call_direction))
        directed_target_floor = FloorAction(call_floor, call_direction)
        self.requests.add(directed_target_floor)
        event = elevator.commit_floor(call_floor, call_direction)
        await event.wait()
        self.requests.remove(directed_target_floor)

    async def select_floor(self, floor: Floor, elevator_id: ElevatorId):
        assert isinstance(floor, Floor)
        assert isinstance(elevator_id, ElevatorId)

        elevator = self.elevators[elevator_id]

        # Check if the floor is already selected
        if floor in elevator.selected_floors:
            logger.info(f"Floor {floor} already selected for elevator {elevator_id}")
            return

        elevator.selected_floors.add(floor)
        event = elevator.commit_floor(floor, Direction.IDLE)
        await event.wait()
        elevator.selected_floors.remove(floor)

    def open_door(self, elevator: Elevator):
        elevator.commit_door(DoorDirection.OPEN)
        # TODO: await self.client.send(f"door_opened#{elevator.id}")

    def close_door(self, elevator: Elevator):
        elevator.commit_door(DoorDirection.CLOSE)
        # TODO: await self.client.send(f"door_closed#{elevator.id}")


if __name__ == "__main__":
    c = ElevatorController()

    e = Elevator(1)

    event_bus.subscribe(Event.FLOOR_ARRIVED, lambda direction, floor: logger.info(f"Floor {floor} arrived with direction {direction.name}"))
    event_bus.subscribe(Event.DOOR_CLOSED, lambda direction, floor: logger.info(f"Door closed at floor {floor} with direction {direction.name}"))
    event_bus.subscribe(Event.DOOR_OPENED, lambda direction, floor: logger.info(f"Door opened at floor {floor} with direction {direction.name}"))

    e.commit_floor(Floor("3"), Direction.IDLE)
    e.commit_floor(Floor("1"), Direction.UP)
    e.commit_floor(Floor("-1"), Direction.UP)

    async def run_all():
        await asyncio.gather(
            e.move_loop(),
            e.door_loop(),
        )

    asyncio.run(run_all())
