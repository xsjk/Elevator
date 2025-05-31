import asyncio
import sys
from typing import Coroutine

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication
from qasync import QEventLoop

from . import main_window
from .gui_controller import GUIController
from .i18n import TranslationManager
from .main_window import MainWindow


def setup() -> tuple[QEventLoop, QCoreApplication]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    if main_window.tm is None:
        tm = TranslationManager(app)
        tm.initialize_translations()
        main_window.tm = tm

    event_loop = QEventLoop(app)
    return event_loop, app


def run(coro: Coroutine):
    loop, app = setup()
    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)

    with loop:
        loop.create_task(coro, name="MainCoroutine")
        loop.run_until_complete(close_event.wait())


__all__ = [
    "MainWindow",
    "GUIController",
    "run",
]
