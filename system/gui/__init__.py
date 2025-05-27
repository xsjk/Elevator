import asyncio
import sys
from typing import Coroutine

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from . import main_window
from .gui_controller import GUIController
from .i18n import TranslationManager
from .main_window import MainWindow


def run(coro: Coroutine):
    app = QApplication(sys.argv)

    main_window.tm = TranslationManager(app)
    main_window.tm.initialize_translations()

    close_event = asyncio.Event()

    app.aboutToQuit.connect(close_event.set)

    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    with event_loop:
        event_loop.create_task(coro)
        event_loop.run_until_complete(close_event.wait())


__all__ = [
    "MainWindow",
    "GUIController",
    "run",
]
