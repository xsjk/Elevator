import asyncio
import inspect
import logging
import sys

from . import gui
from .core.controller import Controller
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

            controller.start(tg)

            tg.create_task(input_loop(), name=f"InputLoop {__file__}:{inspect.stack()[0].lineno}")
            tg.create_task(output_loop(), name=f"OutputLoop {__file__}:{inspect.stack()[0].lineno}")

    except asyncio.CancelledError:
        logging.info("Program cancelled")


if __name__ == "__main__":
    if "--headless" in sys.argv:
        asyncio.run(main(Controller()))
    else:
        gui.run(main(GUIController()))
