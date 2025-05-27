import asyncio
import inspect
import logging
from dataclasses import dataclass, field

from .elevator import Elevator, logger
from ..utils.common import (
    Direction,
    DoorDirection,
    ElevatorId,
    Event,
    Floor,
    FloorAction,
)
from ..utils.event_bus import event_bus


@dataclass
class Config:
    floor_travel_duration: float = 3.0  # Time for elevator to travel between floors when running at max speed
    accelerate_duration: float = 3.0  # Time for elevator to accelerate (seconds)
    door_move_duration: float = 1.0  # Time for elevator door to move (seconds)
    door_stay_duration: float = 3.0  # Time elevator door remains open (seconds)
    floors: tuple[str, ...] = ("-1", "1", "2", "3")  # Floors in the building
    default_floor: Floor = Floor("1")  # Default floor to start from
    elevator_count: int = 2  # Number of elevators in the building


@dataclass
class Controller:
    config: Config = field(default_factory=Config)
    requests: set[FloorAction] = field(default_factory=set)  # External requests
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Event queue
    message_tasks: list = field(default_factory=list)

    def __post_init__(self):
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

    def reset(self):
        self.stop()

        # Empty the queue
        while not self.queue.empty():
            self.queue.get_nowait()

        # Clear requests
        self.requests.clear()

        # Reset elevators
        self.__post_init__()

        self.start()

        logger.info("Controller: Elevator system has been reset")

    def start(self, tg: asyncio.TaskGroup | None = None):
        self.control_task = (asyncio if tg is None else tg).create_task(self.control_loop(), name=f"ControllerControlLoop {__file__}:{inspect.stack()[0].lineno}")

    def stop(self):
        if getattr(self, "control_task", None) is not None:
            self.control_task.cancel()
        for t in self.message_tasks:
            t.cancel()
        self.message_tasks.clear()

    async def control_loop(self):
        try:
            logger.debug("Controller: Control loop started")
            async with asyncio.TaskGroup() as tg:
                for e in self.elevators.values():
                    tg.create_task(e.door_loop(), name=f"ElevatorDoorLoop-{e.id} {__file__}:{inspect.stack()[0].lineno}")
                    tg.create_task(e.move_loop(), name=f"ElevatorMoveLoop-{e.id} {__file__}:{inspect.stack()[0].lineno}")
        except asyncio.CancelledError:
            logger.debug("Controller: Control loop cancelled")

    def handle_message_task(self, message: str):
        self.message_tasks.append(asyncio.create_task(self.handle_message(message), name=f"HandleMessage-{message} {__file__}:{inspect.stack()[0].lineno}"))

    async def handle_message(self, message: str):
        try:
            if message == "reset":
                self.reset()

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

        except asyncio.CancelledError:
            pass

    async def get_event_message(self) -> str:
        return await self.queue.get()

    def calculate_duration(self, n_floors: float, n_stops: int) -> float:
        return n_floors * self.config.floor_travel_duration + n_stops * (self.config.door_move_duration * 2 + self.config.door_stay_duration)

    def estimate_arrival_time(self, elevator: Elevator, target_floor: Floor, requested_direction: Direction) -> float:
        logger.setLevel(logging.CRITICAL)
        elevator = elevator.copy()
        elevator.commit_floor(target_floor, requested_direction)

        if elevator.state.is_moving():
            duration = elevator.door_move_duration + elevator.door_stay_duration
        elif target_floor == elevator.current_floor and elevator.commited_direction == requested_direction:
            return elevator.estimate_door_open_time()
        else:
            duration = elevator.estimate_door_close_time() + elevator.door_move_duration + elevator.door_stay_duration

        n_floors, n_stops = elevator.arrival_summary(target_floor, requested_direction)
        duration += self.calculate_duration(n_floors, n_stops)
        logger.setLevel(logging.DEBUG)
        return duration

    async def call_elevator(self, call_floor: Floor, call_direction: Direction):
        assert isinstance(call_floor, Floor)
        assert call_direction in (Direction.UP, Direction.DOWN)

        # Check if the call direction is already requested
        if (call_floor, call_direction) in self.requests:
            logger.info(f"Controller: Floor {call_floor} already requested {call_direction.name.lower()}")
            return

        logger.info(f"Controller: Calling elevator: Floor {call_floor}, Direction {call_direction.name.lower()}")

        # Choose the best elevator (always choose the one that takes the shorter arrival time)
        elevator = min(self.elevators.values(), key=lambda e: self.estimate_arrival_time(e, call_floor, call_direction))
        logger.info(f"Controller: Elevator {elevator.id} selected for call at Floor {call_floor} going {call_direction.name.lower()}")
        directed_target_floor = FloorAction(call_floor, call_direction)
        self.requests.add(directed_target_floor)
        event = elevator.commit_floor(call_floor, call_direction)
        await event.wait()
        self.requests.remove(directed_target_floor)
        event_bus.publish(Event.CALL_COMPLETED, call_floor, call_direction)

    async def select_floor(self, floor: Floor, elevator_id: ElevatorId):
        assert isinstance(floor, Floor)
        assert isinstance(elevator_id, ElevatorId)

        elevator = self.elevators[elevator_id]

        # Check if the floor is already selected
        if floor in elevator.selected_floors:
            logger.info(f"Controller: Floor {floor} already selected for elevator {elevator_id}")
            return

        elevator.selected_floors.add(floor)
        event = elevator.commit_floor(floor, Direction.IDLE)
        await event.wait()
        elevator.selected_floors.remove(floor)
        event_bus.publish(Event.FLOOR_ARRIVED, floor, elevator_id)

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
                await c.handle_message("call_up@1")
                await c.handle_message("call_down@2")

                while True:
                    msg = await c.get_event_message()
                    logger.info(msg)

        except asyncio.CancelledError:
            pass

    asyncio.run(main())
