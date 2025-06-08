import asyncio
from enum import IntEnum, auto
from typing import Iterable, Self, overload


class Event(IntEnum):
    ELEVATOR_STATE_CHANGED = auto()
    ELEVATOR_FLOOR_CHANGED = auto()
    ELEVATOR_UPDATED = auto()  # visualizer should subscribe to this event to animate elevator movement and door opening/closing
    CALL_COMPLETED = auto()
    FLOOR_ARRIVED = auto()


class Direction(IntEnum):
    UP = 1
    DOWN = -1
    IDLE = 0

    def __neg__(self) -> Self:
        return self.__class__(-self.value)


class DoorDirection(IntEnum):
    OPEN = 1
    CLOSE = -1
    STAY = 0

    def __neg__(self) -> Self:
        return self.__class__(-self.value)


class DoorState(IntEnum):
    OPENED = auto()
    CLOSED = auto()
    OPENING = auto()
    CLOSING = auto()

    def is_open(self) -> bool:
        return self != DoorState.CLOSED


class ElevatorState(IntEnum):
    MOVING_UP = auto()
    MOVING_DOWN = auto()
    STOPPED_DOOR_CLOSED = auto()
    STOPPED_DOOR_OPENED = auto()
    OPENING_DOOR = auto()
    CLOSING_DOOR = auto()

    def get_moving_direction(self) -> Direction:
        match self:
            case ElevatorState.MOVING_UP:
                return Direction.UP
            case ElevatorState.MOVING_DOWN:
                return Direction.DOWN
            case _:
                return Direction.IDLE

    def get_door_state(self) -> DoorState:
        match self:
            case ElevatorState.STOPPED_DOOR_OPENED:
                return DoorState.OPENED
            case ElevatorState.OPENING_DOOR:
                return DoorState.OPENING
            case ElevatorState.CLOSING_DOOR:
                return DoorState.CLOSING
            case _:
                return DoorState.CLOSED

    def is_door_open(self) -> bool:
        return self.get_door_state().is_open()

    def is_moving(self) -> bool:
        return self in (ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN)


type ElevatorId = int
type FloorLike = Floor | int | str


class Floor(int):
    min = -1
    max = 3

    def __new__(cls, value: FloorLike) -> Self:
        if isinstance(value, cls):
            return value
        index = int(value)
        if index < 0:
            index += 1
        return super().__new__(cls, index)

    def __str__(self) -> str:
        index = int(self)
        return str(index if index > 0 else index - 1)

    def __repr__(self) -> str:
        return f"Floor({str(self)})"

    @overload
    def __add__(self, other: int) -> Self: ...

    @overload
    def __add__(self, other: float) -> float: ...

    def __add__(self, other):
        if isinstance(other, int):
            return super().__new__(self.__class__, int(self) + other)
        elif isinstance(other, float):
            return float(self) + other
        else:
            raise TypeError(f"Unsupported operand type(s) for +: 'Floor' and '{type(other).__name__}'")

    @overload
    def __sub__(self, other: Self) -> int: ...  # type: ignore

    @overload
    def __sub__(self, other: int) -> Self: ...

    @overload
    def __sub__(self, other: float) -> float: ...

    def __sub__(self, other):
        if isinstance(other, self.__class__):
            return int(self) - int(other)
        elif isinstance(other, int):
            return super().__new__(self.__class__, int(self) - other)
        elif isinstance(other, float):
            return float(self) - other
        else:
            raise TypeError(f"Unsupported operand type(s) for -: 'Floor' and '{type(other).__name__}'")

    def direction_to(self, other: Self) -> Direction:
        """Get the direction from the current floor to another floor."""
        if self < other:
            return Direction.UP
        elif self > other:
            return Direction.DOWN
        else:
            return Direction.IDLE

    def between(self, other1: Self, other2: Self) -> bool:
        """Check if the current floor is between two other floors."""
        return (self > other1 and self < other2) or (self < other1 and self > other2)

    def is_of(self, direction: Direction, other: Self) -> bool:
        """Check if the current floor is in the direction of another floor."""
        match direction:
            case Direction.UP:
                return self < other
            case Direction.DOWN:
                return self > other
            case _:
                return False


class FloorAction(tuple[Floor, Direction]):
    def __new__(cls, floor: FloorLike, direction: Direction):
        return super().__new__(cls, (Floor(floor), direction))

    def __repr__(self) -> str:
        return f"({self[0]}, {self[1].name})"

    @property
    def floor(self) -> Floor:
        return self[0]

    @property
    def direction(self) -> Direction:
        return self[1]


class Strategy(IntEnum):
    GREEDY = auto()
    OPTIMAL = auto()


class DestinationHeuristic(IntEnum):
    NONE = auto()
    NEAREST = auto()
    FURTHEST = auto()
    MEAN = auto()


async def cancel(tasks: Iterable[asyncio.Task], *, message: str = "exit") -> None:
    error: asyncio.CancelledError | None = None
    for task in tasks:
        if not task.done():
            task.cancel(message)
            try:
                await task
            except asyncio.CancelledError as e:
                if str(e) != message:
                    error = e
    if error:
        raise error


if __name__ == "__main__":
    # Example usage
    floor1 = Floor("1")
    floor2 = Floor("2")
    print(type(floor2 - floor1))
    print(floor1)  # Output: 1
    print(floor2)  # Output: 2
    floor1 -= 1
    print(type(floor1))  # Output: <class '__main__.Floor'>
    print(str(floor1))  # Output: -1
