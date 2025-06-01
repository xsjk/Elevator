import logging
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QGroupBox,
)

from ..core.controller import Config, Controller
from ..utils.common import Direction, DoorState, Floor, FloorLike, ElevatorId
from .i18n import TranslationManager
from .visualizer import ElevatorVisualizer
from .theme_manager import ThemeManager

tm: TranslationManager | None = None

# Global theme_manager instance
theme_manager = ThemeManager()


class ElevatorConfigDialog(QDialog):
    """Configuration dialog for elevator system settings"""

    def __init__(self, current_config: Config, parent=None):
        super().__init__(parent)
        self.current_config = current_config
        self.setWindowTitle(QCoreApplication.translate("ConfigDialog", "Elevator System Configuration"))
        self.setModal(True)
        self.setProperty("class", "config-dialog")

        layout = QVBoxLayout(self)
        layout.setSpacing(25)
        layout.setContentsMargins(30, 30, 30, 30)

        # Add enhanced title
        title_label = QLabel("🏢 " + QCoreApplication.translate("ConfigDialog", "Elevator System Configuration"))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setProperty("class", "dialog-title")
        layout.addWidget(title_label)  # Create enhanced grouped form layout
        config_group = QGroupBox("⚙️ " + QCoreApplication.translate("ConfigDialog", "System Settings"))
        config_group.setProperty("class", "config-group")
        group_layout = QVBoxLayout(config_group)
        group_layout.setSpacing(20)

        # Create form layout for configuration options
        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(18)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setHorizontalSpacing(25)

        # Elevator count configuration with enhanced styling
        self.elevator_count_spinbox = QSpinBox()
        self.elevator_count_spinbox.setRange(1, 10)
        self.elevator_count_spinbox.setValue(current_config.elevator_count)
        self.elevator_count_spinbox.setMinimumWidth(120)
        self.elevator_count_label = QLabel("🏗️ " + QCoreApplication.translate("ConfigDialog", "Number of Elevators:"))
        self.elevator_count_label.setProperty("class", "config-label")
        self.form_layout.addRow(self.elevator_count_label, self.elevator_count_spinbox)

        # Floor travel duration with enhanced styling
        self.floor_travel_spinbox = QDoubleSpinBox()
        self.floor_travel_spinbox.setRange(0.1, 10.0)
        self.floor_travel_spinbox.setSingleStep(0.1)
        self.floor_travel_spinbox.setDecimals(1)
        self.floor_travel_spinbox.setValue(current_config.floor_travel_duration)
        self.floor_travel_spinbox.setSuffix(QCoreApplication.translate("ConfigDialog", "s"))
        self.floor_travel_spinbox.setMinimumWidth(120)
        self.floor_travel_label = QLabel("⏱️ " + QCoreApplication.translate("ConfigDialog", "Floor Travel Duration:"))
        self.floor_travel_label.setProperty("class", "config-label")
        self.form_layout.addRow(self.floor_travel_label, self.floor_travel_spinbox)

        # Door operation duration with enhanced styling
        self.door_duration_spinbox = QDoubleSpinBox()
        self.door_duration_spinbox.setRange(0.1, 10.0)
        self.door_duration_spinbox.setSingleStep(0.1)
        self.door_duration_spinbox.setDecimals(1)
        self.door_duration_spinbox.setValue(current_config.door_move_duration)
        self.door_duration_spinbox.setSuffix(QCoreApplication.translate("ConfigDialog", "s"))
        self.door_duration_spinbox.setMinimumWidth(120)
        self.door_duration_label = QLabel("🚪 " + QCoreApplication.translate("ConfigDialog", "Door Operation Duration:"))
        self.door_duration_label.setProperty("class", "config-label")
        self.form_layout.addRow(self.door_duration_label, self.door_duration_spinbox)

        # Door stay duration with enhanced styling
        self.door_stay_spinbox = QDoubleSpinBox()
        self.door_stay_spinbox.setRange(0.1, 20.0)
        self.door_stay_spinbox.setSingleStep(0.1)
        self.door_stay_spinbox.setDecimals(1)
        self.door_stay_spinbox.setValue(current_config.door_stay_duration)
        self.door_stay_spinbox.setSuffix(QCoreApplication.translate("ConfigDialog", "s"))
        self.door_stay_spinbox.setMinimumWidth(120)
        self.door_stay_label = QLabel("⏳ " + QCoreApplication.translate("ConfigDialog", "Door Stay Duration:"))
        self.door_stay_label.setProperty("class", "config-label")
        self.form_layout.addRow(self.door_stay_label, self.door_stay_spinbox)

        group_layout.addLayout(self.form_layout)
        layout.addWidget(config_group)

        # # Add enhanced info label
        # self.info_label = QLabel(QCoreApplication.translate("ConfigDialog", "Note: Changing elevator count requires system restart."))
        # self.info_label.setWordWrap(True)
        # self.info_label.setProperty("class", "info-warning")
        # layout.addWidget(self.info_label)

        # Enhanced button box
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button:
            ok_button.setText(QCoreApplication.translate("ConfigDialog", "Ok"))
        if cancel_button:
            cancel_button.setText(QCoreApplication.translate("ConfigDialog", "Cancel"))

        layout.addWidget(self.button_box)

    def get_config_values(self):
        """Return the configured values"""
        return {
            "elevator_count": self.elevator_count_spinbox.value(),
            "floor_travel_duration": float(self.floor_travel_spinbox.value()),
            "door_move_duration": float(self.door_duration_spinbox.value()),
            "door_stay_duration": float(self.door_stay_spinbox.value()),
        }


class MainWindow(QMainWindow):
    """
    Main window of the elevator control system
    Supports dynamic number of elevators based on controller configuration
    Contains building panel, elevator panels and console
    """

    def __init__(self, elevator_controller: Controller):
        super().__init__()
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "Elevator Control System"))
        self.setGeometry(100, 100, 1200, 800)

        # Apply initial theme
        self.apply_theme()
        theme_manager.theme_changed.connect(self.apply_theme)

        self.elevator_controller = elevator_controller

        # Create main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setSpacing(4)
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        # Create content layout: Building, Visualizer, Sidebar
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(3)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.addLayout(self.content_layout)

        # Building panel
        self.building_panel = BuildingPanel(self.elevator_controller)

        # Elevator visualizer and panels
        self.elevators_widget = QWidget()
        self.elevators_layout = QVBoxLayout(self.elevators_widget)
        self.elevators_layout.setSpacing(8)

        # Add visualizer with correct floor order (from bottom to top) and dynamic elevator count
        self.elevator_visualizer = ElevatorVisualizer(
            floors=[Floor(s) for s in elevator_controller.config.floors],
            elevator_count=elevator_controller.config.elevator_count,
        )
        self.elevators_layout.addWidget(self.elevator_visualizer)
        self.elevator_visualizer.setVisible(True)

        # Add scroll area for elevator panels
        elevator_scroll_area = QScrollArea()
        elevator_scroll_area.setWidgetResizable(True)
        elevator_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        elevator_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        elevator_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        elevator_scroll_area.setProperty("class", "elevator-scroll-area")

        # Set size policy for scroll area to expand vertically but not horizontally
        elevator_scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Create a widget to hold elevator panels
        elevator_panels_widget = QWidget()
        elevator_panels_widget.setProperty("class", "elevator-panels-widget")
        self.elevator_panels_layout = QHBoxLayout(elevator_panels_widget)
        # Allow horizontal layout to determine its own width

        # Set the layout for the scroll area
        elevator_scroll_area.setWidget(elevator_panels_widget)

        # Create elevator panels dynamically based on elevator_count from config
        self.elevator_panels: dict[int, ElevatorPanel] = {}
        for elevator_id in range(1, self.elevator_controller.config.elevator_count + 1):
            panel = ElevatorPanel(elevator_id, self.elevator_controller)
            self.elevator_panels[elevator_id] = panel
            self.elevator_panels_layout.addWidget(panel)

        self.elevators_layout.addWidget(elevator_scroll_area)

        # Sidebar: combine console and controls
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(8)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # Add console
        self.console_widget = ConsoleWidget(self.elevator_controller)
        sidebar_layout.addWidget(self.console_widget, 3)

        # Add control panel
        control_frame = self.create_control_panel()
        sidebar_layout.addWidget(control_frame, 1)

        # Assemble main content
        self.content_layout.addWidget(self.building_panel, 1)
        self.content_layout.addWidget(self.elevators_widget, 3)
        self.content_layout.addWidget(sidebar, 1)

        # Register as observer for language changes
        if tm is not None:
            tm.add_observer(self)

    def create_control_panel(self) -> QFrame:
        """Create the enhanced control panel with modern styling"""
        control_frame = QFrame()
        control_frame.setProperty("class", "control-panel")
        control_layout = QVBoxLayout(control_frame)
        control_layout.setSpacing(2)
        control_layout.setContentsMargins(2, 2, 2, 2)

        # Add a small spacer
        control_layout.addSpacing(10)

        # Panel title
        self.control_title = QLabel("⚙️ " + QCoreApplication.translate("MainWindow", "Control Panel"))
        self.control_title.setProperty("class", "control-title")
        self.control_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.control_title)

        # Reset button with softer style
        self.reset_button = QPushButton("🔄 " + QCoreApplication.translate("MainWindow", "Reset System"))
        self.reset_button.setProperty("class", "system-button")  # Changed from control-button to system-button
        self.reset_button.clicked.connect(lambda: self.elevator_controller.handle_message_task("reset"))
        self.reset_button.setToolTip(QCoreApplication.translate("MainWindow", "Reset all elevators to initial state"))
        control_layout.addWidget(self.reset_button)

        # Configuration button with softer style
        self.config_button = QPushButton("⚙️ " + QCoreApplication.translate("MainWindow", "Configure Elevators"))
        self.config_button.setProperty("class", "system-button")  # Changed from control-button to system-button
        self.config_button.clicked.connect(self.open_elevator_config_dialog)
        self.config_button.setToolTip(QCoreApplication.translate("MainWindow", "Change elevator system settings"))
        control_layout.addWidget(self.config_button)

        # Visualizer toggle checkbox
        self.visualizer_toggle = QCheckBox("📊 " + QCoreApplication.translate("MainWindow", "Show Visualizer"))
        self.visualizer_toggle.setChecked(True)
        self.visualizer_toggle.setProperty("class", "control-checkbox")
        self.visualizer_toggle.stateChanged.connect(self.toggle_visualizer)
        self.visualizer_toggle.setToolTip(QCoreApplication.translate("MainWindow", "Toggle elevator visualizer display"))
        control_layout.addWidget(self.visualizer_toggle)

        # Language selector
        language_layout = QHBoxLayout()
        self.language_label = QLabel("语言：")
        self.language_label.setProperty("class", "control-label")
        self.language_selector = QComboBox()
        if tm and tm.available_languages:
            self.language_selector.addItems(tm.available_languages)
            idx = self.language_selector.findText(tm.current_language)
            if idx >= 0:
                self.language_selector.setCurrentIndex(idx)
        self.language_selector.currentTextChanged.connect(self.change_language)
        self.language_selector.setProperty("class", "control-combobox")
        self.language_selector.setToolTip(QCoreApplication.translate("MainWindow", "Change interface language"))
        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_selector)
        control_layout.addLayout(language_layout)

        # Theme selector
        theme_layout = QHBoxLayout()
        self.theme_label = QLabel("主题：")
        self.theme_label.setProperty("class", "control-label")
        self.theme_selector = QComboBox()
        self.theme_selector.addItems([
            QCoreApplication.translate("MainWindow", "System Default"),
            QCoreApplication.translate("MainWindow", "Light Mode"),
            QCoreApplication.translate("MainWindow", "Dark Mode"),
        ])
        if getattr(theme_manager, "follow_system", True):
            idx0 = 0
        else:
            idx0 = 1 if theme_manager.get_current_theme() == "light" else 2
        self.theme_selector.setCurrentIndex(idx0)
        self.theme_selector.setProperty("class", "control-combobox")
        self.theme_selector.currentIndexChanged.connect(self.change_theme_mode)
        self.theme_selector.setToolTip(QCoreApplication.translate("MainWindow", "Change theme appearance"))
        theme_layout.addWidget(self.theme_label)
        theme_layout.addWidget(self.theme_selector)
        control_layout.addLayout(theme_layout)

        # Add stretch to push everything to the top
        control_layout.addStretch()
        return control_frame

    def toggle_visualizer(self, state):
        """Toggle the visibility of the elevator visualizer"""
        self.elevator_visualizer.setVisible(self.visualizer_toggle.isChecked())

    def reset(self):
        """Reset the elevator system to its initial state"""
        # Reset UI state for all elevators dynamically
        assert len(self.elevator_panels) == self.elevator_controller.config.elevator_count, "Elevator panels count does not match controller config"

        for eid, panel in self.elevator_panels.items():
            panel.reset()
            # Determine initial floor from config, default to "1" if not available
            initial_floor_str = str(self.elevator_controller.config.default_floor)
            initial_floor = Floor(initial_floor_str)
            self.elevator_visualizer.update_elevator_status(eid, initial_floor, False, direction=Direction.IDLE)

        self.building_panel.reset_buttons()

    def set_elevator_count(self, count: int):
        """Set the number of elevators in the gui"""
        elevator_panels_layout = self.elevator_panels_layout
        if count < self.elevator_controller.config.elevator_count:
            # Remove excess panels
            for eid in range(count + 1, self.elevator_controller.config.elevator_count + 1):
                panel = self.elevator_panels.pop(eid)
                elevator_panels_layout.removeWidget(panel)
                panel.deleteLater()
        elif count > self.elevator_controller.config.elevator_count:
            # Add new panels
            for eid in range(self.elevator_controller.config.elevator_count + 1, count + 1):
                panel = ElevatorPanel(eid, self.elevator_controller)
                self.elevator_panels[eid] = panel
                self.elevator_panels_layout.addWidget(panel)

        # Create or remove elevator in visualizer
        self.elevator_visualizer.set_elevator_count(count)

    def change_language(self, language):
        logging.debug(f"Changing language to {language}")
        if tm is not None:
            tm.set_language(language)

    def update_language(self):
        logging.debug("Updating MainWindow language")
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "Elevator Control System"))
        self.reset_button.setText("🔄 " + QCoreApplication.translate("MainWindow", "Reset System"))
        self.config_button.setText("⚙️ " + QCoreApplication.translate("MainWindow", "Configure Elevators"))
        self.visualizer_toggle.setText("📊 " + QCoreApplication.translate("MainWindow", "Show Visualizer"))
        self.control_title.setText("⚙️ " + QCoreApplication.translate("MainWindow", "Control Panel"))
        self.language_label.setText("语言：")
        self.theme_label.setText("主题：")
        self.theme_selector.setItemText(0, QCoreApplication.translate("MainWindow", "System Default"))
        self.theme_selector.setItemText(1, QCoreApplication.translate("MainWindow", "Light Mode"))
        self.theme_selector.setItemText(2, QCoreApplication.translate("MainWindow", "Dark Mode"))

        # Update tooltips
        self.visualizer_toggle.setToolTip(QCoreApplication.translate("MainWindow", "Toggle elevator visualizer display"))
        self.language_selector.setToolTip(QCoreApplication.translate("MainWindow", "Change interface language"))
        self.theme_selector.setToolTip(QCoreApplication.translate("MainWindow", "Change theme appearance"))
        self.reset_button.setToolTip(QCoreApplication.translate("MainWindow", "Reset all elevators to initial state"))
        self.config_button.setToolTip(QCoreApplication.translate("MainWindow", "Change elevator system settings"))

    def open_elevator_config_dialog(self):
        """Open the elevator configuration dialog"""
        dialog = ElevatorConfigDialog(self.elevator_controller.config, self)
        if dialog.exec():
            # Get the new configuration values
            new_config_values = dialog.get_config_values()
            self.elevator_controller.set_config(**new_config_values)
            logging.info("Elevator configuration applied successfully.")
        dialog.deleteLater()

    def apply_theme(self, theme_name=None):
        self.setStyleSheet(theme_manager.get_theme_styles(theme_name))

        if hasattr(self, "theme_selector"):
            if theme_manager.follow_system:
                idx = 0
            else:
                idx = 1 if (theme_name or theme_manager.get_current_theme()) == "light" else 2

            if self.theme_selector.currentIndex() != idx:
                self.theme_selector.blockSignals(True)
                self.theme_selector.setCurrentIndex(idx)
                self.theme_selector.blockSignals(False)

    def change_theme_mode(self, index):
        if index == 0:
            theme_manager.set_follow_system()
        elif index == 1:
            theme_manager.set_theme("light")
        elif index == 2:
            theme_manager.set_theme("dark")


class BuildingPanel(QFrame):
    """Floor control panel containing buttons to call elevators from each floor"""

    def __init__(self, elevator_controller: Controller):
        super().__init__()
        self.elevator_controller = elevator_controller
        self.setMinimumWidth(200)
        self.setProperty("class", "building-panel")

        # Initialize button dictionaries
        self.floor_labels = {}
        self.up_buttons = {}
        self.down_buttons = {}

        # Setup layout
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Add title
        logo_label = QLabel("🏢")
        logo_label.setProperty("class", "logo")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(logo_label)

        self.title = QLabel("🏢 " + QCoreApplication.translate("BuildingPanel", "Floor Control"))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setProperty("class", "building-title")
        layout.addWidget(self.title)

        # Get floor list from config, arranged from top to bottom
        self.floors_config = self.elevator_controller.config.floors[::-1]

        # Create floor buttons
        self._create_floor_buttons(layout)

        layout.addStretch()

        if tm is not None:
            tm.add_observer(self)

    def _create_floor_buttons(self, layout):
        """Create floor buttons"""
        for floor_str in self.floors_config:
            # Create floor container
            floor_widget = QWidget()
            floor_layout = QHBoxLayout(floor_widget)
            floor_layout.setSpacing(15)

            # Create floor label
            label_text = f"🚪 {floor_str} {QCoreApplication.translate('BuildingPanel', 'Floor')}"
            floor_label = QLabel(label_text)
            floor_label.setProperty("class", "building-floor-label")
            self.floor_labels[floor_str] = floor_label
            floor_layout.addWidget(floor_label)

            # Create up/down button layout
            button_layout = QVBoxLayout()
            button_layout.setSpacing(8)

            # Add up button (except for top floor)
            if floor_str != self.floors_config[0]:
                up_button = self._create_direction_button("▲", floor_str, "up", "Call elevator going up")
                up_button.setProperty("class", "building-call-button")
                button_layout.addWidget(up_button)
                self.up_buttons[floor_str] = up_button
            else:
                button_layout.addWidget(self._create_spacer())

            # Add down button (except for bottom floor)
            if floor_str != self.floors_config[-1]:
                down_button = self._create_direction_button("▼", floor_str, "down", "Call elevator going down")
                down_button.setProperty("class", "building-call-button")
                button_layout.addWidget(down_button)
                self.down_buttons[floor_str] = down_button
            else:
                button_layout.addWidget(self._create_spacer())

            floor_layout.addLayout(button_layout)
            layout.addWidget(floor_widget)

    def _create_direction_button(self, text, floor_str, direction, tooltip):
        """Create a direction button"""
        button = QPushButton(text)
        button.setCheckable(True)
        button.setToolTip(QCoreApplication.translate("BuildingPanel", tooltip))
        button.clicked.connect(lambda checked, f=floor_str, d=direction: self.elevator_controller.handle_message_task(f"{'' if checked else 'cancel_'}call_{d}@{f}"))
        return button

    def _create_spacer(self):
        """Create a spacer widget"""
        spacer = QWidget()
        spacer.setFixedSize(50, 50)
        return spacer

    def clear_call_button(self, floor: FloorLike, direction: Direction):
        """Clear call button state for the specified floor and direction"""
        floor = Floor(floor)
        floor_str = str(floor)
        if direction == Direction.UP and floor_str in self.up_buttons:
            self.up_buttons[floor_str].setChecked(False)
        elif direction == Direction.DOWN and floor_str in self.down_buttons:
            self.down_buttons[floor_str].setChecked(False)

    def reset_buttons(self):
        """Reset all button states"""
        for button in self.up_buttons.values():
            button.setChecked(False)
        for button in self.down_buttons.values():
            button.setChecked(False)

    def update_language(self):
        """Update UI text when language changes"""
        self.title.setText(QCoreApplication.translate("BuildingPanel", "Floor Control"))
        for floor, label in self.floor_labels.items():
            label.setText(f"{floor} {QCoreApplication.translate('BuildingPanel', 'Floor')}")

        # Update direction button tooltips
        for floor_str, button in self.up_buttons.items():
            button.setToolTip(QCoreApplication.translate("BuildingPanel", "Call elevator going up"))

        for floor_str, button in self.down_buttons.items():
            button.setToolTip(QCoreApplication.translate("BuildingPanel", "Call elevator going down"))


class ElevatorPanel(QFrame):
    """Elevator panel showing elevator status and providing floor selection buttons"""

    def __init__(self, elevator_id: ElevatorId, elevator_controller: Controller):
        super().__init__()
        self.elevator_id = elevator_id
        self.elevator_controller = elevator_controller
        self.setMinimumWidth(180)
        self.setMaximumWidth(250)
        self.setProperty("class", "elevator-panel")

        # Initialize button dictionary
        self.floor_buttons = {}

        # Create main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Add title
        self.title = QLabel(f"🚁 {QCoreApplication.translate('ElevatorPanel', 'Elevator')} #{elevator_id}")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setProperty("class", "elevator-title")
        layout.addWidget(self.title)

        # Create status display area
        self._create_status_display(layout)

        # Create floor buttons
        self._create_floor_buttons(layout)

        # Create door control buttons
        self._create_door_controls(layout)

        layout.addStretch()

        if tm is not None:
            tm.add_observer(self)

    def _create_status_display(self, layout):
        """Create status display area"""
        self.status_frame = QFrame()
        status_layout = QVBoxLayout(self.status_frame)
        status_layout.setSpacing(2)

        # Create floor label
        self.floor_label = QLabel(f"📍 {QCoreApplication.translate('ElevatorPanel', 'Current Floor')}: 1")
        self.floor_label.setProperty("class", "elevator-status-label")
        status_layout.addWidget(self.floor_label)

        # Create door label
        self.door_label = QLabel(f"🚪 {QCoreApplication.translate('ElevatorPanel', 'Door')}: {QCoreApplication.translate('ElevatorPanel', 'Closed')}")
        self.door_label.setProperty("class", "elevator-status-label")
        status_layout.addWidget(self.door_label)

        # Create direction label
        self.direction_label = QLabel(f"🧭 {QCoreApplication.translate('ElevatorPanel', 'Direction')}: {QCoreApplication.translate('ElevatorPanel', 'Idle')}")
        self.direction_label.setProperty("class", "elevator-status-label")
        status_layout.addWidget(self.direction_label)

        layout.addWidget(self.status_frame)

    def _create_floor_buttons(self, layout):
        """Create floor buttons"""
        button_frame = QFrame()
        button_layout = QGridLayout(button_frame)
        button_layout.setSpacing(4)
        button_layout.setContentsMargins(1, 1, 1, 1)

        floor_positions = {"3": (0, 0), "2": (0, 1), "1": (1, 0), "-1": (1, 1)}

        for floor_str, pos in floor_positions.items():
            button = QPushButton(floor_str)
            button.setProperty("class", "elevator-floor-button")
            button.setCheckable(True)
            button.setToolTip(QCoreApplication.translate("ElevatorPanel", "Select floor") + f" {floor_str}")
            button.clicked.connect(lambda checked, f=floor_str: self.elevator_controller.handle_message_task(f"{'' if checked else 'de'}select_floor@{f}#{self.elevator_id}"))
            button_layout.addWidget(button, pos[0], pos[1])
            self.floor_buttons[floor_str] = button

        button_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(button_frame)

    def _create_door_controls(self, layout):
        """Create door control buttons"""
        door_frame = QWidget()
        door_layout = QHBoxLayout(door_frame)
        door_layout.setSpacing(2)

        # Create open/close door buttons
        self.door_button_info = [
            ("open_door_button", "◀|▶", "open_door", QCoreApplication.translate("ElevatorPanel", "Open elevator doors")),
            ("close_door_button", "▶|◀", "close_door", QCoreApplication.translate("ElevatorPanel", "Close elevator doors")),
        ]

        for attr_name, label, command, tooltip in self.door_button_info:
            button = QPushButton(label)
            button.setProperty("class", "door-control-button")
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _, cmd=command: self.elevator_controller.handle_message_task(f"{cmd}#{self.elevator_id}"))
            door_layout.addWidget(button)
            setattr(self, attr_name, button)

        layout.addWidget(door_frame)

    def update_elevator_status(self, floor: FloorLike | None = None, door_state: DoorState | None = None, direction: Direction | None = None):
        """Update elevator status display"""
        # Initialize stored values if they don't exist
        if not hasattr(self, "_last_floor"):
            self._last_floor = Floor("1")
        if not hasattr(self, "_last_door_state"):
            self._last_door_state = DoorState.CLOSED
        if not hasattr(self, "_last_direction"):
            self._last_direction = Direction.IDLE

        # Use provided args or fall back to previous values
        if floor is not None:
            self._last_floor = Floor(floor)
        if door_state is not None:
            assert isinstance(door_state, DoorState), f"Expected DoorState type, got {type(door_state)}"
            self._last_door_state = door_state
        if direction is not None:
            assert isinstance(direction, Direction), f"Expected Direction type, got {type(direction)}"
            self._last_direction = direction

        # Update floor display
        current_floor_str = str(self._last_floor)
        self.floor_label.setText(f"📍 {QCoreApplication.translate('ElevatorPanel', 'Current Floor')}: {current_floor_str}")

        # Update door status display
        door_text = QCoreApplication.translate("ElevatorPanel", self._last_door_state.name.capitalize())
        self.door_label.setText(f"🚪 {QCoreApplication.translate('ElevatorPanel', 'Door')}: {door_text}")

        # Update direction display
        direction_text = QCoreApplication.translate("ElevatorPanel", self._last_direction.name.capitalize())
        self.direction_label.setText(f"🧭 {QCoreApplication.translate('ElevatorPanel', 'Direction')}: {direction_text}")

    def clear_floor_button(self, floor_str: str):
        """Clear the specified floor button selection state"""
        if floor_str in self.floor_buttons:
            self.floor_buttons[floor_str].setChecked(False)

    def _reset_internal_buttons(self):
        """Reset all internal button states"""
        for button in self.floor_buttons.values():
            button.setChecked(False)

    def reset(self):
        """Reset the elevator panel to its initial state"""
        self._reset_internal_buttons()
        self.update_elevator_status(Floor("1"), DoorState.CLOSED, Direction.IDLE)

    def update_language(self):
        """Update UI text when language changes"""
        self.title.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Elevator')} #{self.elevator_id}")
        self.update_elevator_status()

        # Update floor button tooltips
        for floor_str, button in self.floor_buttons.items():
            button.setToolTip(QCoreApplication.translate("ElevatorPanel", "Select floor") + f" {floor_str}")

        # Update door control button tooltips
        if hasattr(self, "door_button_info"):
            for attr_name, _, _, tooltip_template in self.door_button_info:
                if hasattr(self, attr_name):
                    button = getattr(self, attr_name)
                    if attr_name == "open_door_button":
                        button.setToolTip(QCoreApplication.translate("ElevatorPanel", "Open elevator doors"))
                    elif attr_name == "close_door_button":
                        button.setToolTip(QCoreApplication.translate("ElevatorPanel", "Close elevator doors"))


class ConsoleWidget(QFrame):
    """
    Console widget for executing commands and showing output
    Allows direct interaction with the elevator controller
    """

    def __init__(self, elevator_controller):
        super().__init__()
        self.elevator_controller = elevator_controller
        self.setProperty("class", "console-widget")

        self.color_scheme = {
            "light": {
                "header": "#1a56db",
                "system_msg": "#4a5568",
                "command": "#047857",
                "timestamp": "#6b7280",
                "message": "#111827",
            },
            "dark": {
                "header": "#58a6ff",
                "system_msg": "#7c3aed",
                "command": "#00ff41",
                "timestamp": "#6b7280",
                "message": "#f3f4f6",
            },
        }

        self.current_colors = self.get_theme_colors()

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Enhanced console title with hacker aesthetic
        self.title = QLabel("💻 " + QCoreApplication.translate("ConsoleWidget", "Command Console"))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setProperty("class", "console-title")
        layout.addWidget(self.title)

        # Enhanced console output with modern terminal styling
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setProperty("class", "console-output")

        self.refresh_welcome_message()

        layout.addWidget(self.console_output)

        # Enhanced input layout with modern styling
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self.input_label = QLabel("➜ " + QCoreApplication.translate("ConsoleWidget", "Command:"))
        self.input_label.setProperty("class", "console-input-label")

        self.console_input = QLineEdit()
        self.console_input.setProperty("class", "console-input")
        self.console_input.setPlaceholderText(QCoreApplication.translate("ConsoleWidget", "Enter command, e.g.: call_up@1, select_floor@2#1..."))
        self.console_input.returnPressed.connect(self.execute_command)
        self.console_input.setToolTip(QCoreApplication.translate("ConsoleWidget", "Type command and press Enter to execute"))

        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.console_input)
        layout.addLayout(input_layout)

        if tm is not None:
            tm.add_observer(self)

        theme_manager.theme_changed.connect(self.update_theme_colors)

    def get_theme_colors(self):
        theme = theme_manager.get_current_theme()
        return self.color_scheme["dark" if theme == "dark" else "light"]

    def refresh_welcome_message(self):
        self.console_output.clear()
        header_color = self.current_colors["header"]
        system_msg_color = self.current_colors["system_msg"]

        self.console_output.append(f"<span style='color: {header_color}; font-weight: bold;'>╔══════════════════╗</span>")
        self.console_output.append(f"<span style='color: {header_color}; font-weight: bold;'>║-ELEVATOR-CONTROL-║</span>")
        self.console_output.append(f"<span style='color: {header_color}; font-weight: bold;'>╚══════════════════╝</span>")
        self.console_output.append(f"<span style='color: {system_msg_color};'>" + QCoreApplication.translate("ConsoleWidget", "System initialized. Ready for commands...") + "</span>")

    def update_theme_colors(self, theme_name=None):
        self.current_colors = self.get_theme_colors()
        self.refresh_welcome_message()

    def execute_command(self):
        """Execute a command from the console input with enhanced styling"""
        command = self.console_input.text()
        if not command:
            return

        self.console_input.clear()
        self.elevator_controller.handle_message_task(command)

    def log_message(self, message: str):
        """Log a message to the console output with enhanced styling"""
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        timestamp_color = self.current_colors["timestamp"]
        message_color = self.current_colors["message"]

        self.console_output.append(f"<span style='color: {timestamp_color};'>[{timestamp}]</span> " + f"<span style='color: {message_color};'>{message}</span>")

    def update_language(self):
        """Update UI text when language changes"""
        logging.debug("Updating ConsoleWidget language")
        self.title.setText(QCoreApplication.translate("ConsoleWidget", "Command Console"))
        self.input_label.setText("➜ " + QCoreApplication.translate("ConsoleWidget", "Command:"))
        self.console_input.setPlaceholderText(QCoreApplication.translate("ConsoleWidget", "Enter command, e.g.: call_up@1, select_floor@2#1..."))
        self.console_input.setToolTip(QCoreApplication.translate("ConsoleWidget", "Type command and press Enter to execute"))

        self.refresh_welcome_message()
