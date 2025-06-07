"""
Theme Manager for Elevator Control System
Handles loading and switching between light and dark themes
"""

import logging
from pathlib import Path
from typing import Optional

from qtpy.QtCore import QCoreApplication, QEvent, QObject
from qtpy.QtGui import QPalette
from qtpy.QtWidgets import QApplication

try:
    from qtpy.QtCore import Signal
except ImportError:
    from qtpy.QtCore import pyqtSignal as Signal


class ThemeManager(QObject):
    """Manage app themes and detect system changes"""

    theme_changed = Signal(str)

    def __init__(self, app: Optional[QCoreApplication] = None, default_theme: str = "system"):
        super().__init__()
        self.app = app
        self.styles_dir = Path(__file__).parent / "styles"
        # discover available themes by scanning *_theme.qss
        self.themes = [p.stem.replace("_theme", "") for p in self.styles_dir.glob("*_theme.qss")]
        self.current_theme = default_theme
        self._applied_theme = None
        self._theme_cache: dict[str, str] = {}
        # preload common styles
        common_file = self.styles_dir / "common.qss"
        if common_file.exists():
            self._theme_cache["common"] = common_file.read_text(encoding="utf-8")
        if self.app:
            self.app.installEventFilter(self)
            self._detect_and_set_system_theme()

    @property
    def applied_theme(self) -> str:
        return self._applied_theme or self.get_system_theme()

    @applied_theme.setter
    def applied_theme(self, value: str):
        if value == self._applied_theme:
            return
        self._applied_theme = value
        self.theme_changed.emit(value)

    def _detect_and_set_system_theme(self):
        # apply system theme if following
        if self.current_theme == "system":
            applied = self.get_system_theme()
            self.applied_theme = applied

    def get_system_theme(self) -> str:
        # detect system light/dark mode based on window color luminance
        try:
            app = QApplication.instance()
            if app:
                assert isinstance(app, QApplication)
                palette = app.palette()
                wc = palette.color(QPalette.ColorRole.Window)
                lum = 0.299 * wc.red() + 0.587 * wc.green() + 0.114 * wc.blue()
                return "dark" if lum < 128 else "light"
        except Exception:
            pass
        return "light"

    def eventFilter(self, obj, event):
        # handle system palette change when following
        if event.type() == QEvent.Type.PaletteChange and self.current_theme == "system":
            new_theme = self.get_system_theme()
            self.applied_theme = new_theme

        return super().eventFilter(obj, event)

    def _load_theme_file(self, name: str) -> str:
        if name in self._theme_cache:
            return self._theme_cache[name]
        path = self.styles_dir / f"{name}_theme.qss"
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                self._theme_cache[name] = content
                return content
            except Exception as e:
                logging.error(f"ThemeManager: Error loading {path}: {e}")
        else:
            logging.warning(f"ThemeManager: Theme file {path} not found")
        return ""

    def get_theme_styles(self, theme_name: Optional[str] = None) -> str:
        # combine common and specific styles
        name = theme_name or (self.get_system_theme() if self.current_theme == "system" else self.current_theme)
        return self._load_theme_file("common") + "\n" + self._load_theme_file(name)

    def get_current_theme(self) -> str:
        """Get currently applied theme (resolved)"""
        return self.get_system_theme() if self.current_theme == "system" else self.current_theme

    def set_theme(self, name: str) -> None:
        # update current theme and emit change
        if name == self.current_theme:
            return
        self.current_theme = name
        applied = self.get_system_theme() if name == "system" else name
        self.applied_theme = applied
