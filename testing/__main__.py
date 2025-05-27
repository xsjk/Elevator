import asyncio
import logging
import sys
from enum import IntEnum
from pathlib import Path

from aioconsole import ainput

sys.path.append(str(Path(__file__).parent.parent))

from system.utils.zmq_async import Server

logger = logging.getLogger(__name__)

#######   ELEVATOR PROJECT    #######


### Simple Test Case ###
class PassengerState(IntEnum):
    # only for reference, it may be complex in other testcase.
    IN_ELEVATOR_1_AT_TARGET_FLOOR = 1
    IN_ELEVATOR_1_AT_OTHER_FLOOR = 2
    IN_ELEVATOR_2_AT_TARGET_FLOOR = 3
    IN_ELEVATOR_2_AT_OTHER_FLOOR = 4
    OUT_ELEVATOR_0_AT_TARGET_FLOOR = 5
    OUT_ELEVATOR_0_AT_OTHER_FLOOR = 6


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
        self.matching_signal = f"up_floor_arrived@{self.current_floor}" if self.direction == "up" else f"down_floor_arrived@{self.current_floor}"
        self.state = PassengerState.OUT_ELEVATOR_0_AT_OTHER_FLOOR

    def change_state(self, target_state: PassengerState):
        self.state = target_state

    def is_finished(self):
        return self.finished

    def set_elevator_code(self, value):
        self._elevator_code = value

    def get_elevator_code(self):
        return self._elevator_code


async def testing(server: Server, client_addr: str):
    ############ Initialize Passengers ############
    passengers = [Passenger(1, 3, "A"), Passenger(2, 1, "B")]  # There can be many passengers in testcase.
    timeStamp = -1  # default time stamp is -1
    clientMessage = ""  # default received message is ""
    count = 0

    # Get the first connected client address as the test target
    bindedClient = list(server.clients_addr)[0]
    logger.info(f"Starting test for client: {bindedClient}")

    await server.send(bindedClient, "reset")  # Reset the client
    await asyncio.sleep(1)

    for passenger in passengers:
        await server.send(bindedClient, f"call_{passenger.direction}@{passenger.start_floor}")

    ############ Passenger timed automata ############
    while True:
        address, clientMessage, timeStamp = await server.read()
        if address != client_addr:
            continue
        for passenger in passengers:
            match passenger.state:
                case PassengerState.IN_ELEVATOR_1_AT_OTHER_FLOOR:
                    if clientMessage.endswith(f"floor_arrived@{passenger.target_floor}#{passenger.get_elevator_code()}"):
                        passenger.current_floor = passenger.target_floor
                        passenger.change_state(PassengerState.IN_ELEVATOR_1_AT_TARGET_FLOOR)

                case PassengerState.IN_ELEVATOR_1_AT_TARGET_FLOOR:
                    if clientMessage == "door_opened#1":
                        logger.info(f"Passenger {passenger.name} is leaving the elevator")
                        passenger.change_state(PassengerState.OUT_ELEVATOR_0_AT_TARGET_FLOOR)
                        passenger.finished = True

                case PassengerState.IN_ELEVATOR_2_AT_OTHER_FLOOR:
                    # Not exec in this naive testcase
                    if clientMessage.endswith(f"floor_arrived@{passenger.target_floor}#{passenger.get_elevator_code()}"):
                        passenger.current_floor = passenger.target_floor
                        passenger.change_state(PassengerState.IN_ELEVATOR_2_AT_TARGET_FLOOR)

                case PassengerState.IN_ELEVATOR_2_AT_TARGET_FLOOR:
                    if clientMessage == "door_opened#2":
                        logger.info(f"Passenger {passenger.name} is leaving the elevator")
                        passenger.change_state(PassengerState.OUT_ELEVATOR_0_AT_TARGET_FLOOR)
                        passenger.finished = True

                case PassengerState.OUT_ELEVATOR_0_AT_OTHER_FLOOR:
                    if clientMessage.startswith(passenger.matching_signal) and passenger.current_floor == passenger.start_floor:
                        passenger.set_elevator_code(int(clientMessage.split("#")[-1]))

                    if clientMessage == f"door_opened#{passenger.get_elevator_code()}":
                        logger.info(f"Passenger {passenger.name} is entering elevator {passenger.get_elevator_code()}")
                        await asyncio.sleep(1)
                        if passenger.get_elevator_code() == 1:
                            passenger.change_state(PassengerState.IN_ELEVATOR_1_AT_OTHER_FLOOR)
                        elif passenger.get_elevator_code() == 2:
                            passenger.change_state(PassengerState.IN_ELEVATOR_2_AT_OTHER_FLOOR)
                        await server.send(bindedClient, f"select_floor@{passenger.target_floor}#{passenger.get_elevator_code()}")

                case PassengerState.OUT_ELEVATOR_0_AT_TARGET_FLOOR:
                    if passenger.is_finished() and not passenger.finished_print:
                        logger.info(f"Passenger {passenger.name} has reached the target floor.")
                        passenger.finished_print = True
                        count += 1

        if count == len(passengers):
            logger.info("PASSED: ALL PASSENGERS HAS ARRIVED AT THE TARGET FLOOR!")
            await asyncio.sleep(1)
            await server.send(bindedClient, "reset")
            server.clients_addr.remove(address)
            break


async def main():
    server = Server()
    server.start()

    try:
        while True:
            addr = await server.get_next_client()
            user_input = await ainput(f"Start testing for {addr}? (y/n)\n")
            if user_input.lower() == "y":
                await testing(server, addr)

    except asyncio.CancelledError:
        logger.info("Program cancelled")
    finally:
        server.stop()


if __name__ == "__main__":
    asyncio.run(main())
