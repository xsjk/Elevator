import asyncio
import logging

from . import run
from .gui_controller import GUIController


async def main():
    try:
        async with asyncio.TaskGroup() as tg:
            c = GUIController()
            await c.start(tg)

            async def listen():
                async for msg in c.messages():
                    logging.info(f"Received message: {msg}")

            tg.create_task(listen(), name="ListenMsgLoop")

            # Simulate some elevator operations
            await asyncio.sleep(1)
            c.handle_message_task("select_floor@3#1")
            c.handle_message_task("select_floor@3#2")

            await asyncio.sleep(5)
            c.handle_message_task("call_up@1")
            c.handle_message_task("call_down@1")

    except asyncio.CancelledError:
        pass


run(main())
