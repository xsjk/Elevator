import asyncio
import random
from dataclasses import dataclass, field
from enum import IntEnum, auto


class PassengerState(IntEnum):
    IN_ELEVATOR_AT_TARGET_FLOOR = auto()
    IN_ELEVATOR_AT_OTHER_FLOOR = auto()
    OUT_ELEVATOR_AT_TARGET_FLOOR = auto()
    OUT_ELEVATOR_AT_OTHER_FLOOR = auto()


@dataclass
class Passenger:
    start_floor: int
    target_floor: int
    name: str = "test"
    state: PassengerState = PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    def __post_init__(self):
        # Initialize passenger properties
        self.direction = "up" if self.target_floor > self.start_floor else "down"
        self._elevator_code = -1
        self.current_floor = self.start_floor
        self.finished = self.target_floor == self.start_floor
        self.matching_signal = f"{self.direction}_floor_arrived@{self.current_floor}"
        # Initial call request
        if not self.finished:
            self.queue.put_nowait(f"call_{self.direction}@{self.start_floor}")

    def __str__(self):
        return f"Passenger({self.name}, {self.start_floor} -> {self.target_floor})"

    def __hash__(self) -> int:
        return hash((self.start_floor, self.target_floor, self.name))

    async def handle_message(self, message: str) -> bool:
        # Process elevator messages based on passenger state
        match self.state:
            case PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR:
                # Check elevator arrival at target floor
                if message.endswith(f"floor_arrived@{self.target_floor}#{self._elevator_code}"):
                    self.current_floor = self.target_floor
                    self.matching_signal = f"{self.direction}_floor_arrived@{self.current_floor}"
                    self.state = PassengerState.IN_ELEVATOR_AT_TARGET_FLOOR
            case PassengerState.IN_ELEVATOR_AT_TARGET_FLOOR:
                # Check door opened at target floor
                if message == f"door_opened#{self._elevator_code}":
                    self.state = PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR
                    self.finished = True
            case PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR:
                # Elevator arrives at start floor
                if message.startswith(self.matching_signal) and self.current_floor == self.start_floor:
                    self._elevator_code = int(message.split("#")[-1])
                elif message == f"door_opened#{self._elevator_code}" and self._elevator_code > 0:
                    # Enter elevator
                    await asyncio.sleep(0.1)
                    self.state = PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR
                    # Request target floor
                    self.queue.put_nowait(f"select_floor@{self.target_floor}#{self._elevator_code}")
            case PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR:
                # Passenger has finished
                return True
        return self.finished and self.state == PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR


def generate_passengers(num: int, queue: asyncio.Queue, floors=None, force_different=True) -> list[Passenger]:
    """Generate random passengers

    Args:
        num: Number of passengers to generate
        queue: Message queue for passengers
        floors: List of floors to use (default: [-1, 1, 2, 3])
        force_different: Force target floor to be different from start floor

    Returns:
        List of generated passengers
    """
    floors = floors or [-1, 1, 2, 3]
    passengers: list[Passenger] = []
    for i in range(num):
        start = random.choice(floors)
        if force_different:
            target = random.choice([f for f in floors if f != start])
        else:
            target = random.choice(floors)
        passengers.append(Passenger(start, target, f"P_{i + 1}", queue=queue))
    return passengers
