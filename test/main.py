import asyncio
import logging
import sys
from enum import IntEnum
from pathlib import Path

from aioconsole import ainput

sys.path.append(str(Path(__file__).parent.parent))

from utils.zmq_async import Server

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

    def change_state(self, target_state: PassengerState) -> str:
        self.state = target_state

    def is_finished(self):
        return self.finished

    def set_elevator_code(self, value):
        self._elevator_code = value

    def get_elevator_code(self):
        return self._elevator_code


async def testing(server: Server):
    async def is_received_new_message(oldTimeStamp: int, oldServerMessage: str, Msgunprocessed: bool = False) -> tuple:
        if Msgunprocessed:
            return True, oldTimeStamp, oldServerMessage
        else:
            try:
                address, message, timestamp = await asyncio.wait_for(server.read(), timeout=0.01)
                if address == bindedClient:
                    return True, timestamp, message
                else:
                    return False, oldTimeStamp, oldServerMessage
            except asyncio.TimeoutError:
                return False, oldTimeStamp, oldServerMessage

    ############ Initialize Passengers ############
    passengers = [Passenger(1, 3, "A")]  # There can be many passengers in testcase.
    timeStamp = -1  # default time stamp is -1
    clientMessage = ""  # default received message is ""
    messageUnprocessed = False  # Used when receiving new message
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
        for each_passenger in passengers:
            result, timeStamp, clientMessage = await is_received_new_message(timeStamp, clientMessage, messageUnprocessed)
            messageUnprocessed = False

            if result:
                match each_passenger.state:
                    case PassengerState.IN_ELEVATOR_1_AT_OTHER_FLOOR:
                        if clientMessage.endswith(f"floor_arrived@{each_passenger.target_floor}#{each_passenger.get_elevator_code()}"):
                            each_passenger.current_floor = each_passenger.target_floor
                            each_passenger.change_state(PassengerState.IN_ELEVATOR_1_AT_TARGET_FLOOR)

                    case PassengerState.IN_ELEVATOR_1_AT_TARGET_FLOOR:
                        if clientMessage == "door_opened#1":
                            logger.info(f"Passenger {each_passenger.name} is leaving the elevator")
                            each_passenger.change_state(PassengerState.OUT_ELEVATOR_0_AT_TARGET_FLOOR)
                            each_passenger.finished = True

                    case PassengerState.IN_ELEVATOR_2_AT_OTHER_FLOOR:
                        # Not exec in this naive testcase
                        if clientMessage.endswith(f"floor_arrived@{each_passenger.target_floor}#{each_passenger.get_elevator_code()}"):
                            each_passenger.current_floor = each_passenger.target_floor
                            each_passenger.change_state(PassengerState.IN_ELEVATOR_2_AT_TARGET_FLOOR)

                    case PassengerState.IN_ELEVATOR_2_AT_TARGET_FLOOR:
                        if clientMessage == "door_opened#2":
                            logger.info(f"Passenger {each_passenger.name} is leaving the elevator")
                            each_passenger.change_state(PassengerState.OUT_ELEVATOR_0_AT_TARGET_FLOOR)
                            each_passenger.finished = True

                    case PassengerState.OUT_ELEVATOR_0_AT_OTHER_FLOOR:
                        if clientMessage.startswith(each_passenger.matching_signal) and each_passenger.current_floor == each_passenger.start_floor:
                            each_passenger.set_elevator_code(int(clientMessage.split("#")[-1]))

                        if clientMessage == f"door_opened#{each_passenger.get_elevator_code()}":
                            logger.info(f"Passenger {each_passenger.name} is entering elevator {each_passenger.get_elevator_code()}")
                            await asyncio.sleep(1)
                            if each_passenger.get_elevator_code() == 1:
                                each_passenger.change_state(PassengerState.IN_ELEVATOR_1_AT_OTHER_FLOOR)
                            elif each_passenger.get_elevator_code() == 2:
                                each_passenger.change_state(PassengerState.IN_ELEVATOR_2_AT_OTHER_FLOOR)
                            await server.send(bindedClient, f"select_floor@{each_passenger.target_floor}#{each_passenger.get_elevator_code()}")

                    case PassengerState.OUT_ELEVATOR_0_AT_TARGET_FLOOR:
                        if each_passenger.is_finished() and not each_passenger.finished_print:
                            logger.info(f"Passenger {each_passenger.name} has reached the target floor.")
                            each_passenger.finished_print = True
                            count += 1

        if count == len(passengers):
            logger.info("Test passed: All passengers have reached their target floors!")
            await asyncio.sleep(1)
            await server.send(bindedClient, "reset")
            break

        await asyncio.sleep(0.01)


async def main():
    server = Server()
    await server.start()

    try:
        while True:
            addr = await server.get_first_client()
            user_input = await ainput(f"Start testing for {addr}? (y/n)\n")
            if user_input.lower() == "y":
                await testing(server)

    except asyncio.CancelledError:
        logger.info("Program cancelled")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
