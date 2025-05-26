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

    controller = GUIElevatorController(client)
    main_window = MainWindow(controller)
    controller.set_main_window(main_window)
    main_window.show()

    await client.send(f"Client[{identity}] is online")
    logging.info(f"Client[{identity}] is online")

    # Start controller's listening loop
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(controller.input_loop())
            for e in controller.elevators.values():
                tg.create_task(e.door_loop())
                tg.create_task(e.move_loop())
    except asyncio.CancelledError:
        logging.info("Program cancelled")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = QApplication(sys.argv)

    gui.main_window.tm = TranslationManager(app)
    gui.main_window.tm.initialize_translations()

    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    with event_loop:
        event_loop.create_task(main())
        event_loop.run_forever()
