import logging

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from controller import Controller
from gui.i18n import TranslationManager
from gui.visualizer import ElevatorVisualizer
from utils.common import Direction, DoorState, Floor

tm: TranslationManager | None = None


class MainWindow(QMainWindow):
    """
    Main window of the elevator control system
    Contains building panel, elevator panels and console
    """

    def __init__(self, elevator_controller: Controller):
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
        else:
            logging.warning("TranslationManager is not initialized or no available languages found.")

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

        # Add visualizer toggle checkbox
        self.visualizer_toggle = QCheckBox(QCoreApplication.translate("MainWindow", "Show Visualizer"))
        self.visualizer_toggle.setChecked(True)  # Default to checked
        self.visualizer_toggle.stateChanged.connect(self.toggle_visualizer)
        self.language_layout.addWidget(self.visualizer_toggle)

        # Add visualizer with correct floor order (from bottom to top)
        self.elevator_visualizer = ElevatorVisualizer(floors=[Floor(s) for s in elevator_controller.config.floors])
        self.elevators_layout.addWidget(self.elevator_visualizer)
        self.elevator_visualizer.setVisible(True)  # Initially visible if toggle is checked

        # Add elevator control panels
        elevator_panels_widget = QWidget()
        elevator_panels_layout = QHBoxLayout(elevator_panels_widget)
        self.elevator_panels = {i: ElevatorPanel(i, self.elevator_controller) for i in (1, 2)}
        elevator_panels_layout.addWidget(self.elevator_panels[1])
        elevator_panels_layout.addWidget(self.elevator_panels[2])
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
        self.reset_button.clicked.connect(self.elevator_controller.reset)
        self.control_layout.addWidget(self.reset_button)
        self.control_layout.addStretch()
        self.content_layout.addLayout(self.control_layout)

        # Register as observer for language changes
        if tm is not None:
            tm.add_observer(self)

    def toggle_visualizer(self, state):
        """Toggle the visibility of the elevator visualizer"""
        self.elevator_visualizer.setVisible(self.visualizer_toggle.isChecked())

    def reset(self):
        """Reset the elevator system to its initial state"""
        # Reset UI state
        for eid, panel in self.elevator_panels.items():
            panel.reset_internal_buttons()
            # Determine initial floor from config, default to "1" if not available
            initial_floor_str = str(self.elevator_controller.config.default_floor)
            initial_floor = Floor(initial_floor_str)  # Convert to Floor enum object
            panel.update_elevator_status(initial_floor, DoorState.CLOSED, Direction.IDLE)
            self.elevator_visualizer.update_elevator_status(eid, initial_floor, False, direction=Direction.IDLE)

        self.building_panel.reset_buttons()

        # Reset visualizer (if needed, or handled by controller events)

    def change_language(self, language):
        logging.debug(f"Changing language to {language}")
        if tm is not None:
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

    def __init__(self, elevator_controller: Controller):
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

        # Floor list (strings) from config, arranged from top to bottom
        self.floors_config = self.elevator_controller.config.floors[::-1]

        self.floor_widgets = {}
        self.floor_labels = {}
        self.up_buttons = {}  # Store up call buttons, keyed by floor string
        self.down_buttons = {}  # Store down call buttons, keyed by floor string

        # Create buttons for each floor
        for floor_str in self.floors_config:  # Iterate over floor strings from config
            floor_widget = QWidget()
            floor_layout = QHBoxLayout(floor_widget)

            # Use simple string formatting for QLabel to avoid f-string complexity with translate
            label_text = f"{floor_str} {QCoreApplication.translate('BuildingPanel', 'Floor')}"
            floor_label = QLabel(label_text)
            self.floor_labels[floor_str] = floor_label
            floor_layout.addWidget(floor_label)

            button_layout = QVBoxLayout()

            # Add up button (except for top floor)
            if floor_str != self.floors_config[0]:  # Top floor
                up_button = QPushButton("↑")
                up_button.setFixedSize(40, 40)
                up_button.setCheckable(True)  # Make button checkable
                up_button.clicked.connect(lambda checked, f_str=floor_str: self.call_elevator_up(f_str))
                button_layout.addWidget(up_button)
                self.up_buttons[floor_str] = up_button
            else:  # Placeholder for top floor (no up button)
                spacer = QWidget()
                spacer.setFixedSize(40, 40)
                button_layout.addWidget(spacer)

            # Add down button (except for bottom floor)
            if floor_str != self.floors_config[-1]:  # Bottom floor
                down_button = QPushButton("↓")
                down_button.setFixedSize(40, 40)
                down_button.setCheckable(True)  # Make button checkable
                down_button.clicked.connect(lambda checked, f_str=floor_str: self.call_elevator_down(f_str))
                button_layout.addWidget(down_button)
                self.down_buttons[floor_str] = down_button
            else:  # Placeholder for bottom floor (no down button)
                spacer = QWidget()
                spacer.setFixedSize(40, 40)
                button_layout.addWidget(spacer)

            floor_layout.addLayout(button_layout)
            layout.addWidget(floor_widget)
            self.floor_widgets[floor_str] = floor_widget

        layout.addStretch()

        if tm is not None:
            tm.add_observer(self)

    def call_elevator_up(self, floor_str: str):
        # Call elevator to go up from floor_str (string)
        self.elevator_controller.handle_message_task(f"call_up@{floor_str}")
        if floor_str in self.up_buttons:
            self.up_buttons[floor_str].setChecked(True)  # Keep button pressed

    def call_elevator_down(self, floor_str: str):
        # Call elevator to go down from floor_str (string)
        self.elevator_controller.handle_message_task(f"call_down@{floor_str}")
        if floor_str in self.down_buttons:
            self.down_buttons[floor_str].setChecked(True)  # Keep button pressed

    def clear_call_button(self, floor: Floor, direction: Direction):
        # Clear a specific call button when the request is serviced
        # floor: Floor enum object
        # direction: Direction enum object
        floor_str = str(floor)  # Convert Floor enum to string for key lookup
        if direction == Direction.UP and floor_str in self.up_buttons:
            self.up_buttons[floor_str].setChecked(False)
        elif direction == Direction.DOWN and floor_str in self.down_buttons:
            self.down_buttons[floor_str].setChecked(False)

    def reset_buttons(self):
        # Reset all call button states
        for button in self.up_buttons.values():
            button.setChecked(False)
        for button in self.down_buttons.values():
            button.setChecked(False)

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

    def __init__(self, elevator_id, elevator_controller: Controller):
        super().__init__()
        self.elevator_id = elevator_id
        self.elevator_controller = elevator_controller
        self.setFrameShape(QFrame.Shape.Box)
        self.setMinimumWidth(120)

        layout = QVBoxLayout(self)

        self.title = QLabel(f"{QCoreApplication.translate('ElevatorPanel', 'Elevator')} #{elevator_id}")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.title)

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
        layout.addWidget(self.status_frame)

        button_frame = QFrame()
        button_layout = QGridLayout(button_frame)

        self.floor_buttons: dict[str, QPushButton] = {}

        # Ensure floor_positions keys are strings
        floor_positions = {"3": (0, 0), "2": (0, 1), "1": (1, 0), "-1": (1, 1)}

        for floor_str, pos in floor_positions.items():
            button = QPushButton(floor_str)
            button.setFixedSize(50, 50)
            button.setCheckable(True)
            button.clicked.connect(lambda checked, f_str=floor_str: self.select_floor(f_str))
            button_layout.addWidget(button, pos[0], pos[1])
            self.floor_buttons[floor_str] = button
        layout.addWidget(button_frame)

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

        if tm is not None:
            tm.add_observer(self)

    def select_floor(self, floor_str: str):
        # floor_str is the string representation of the floor
        self.elevator_controller.handle_message_task(f"select_floor@{floor_str}#{self.elevator_id}")
        self.floor_buttons[floor_str].setChecked(True)

    def open_door(self):
        """Open elevator door"""
        self.elevator_controller.handle_message_task(f"open_door#{self.elevator_id}")

    def close_door(self):
        """Close elevator door"""
        self.elevator_controller.handle_message_task(f"close_door#{self.elevator_id}")

    def update_elevator_status(self, floor: Floor, door_state: DoorState, direction: Direction):
        assert isinstance(floor, Floor), f"Expected Floor type, got {type(floor)}"
        assert isinstance(door_state, DoorState), f"Expected DoorState type, got {type(door_state)}"
        assert isinstance(direction, Direction), f"Expected Direction type, got {type(direction)}"

        current_floor_str = str(floor)
        self.floor_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Current Floor:')} {current_floor_str}")

        door_text_key = door_state.name.capitalize()
        door_text = QCoreApplication.translate("ElevatorPanel", door_text_key)
        self.door_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Door:')} {door_text}")

        direction_text_key = direction.name.capitalize()
        direction_text = QCoreApplication.translate("ElevatorPanel", direction_text_key)
        self.direction_label.setText(f"{QCoreApplication.translate('ElevatorPanel', 'Direction:')} {direction_text}")

    def clear_floor_button(self, floor_str: str):
        self.floor_buttons[floor_str].setChecked(False)

    def reset_internal_buttons(self):
        for floor_str in self.floor_buttons:
            self.floor_buttons[floor_str].setChecked(False)

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

        if tm is not None:  # Check if tm is initialized
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
