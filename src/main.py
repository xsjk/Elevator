import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

import gui.main_window
from gui.gui_controller import GUIController
from gui.i18n import TranslationManager
from gui.main_window import MainWindow
from utils.zmq_async import Client


async def main():
    identity = "Group3"
    client = Client(identity=identity)
    client.start()

    controller = GUIController()
    main_window = MainWindow(controller)
    controller.set_main_window(main_window)
    main_window.show()

    async def input_loop():
        while True:
            message, _ = await client.read()
            await controller.handle_message(message)

    async def output_loop():
        while True:
            msg = await controller.get_event_message()
            print(msg)
            await client.send(msg)

    await client.send(f"Client[{identity}] is online")

    try:
        async with asyncio.TaskGroup() as tg:
            controller.start(tg)
            tg.create_task(input_loop())
            tg.create_task(output_loop())
    except asyncio.CancelledError:
        logging.info("Program cancelled")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    gui.main_window.tm = TranslationManager(app)
    gui.main_window.tm.initialize_translations()

    with QEventLoop(app) as event_loop:
        asyncio.set_event_loop(event_loop)
        event_loop.run_until_complete(main())
