import asyncio
import sys
from typing import Coroutine

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from . import main_window
from .gui_controller import GUIController
from .i18n import TranslationManager
from .main_window import MainWindow


def setup() -> QEventLoop:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    event_loop = QEventLoop(app)
    return event_loop


def run(coro: Coroutine):
    runner = asyncio.Runner(loop_factory=setup)
    try:
        runner.run(coro)
    except RuntimeError as e:
        # Ignore error that occurs when app is closed
        if "Event loop stopped before Future completed" not in str(e):
            raise e


__all__ = [
    "MainWindow",
    "GUIController",
    "run",
]
