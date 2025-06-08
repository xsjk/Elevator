import argparse
import asyncio
import inspect
import logging

from . import gui
from .core.controller import Config, Controller
from .core.logger import logger
from .gui import GUIController
from .utils.zmq_async import Client


async def main(controller: Controller):
    async def input_loop():
        async for msg, _ in client.messages():
            controller.handle_message_task(msg)

    async def output_loop():
        async for msg in controller.messages():
            await client.send(msg)

    try:
        async with asyncio.TaskGroup() as tg:
            identity = "Group3"
            client = Client(identity=identity)
            client.start(tg)

            await client.send(f"Client[{identity}] is online")

            await controller.start(tg)

            tg.create_task(input_loop(), name=f"InputLoop {__file__}:{inspect.stack()[0].lineno}")
            tg.create_task(output_loop(), name=f"OutputLoop {__file__}:{inspect.stack()[0].lineno}")

    except asyncio.CancelledError:
        logging.info("Program cancelled")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elevator System")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the logging level")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no GUI)")
    parser.add_argument("--num-elevators", type=int, default=2, help="Number of elevators to simulate")
    parser.add_argument("--floor-travel-duration", type=float, default=3.0, help="Duration for an elevator to travel between floors in seconds")
    parser.add_argument("--door-move-duration", type=float, default=1.0, help="Duration for an elevator door to open/close in seconds")
    parser.add_argument("--door-stay-duration", type=float, default=3.0, help="Duration for an elevator door to stay open in seconds")

    args = parser.parse_args()
    logger.setLevel(getattr(logging, args.log_level.upper()))

    cfg = Config(
        elevator_count=args.num_elevators,
        floor_travel_duration=args.floor_travel_duration,
        door_move_duration=args.door_move_duration,
        door_stay_duration=args.door_stay_duration,
    )

    # Run in headless mode or with GUI
    if args.headless:
        asyncio.run(main(Controller()))
    else:
        gui.run(main(GUIController()))
