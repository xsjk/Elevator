import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator

from ..utils.common import (
    Direction,
    DoorDirection,
    ElevatorId,
    Event,
    Floor,
    FloorAction,
)
from ..utils.event_bus import event_bus
from .elevator import Elevator, logger


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
    requests: set[FloorAction] = field(default_factory=set)  # External elevator call requests
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # Event queue for inter-component communication
    message_tasks: dict[str, asyncio.Task] = field(default_factory=dict)  # Tasks for handling messages, each task should handle asyncio.CancelledError in its implementation

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

    async def reset(self):
        await self.stop()

        # Empty the queue
        while not self.queue.empty():
            self.queue.get_nowait()

        # Reset elevators
        self.__post_init__()

        self.start()

        logger.info("Controller: Elevator system has been reset")

    def start(self, tg: asyncio.TaskGroup | None = None):
        for e in self.elevators.values():
            e.start(tg)

    async def stop(self):
        for e in self.elevators.values():
            await e.stop()

        current_task = asyncio.current_task()
        for t in list(self.message_tasks.values()):
            if t is not current_task:
                t.cancel()
                await t

        assert len(self.requests) == 0
        for e in self.elevators.values():
            assert len(e.selected_floors) == 0

    def handle_message_task(self, message: str) -> asyncio.Task:
        assert message not in self.message_tasks, f"Controller: Message task for '{message}' already exists"

        logger.debug(f"Controller: Existing tasks: {list(self.message_tasks)}")

        async def wrapper():
            try:
                await self.handle_message(message)
            except asyncio.CancelledError:
                logger.debug(f"Controller: Message task for '{message}' cancelled")
            except Exception as e:
                logger.error(f"Controller: Error while handling message '{message}': {e}")
                raise e
            finally:
                self.message_tasks.pop(message)

        self.message_tasks[message] = asyncio.create_task(wrapper(), name=f"HandleMessage-{message} {__file__}:{inspect.stack()[0].lineno}")
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

    def calculate_duration(self, n_floors: float, n_stops: int) -> float:
        return n_floors * self.config.floor_travel_duration + n_stops * (self.config.door_move_duration * 2 + self.config.door_stay_duration)

    def estimate_arrival_time(self, elevator: Elevator, target_floor: Floor, requested_direction: Direction) -> float:
        old_level = logger.level
        logger.setLevel(logging.CRITICAL)
        elevator = elevator.copy()
        elevator.commit_floor(target_floor, requested_direction)

        if elevator.state.is_moving():
            duration = elevator.door_move_duration + elevator.door_stay_duration
        elif target_floor == elevator.current_floor and elevator.committed_direction == requested_direction:
            return elevator.estimate_door_open_time()
        else:
            duration = elevator.estimate_door_close_time() + elevator.door_move_duration + elevator.door_stay_duration

        n_floors, n_stops = elevator.arrival_summary(target_floor, requested_direction)
        duration += self.calculate_duration(n_floors, n_stops)
        logger.setLevel(old_level)
        logger.debug(f"Controller: Estimation details - Elevator ID: {elevator.id}, Target Floor: {target_floor}, Requested Direction: {requested_direction.name}, Number of Floors: {n_floors}, Number of Stops: {n_stops}, Estimated Duration: {duration:.2f} seconds")
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
        enabled_elevators = [e for e in self.elevators.values() if e.started]
        if not enabled_elevators:
            logger.warning(f"Controller: No enabled elevators available for call at Floor {call_floor} going {call_direction.name.lower()}")
            return

        elevator = min(enabled_elevators, key=lambda e: self.estimate_arrival_time(e, call_floor, call_direction))
        logger.info(f"Controller: Elevator {elevator.id} selected for call at Floor {call_floor} going {call_direction.name.lower()}")
        directed_target_floor = FloorAction(call_floor, call_direction)

        try:
            self.requests.add(directed_target_floor)
            await elevator.commit_floor(call_floor, call_direction).wait()
            event_bus.publish(Event.CALL_COMPLETED, call_floor, call_direction)
        except asyncio.CancelledError:
            pass
        finally:
            self.requests.remove(directed_target_floor)
            elevator.cancel_commit(call_floor, call_direction)

    async def cancel_call(self, call_floor: Floor, call_direction: Direction):
        assert isinstance(call_floor, Floor)
        assert call_direction in (Direction.UP, Direction.DOWN)

        directed_target_floor = FloorAction(call_floor, call_direction)
        key = f"call_{call_direction.name.lower()}@{call_floor}"
        assert directed_target_floor in self.requests
        assert key in self.message_tasks

        # Cancel the task associated with the elevator call
        t = self.message_tasks[key]
        t.cancel()
        await t
        assert directed_target_floor not in self.requests

    async def select_floor(self, floor: Floor, elevator_id: ElevatorId):
        assert isinstance(floor, Floor)
        assert isinstance(elevator_id, ElevatorId)

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
        except asyncio.CancelledError:
            pass
        finally:
            elevator.selected_floors.remove(floor)
            elevator.cancel_commit(floor, Direction.IDLE)

    async def deselect_floor(self, floor: Floor, elevator_id: ElevatorId):
        assert isinstance(floor, Floor)
        assert isinstance(elevator_id, ElevatorId)

        elevator = self.elevators[elevator_id]

        # Check if the floor is already selected
        key = f"select_floor@{floor}#{elevator_id}"
        assert floor in elevator.selected_floors
        assert key in self.message_tasks

        # Cancel the task associated with the floor selection and wait for it to finishs
        t = self.message_tasks[key]
        t.cancel()
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
