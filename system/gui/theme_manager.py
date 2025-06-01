"""
Theme Manager for Elevator Control System
Handles loading and switching between light and dark themes
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QEvent
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication


class ThemeManager(QObject):
    """
    Manages application themes and detects system theme changes
    """

    theme_changed = Signal(str)  # Signal emitted when theme changes

    def __init__(self):
        super().__init__()
        # default theme
        self.current_theme = "light"
        self.follow_system = True
        self.styles_dir = Path(__file__).parent / "styles"
        self._theme_cache = {}
        # preload common theme
        common_file = self.styles_dir / "common_theme.qss"
        if common_file.exists():
            with open(common_file, "r", encoding="utf-8") as f:
                self._theme_cache["common"] = f.read()

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
            self._detect_and_set_system_theme()

    def _detect_and_set_system_theme(self):
        """Detect system theme and set accordingly"""
        system_theme = self._get_system_theme()
        if system_theme != self.current_theme:
            self.set_theme(system_theme)

    def _get_system_theme(self) -> str:
        """
        Detect system theme (light/dark)
        Returns 'light' or 'dark'
        """
        try:
            app = QApplication.instance()
            if app and isinstance(app, QApplication):
                palette = app.palette()
                window_color = palette.color(QPalette.ColorRole.Window)

                # Calculate luminance to determine if it's dark theme
                window_luminance = 0.299 * window_color.red() + 0.587 * window_color.green() + 0.114 * window_color.blue()

                return "dark" if window_luminance < 128 else "light"
        except Exception:
            pass

        # Default to light theme if detection fails
        return "light"

    def eventFilter(self, obj, event: QEvent):
        """Handle application palette change events for dynamic theme follow"""
        if event.type() == QEvent.Type.PaletteChange and self.follow_system:
            new_theme = self._get_system_theme()
            if new_theme != self.current_theme:
                self.current_theme = new_theme
                self.theme_changed.emit(new_theme)
        return super().eventFilter(obj, event)

    def _load_theme_file(self, theme_name: str) -> str:
        """Load theme CSS from file"""
        if theme_name in self._theme_cache:
            return self._theme_cache[theme_name]

        theme_file = self.styles_dir / f"{theme_name}_theme.qss"

        try:
            if theme_file.exists():
                with open(theme_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    self._theme_cache[theme_name] = content
                    return content
            else:
                print(f"Warning: Theme file {theme_file} not found")
                return ""
        except Exception as e:
            print(f"Error loading theme file {theme_file}: {e}")
            return ""

    def get_theme_styles(self, theme_name: Optional[str] = None) -> str:
        """Get combined common and specific theme styles"""
        if theme_name is None:
            theme_name = self.current_theme
        # Load shared layout and dimensions
        common_styles = self._load_theme_file("common")
        # Load specific color theme (light or dark)
        specific_styles = self._load_theme_file(theme_name)
        return common_styles + "\n" + specific_styles

    def set_theme(self, theme_name: str):
        """
        Set the application theme

        Args:
            theme_name: Theme name ('light' or 'dark')
        """
        if theme_name not in ["light", "dark"]:
            print(f"Warning: Unknown theme '{theme_name}', defaulting to light")
            theme_name = "light"

        # Store current theme before changing
        old_theme = self.current_theme

        # Only emit signal when theme actually changes
        if theme_name != old_theme:
            self.follow_system = False
            self.current_theme = theme_name
            self.theme_changed.emit(theme_name)

    def toggle_theme(self):
        """Toggle between light and dark themes"""
        new_theme = "dark" if self.current_theme == "light" else "light"
        self.set_theme(new_theme)

    def set_follow_system(self):
        """Enable following system theme dynamically"""
        self.follow_system = True
        system_theme = self._get_system_theme()
        if system_theme != self.current_theme:
            self.current_theme = system_theme
            self.theme_changed.emit(system_theme)

    def get_current_theme(self) -> str:
        """Get the current theme name"""
        return self.current_theme
