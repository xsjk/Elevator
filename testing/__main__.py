import asyncio
import logging
import random
import sys
from enum import IntEnum, auto
from pathlib import Path
from typing import List

from aioconsole import ainput

sys.path.append(str(Path(__file__).parent.parent))


from system.utils.zmq_async import Server

logger = logging.getLogger(__name__)

#######   ELEVATOR PROJECT    #######


### Simple Test Case ###
class PassengerState(IntEnum):
    IN_ELEVATOR_AT_TARGET_FLOOR = auto()  # Passenger in the elevator, has arrived at the target floor
    IN_ELEVATOR_AT_OTHER_FLOOR = auto()  # Passenger in the elevator, but not at the target floor
    OUT_ELEVATOR_AT_TARGET_FLOOR = auto()  # Passenger not in the elevator, has arrived at the target floor
    OUT_ELEVATOR_AT_OTHER_FLOOR = auto()  # Passenger not in the elevator, at a different floor than the target floor


class Passenger:
    def __init__(self, start_floor, target_floor, name="test"):
        self.start_floor: int = start_floor
        self.target_floor: int = target_floor
        self.direction = "up" if self.target_floor > self.start_floor else "down"
        self._elevator_code = -1
        self.current_floor = start_floor
        self.finished = False if self.target_floor != self.start_floor else True
        self.finished_print = False
        self.name = name
        self.matching_signal = f"{self.direction}_floor_arrived@{self.current_floor}"
        self.state = PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR

    def change_state(self, target_state: PassengerState):
        self.state = target_state

    def is_finished(self):
        return self.finished

    def set_elevator_code(self, value):
        self._elevator_code = value

    def get_elevator_code(self):
        return self._elevator_code

    def update_location(self, floor):
        self.current_floor = floor
        self.matching_signal = f"{self.direction}_floor_arrived@{self.current_floor}"

    def __str__(self):
        return f"Passenger({self.name}, {self.start_floor} -> {self.target_floor})"


def generate_passengers(num: int) -> List[Passenger]:
    floors = [-1, 1, 2, 3]
    passenger_names = [f"Passenger_{i + 1}" for i in range(num)]
    passengers = []

    for name in passenger_names:
        start_floor = random.choice(floors)
        target_floor = random.choice([floor for floor in floors if floor != start_floor])
        passengers.append(Passenger(start_floor, target_floor, name))

    return passengers


async def handle_passenger_state(passenger: Passenger, message: str, server: Server, client_addr: str) -> bool:
    match passenger.state:
        case PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR:
            elevator_code = passenger.get_elevator_code()
            if message.endswith(f"floor_arrived@{passenger.target_floor}#{elevator_code}"):
                passenger.update_location(passenger.target_floor)
                passenger.change_state(PassengerState.IN_ELEVATOR_AT_TARGET_FLOOR)

        case PassengerState.IN_ELEVATOR_AT_TARGET_FLOOR:
            elevator_code = passenger.get_elevator_code()
            if message == f"door_opened#{elevator_code}":
                logger.info(f"Passenger {passenger.name} is leaving elevator {elevator_code}")
                passenger.change_state(PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR)
                passenger.finished = True

        case PassengerState.OUT_ELEVATOR_AT_OTHER_FLOOR:
            # Handling elevator arrival at the passenger's start floor
            if message.startswith(passenger.matching_signal) and passenger.current_floor == passenger.start_floor:
                passenger.set_elevator_code(int(message.split("#")[-1]))

            # Handle passenger entering the elevator
            elif message == f"door_opened#{passenger.get_elevator_code()}" and passenger.get_elevator_code() > 0:
                logger.info(f"Passenger {passenger.name} is entering elevator {passenger.get_elevator_code()}")
                await asyncio.sleep(0.5)  # Simulate some delay for entering the elevator
                passenger.change_state(PassengerState.IN_ELEVATOR_AT_OTHER_FLOOR)
                await server.send(client_addr, f"select_floor@{passenger.target_floor}#{passenger.get_elevator_code()}")

        case PassengerState.OUT_ELEVATOR_AT_TARGET_FLOOR:
            if passenger.is_finished() and not passenger.finished_print:
                logger.info(f"Passenger {passenger.name} has reached the target floor.")
                passenger.finished_print = True
                return True

    return False


async def testing(server: Server, client_addr: str):
    try:
        while True:
            try:
                num_passengers = int(await ainput("Enter the number of passengers (>0): "))
                break
            except ValueError:
                logger.warning("Please enter a valid number")

        passengers = generate_passengers(num_passengers)
        logger.info(f"Created {len(passengers)} passengers:")
        for p in passengers:
            logger.info(f"  {p}")

        if not server.clients_addr:
            logger.error("No clients connected!")
            return

        bindedClient = list(server.clients_addr)[0]
        logger.info(f"Starting test for client: {bindedClient}")

        # Reset the client
        await server.send(bindedClient, "reset")
        await asyncio.sleep(1)

        for passenger in passengers:
            await server.send(bindedClient, f"call_{passenger.direction}@{passenger.start_floor}")

        completed = 0

        async for address, message, timestamp in server.messages():
            if address != client_addr:
                continue

            # Check finished passengers
            for passenger in passengers:
                if await handle_passenger_state(passenger, message, server, bindedClient):
                    completed += 1

            if completed == len(passengers):
                logger.info("PASSED: ALL PASSENGERS HAVE ARRIVED AT THEIR TARGET FLOORS!")
                await asyncio.sleep(1)
                await server.send(bindedClient, "reset")
                if address in server.clients_addr:
                    server.clients_addr.remove(address)
                break

    except Exception as e:
        logger.error(f"Error during testing: {e}")
    finally:
        logger.info("Test completed")


async def main():
    server = Server()
    server.start()
    logger.info("Server started. Waiting for clients...")
    try:
        while True:
            try:
                addr = await server.get_next_client()
                logger.info(f"Client connected: {addr}")
                user_input = await ainput(f"Start testing for {addr}? (y/n)\n")
                if user_input.lower() == "y":
                    await testing(server, addr)
            except Exception as e:
                logger.error(f"Error: {e}")

    except asyncio.CancelledError:
        logger.info("Server shutdown requested")
    finally:
        server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
