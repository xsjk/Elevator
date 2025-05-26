import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

import gui.main_window
from gui.gui_controller import GUIElevatorController
from gui.i18n import TranslationManager
from gui.main_window import MainWindow
from utils.zmq_async import Client


async def main():
    identity = "Group3"
    client = Client(identity=identity)
    await client.start()

    controller = GUIElevatorController()
    main_window = MainWindow(controller)
    controller.set_main_window(main_window)
    main_window.show()

    async def input_loop():
        while True:
            message, _ = await client.read()
            await controller.handle_message(message)

    async def output_loop():
        while True:
            msg = await controller.queue.get()
            print(msg)
            await client.send(msg)

    await client.send(f"Client[{identity}] is online")
    try:
        await asyncio.gather(input_loop(), output_loop())
    except asyncio.CancelledError:
        logging.info("Program cancelled")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = QApplication(sys.argv)

    gui.main_window.tm = TranslationManager(app)
    gui.main_window.tm.initialize_translations()

    with QEventLoop(app) as event_loop:
        asyncio.set_event_loop(event_loop)
        event_loop.create_task(main())
        event_loop.run_forever()
