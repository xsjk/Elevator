import asyncio
import logging

from . import run
from .gui_controller import GUIController

logger = logging.getLogger(__name__)


async def main():
    try:
        async with asyncio.TaskGroup() as tg:
            c = GUIController()
            c.start(tg)

            async def listen_msg():
                while True:
                    msg = await c.get_event_message()
                    logger.info(f"Received message: {msg}")

            tg.create_task(listen_msg(), name="ListenMsgLoop")

            # Simulate some elevator operations
            await asyncio.sleep(1)
            await c.handle_message("select_floor@3#1")
            await c.handle_message("select_floor@3#2")

            await asyncio.sleep(5)
            await c.handle_message("call_up@1")

            await asyncio.sleep(1)
            await c.handle_message("select_floor@3#1")
            await c.handle_message("call_up@1")

    except asyncio.CancelledError:
        pass


run(main())
