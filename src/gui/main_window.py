import logging

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import ElevatorController
from gui.i18n import TranslationManager
from gui.visualizer import ElevatorVisualizer
from utils.common import Direction, DoorState, Floor

tm: TranslationManager | None = None


class MainWindow(QMainWindow):
    """
    Main window of the elevator control system
    Contains building panel, elevator panels and console
    """

    def __init__(self, elevator_controller: ElevatorController):
        super().__init__()
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "Elevator Control System"))
        self.setGeometry(100, 100, 900, 700)

        self.elevator_controller = elevator_controller

        # Create main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Create language selector with dynamically detected languages
        self.language_layout = QHBoxLayout()
        language_label = QLabel("Language/语言:")
        self.language_selector = QComboBox()

        # Add all available languages to the selector
        if tm and tm.available_languages:
            self.language_selector.addItems(tm.available_languages)
            # Set current language
            index = self.language_selector.findText(tm.current_language)
            if index >= 0:
                self.language_selector.setCurrentIndex(index)

        self.language_selector.currentTextChanged.connect(self.change_language)
        self.language_layout.addStretch()
        self.language_layout.addWidget(language_label)
        self.language_layout.addWidget(self.language_selector)
        self.main_layout.addLayout(self.language_layout)

        # Create content layout
        self.content_layout = QHBoxLayout()
        self.main_layout.addLayout(self.content_layout)

        # Create left side building panel
        self.building_panel = BuildingPanel(self.elevator_controller)

        # Create middle elevator panels and visualizer
        self.elevators_widget = QWidget()
        self.elevators_layout = QVBoxLayout(self.elevators_widget)

        # Add visualizer with correct floor order (from bottom to top)
        self.elevator_visualizer = ElevatorVisualizer(floors=[Floor(s) for s in elevator_controller.config.floors])
        self.elevators_layout.addWidget(self.elevator_visualizer)

        # Add elevator control panels
        elevator_panels_widget = QWidget()
        elevator_panels_layout = QHBoxLayout(elevator_panels_widget)
        self.elevator_panels = [ElevatorPanel(i, self.elevator_controller) for i in (1, 2)]
        elevator_panels_layout.addWidget(self.elevator_panels[0])
        elevator_panels_layout.addWidget(self.elevator_panels[1])
        self.elevators_layout.addWidget(elevator_panels_widget)

        # Create console
        self.console_widget = ConsoleWidget(self.elevator_controller)

        # Create splitter
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.top_widget = QWidget()
        self.top_layout = QHBoxLayout(self.top_widget)
        self.top_layout.addWidget(self.building_panel, 1)
        self.top_layout.addWidget(self.elevators_widget, 2)

        self.splitter.addWidget(self.top_widget)
        self.splitter.addWidget(self.console_widget)
        self.splitter.setSizes([500, 200])

        # Add to content layout
        self.content_layout.addWidget(self.splitter)

        # Add reset button
        self.control_layout = QVBoxLayout()
        self.reset_button = QPushButton(QCoreApplication.translate("MainWindow", "Reset Elevator System"))
        self.reset_button.clicked.connect(self.reset_system)
        self.control_layout.addWidget(self.reset_button)
        self.control_layout.addStretch()
        self.content_layout.addLayout(self.control_layout)

        # Register as observer for language changes
        tm.add_observer(self)

    def reset_system(self):
        """Reset the elevator system to its initial state"""
        self.elevator_controller.handle_message_task("reset")

        # TODO: Reset UI state
        # # Reset UI state
        # self.elevator_panels[0].update_elevator_status(1)
        # self.elevator_panels[1].update_elevator_status(2)
        # self.building_panel.reset_buttons()

        # # Reset visualizer
        # self.elevator_visualizer.update_elevator_status(1, Floor("1"))
        # self.elevator_visualizer.update_elevator_status(2, Floor("1"))

    def change_language(self, language):
        logging.debug(f"Changing language to {language}")
        tm.set_language(language)

    def update_language(self):
        logging.debug("Updating MainWindow language")
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "Elevator Control System"))
        self.reset_button.setText(QCoreApplication.translate("MainWindow", "Reset Elevator System"))


class BuildingPanel(QFrame):
    """
    Building panel containing floor buttons
    Shows buttons to call elevators from each floor
    """

    def __init__(self, elevator_controller: ElevatorController):
        super().__init__()
        self.elevator_controller = elevator_controller
        self.setFrameShape(QFrame.Shape.Box)
        self.setMinimumWidth(150)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.title = QLabel(QCoreApplication.translate("BuildingPanel", "Floor Control"))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.title)

        # Floor list, arranged from top to bottom
        self.floors = self.elevator_controller.config.floors[::-1]

        self.floor_widgets = {}
        self.floor_labels = {}

        # Create buttons for each floor
        for floor in self.floors:
            floor_widget = QWidget()
            floor_layout = QHBoxLayout(floor_widget)

            floor_label = QLabel(f"{floor} {QCoreApplication.translate('BuildingPanel', 'Floor')}")
            self.floor_labels[floor] = floor_label
            floor_layout.addWidget(floor_label)

            button_layout = QVBoxLayout()

            # Add up button (except for top floor)
            if floor != self.floors[0]:  # Top floor
                up_button = QPushButton("↑")
                up_button.setFixedSize(40, 40)
                up_button.clicked.connect(lambda checked, f=floor: self.call_elevator_up(f))
                button_layout.addWidget(up_button)
            else:
                # Placeholder
                spacer = QWidget()
                spacer.setFixedSize(40, 40)
                button_layout.addWidget(spacer)

            # Add down button (except for bottom floor)
            if floor != self.floors[-1]:
                down_button = QPushButton("↓")
                down_button.setFixedSize(40, 40)
                down_button.clicked.connect(lambda checked, f=floor: self.call_elevator_down(f))
                button_layout.addWidget(down_button)
            else:
                # Placeholder
                spacer = QWidget()
                spacer.setFixedSize(40, 40)
                button_layout.addWidget(spacer)

            floor_layout.addLayout(button_layout)
            layout.addWidget(floor_widget)
            self.floor_widgets[floor] = floor_widget

        layout.addStretch()

        # Register as observer for language changes
        tm.add_observer(self)

    def call_elevator_up(self, floor):
        """Call elevator to go up from floor"""
        self.elevator_controller.handle_message_task(f"call_up@{floor}")

    def call_elevator_down(self, floor):
        """Call elevator to go down from floor"""
        self.elevator_controller.handle_message_task(f"call_down@{floor}")

    def reset_buttons(self):
        """Reset button states"""
        pass

    def update_language(self):
        """Update UI text when language changes"""
        logging.debug("Updating BuildingPanel language")
        self.title.setText(QCoreApplication.translate("BuildingPanel", "Floor Control"))
        for floor, label in self.floor_labels.items():
            label.setText(f"{floor} {QCoreApplication.translate('BuildingPanel', 'Floor')}")


class ElevatorPanel(QFrame):
    """
    Elevator panel showing elevator status and buttons
    Contains floor selection buttons and door control
    """

    def __init__(self, elevator_id, elevator_controller: ElevatorController):
        super().__init__()
        self.elevator_id = elevator_id
        self.elevator_controller = elevator_controller
        self.setFrameShape(QFrame.Shape.Box)
        self.setMinimumWidth(120)

        layout = QVBoxLayout(self)

        # Elevator title
        self.title = QLabel(f"{QCoreApplication.translate('ElevatorPanel', 'Elevator')} #{elevator_id}")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.title)

        # Elevator status display
        self.status_frame = QFrame()
        self.status_frame.setFrameShape(QFrame.Shape.Panel)
        self.status_frame.setMinimumHeight(60)
        status_layout = QVBoxLayout(self.status_frame)

        self.floor_label = QLabel(f"{QCoreApplication.translate('ElevatorPanel', 'Current Floor:')} 1")
        self.door_label = QLabel(f"{QCoreApplication.translate('ElevatorPanel', 'Door:')} {QCoreApplication.translate('ElevatorPanel', 'Closed')}")
        self.direction_label = QLabel(f"{QCoreApplication.translate('ElevatorPanel', 'Direction:')} {QCoreApplication.translate('ElevatorPanel', 'Idle')}")

        status_layout.addWidget(self.floor_label)
        status_layout.addWidget(self.door_label)
        status_layout.addWidget(self.direction_label)

        layout: QLayout = layout
        layout.addWidget(self.status_frame)

        # Floor buttons
        button_frame = QFrame()
        button_layout = QGridLayout(button_frame)

        self.floor_buttons = {}

        # Button layout as 2x2 grid
        floor_positions = {"3": (0, 0), "2": (0, 1), "1": (1, 0), "-1": (1, 1)}

        for floor, pos in floor_positions.items():
            button = QPushButton(floor)
            button.setFixedSize(50, 50)
            button.clicked.connect(lambda checked, f=floor: self.select_floor(f))
            button_layout.addWidget(button, pos[0], pos[1])
            self.floor_buttons[floor] = button

        layout.addWidget(button_frame)

        # Door control buttons
        door_frame = QWidget()
        door_layout = QHBoxLayout(door_frame)

        self.open_door_button = QPushButton(QCoreApplication.translate("ElevatorPanel", "Open Door"))
        self.open_door_button.clicked.connect(self.open_door)
        door_layout.addWidget(self.open_door_button)

        self.close_door_button = QPushButton(QCoreApplication.translate("ElevatorPanel", "Close Door"))
        self.close_door_button.clicked.connect(self.close_door)
        door_layout.addWidget(self.close_door_button)

        layout.addWidget(door_frame)
        layout.addStretch()

        # Register as observer for language changes
        tm.add_observer(self)

    def select_floor(self, floor):
        """Select a floor inside the elevator"""
        self.elevator_controller.handle_message_task(f"select_floor@{floor}#{self.elevator_id}")

    def open_door(self):
        """Open elevator door"""
        self.elevator_controller.handle_message_task(f"open_door#{self.elevator_id}")

    def close_door(self):
        """Close elevator door"""
        self.elevator_controller.handle_message_task(f"close_door#{self.elevator_id}")

    def update_elevator_status(self, floor: Floor, door_state: DoorState, direction: Direction):
        """Update elevator status display"""
        assert isinstance(floor, Floor)
        assert isinstance(door_state, DoorState)
        assert isinstance(direction, Direction)

        self.floor_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Current Floor:')} {floor}")

        door_text = QCoreApplication.translate("ElevatorPanel", door_state.name.capitalize())
        self.door_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Door:')} {door_text}")

        direction_text = QCoreApplication.translate("ElevatorPanel", direction.name.capitalize())
        self.direction_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Direction:')} {direction_text}")

    def update_language(self):
        """Update UI text when language changes"""
        logging.debug("Updating ElevatorPanel language")
        self.title.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Elevator')} #{self.elevator_id}")
        self.floor_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Current Floor:')} 1")
        self.door_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Door:')} {QCoreApplication.translate('ElevatorPanel', 'Closed')}")
        self.direction_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Direction:')} {QCoreApplication.translate('ElevatorPanel', 'Idle')}")
        self.open_door_button.setText(QCoreApplication.translate("ElevatorPanel", "Open Door"))
        self.close_door_button.setText(QCoreApplication.translate("ElevatorPanel", "Close Door"))


class ConsoleWidget(QFrame):
    """
    Console widget for executing commands and showing output
    Allows direct interaction with the elevator controller
    """

    def __init__(self, elevator_controller):
        super().__init__()
        self.elevator_controller = elevator_controller
        self.setFrameShape(QFrame.Shape.Box)

        layout = QVBoxLayout(self)

        self.title = QLabel(QCoreApplication.translate("ConsoleWidget", "Command Console"))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.title)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        layout.addWidget(self.console_output)

        input_layout = QHBoxLayout()
        self.input_label = QLabel(QCoreApplication.translate("ConsoleWidget", "Command:"))
        self.console_input = QLineEdit()
        self.console_input.setPlaceholderText(QCoreApplication.translate("ConsoleWidget", "Enter command, e.g.: call_up@1, select_floor@2#1..."))
        self.console_input.returnPressed.connect(self.execute_command)

        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.console_input)

        layout.addLayout(input_layout)

        # Register as observer for language changes
        tm.add_observer(self)

    def execute_command(self):
        """Execute a command from the console input"""
        command = self.console_input.text()
        if not command:
            return

        self.console_input.clear()
        self.elevator_controller.handle_message_task(command)
        self.console_output.append(f"> {command}")

    def log_message(self, message):
        """Log a message to the console output"""
        self.console_output.append(message)

    def update_language(self):
        """Update UI text when language changes"""
        logging.debug("Updating ConsoleWidget language")
        self.title.setText(QCoreApplication.translate("ConsoleWidget", "Command Console"))
        self.input_label.setText(QCoreApplication.translate("ConsoleWidget", "Command:"))
        self.console_input.setPlaceholderText(QCoreApplication.translate("ConsoleWidget", "Enter command, e.g.: call_up@1, select_floor@2#1..."))
