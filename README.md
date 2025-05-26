# Elevator Control System

An advanced elevator control system implemented in Python using PySide6 for the graphical user interface. This system provides realistic elevator simulation with dual elevator management, floor calling, door control, and smooth animations.

## Features

### 🏢 Core Functionality

- **Dual Elevator System**: Control and monitor two independent elevators
- **Smart Dispatching**: Intelligent elevator assignment based on distance and efficiency
- **Floor Calling**: Call elevators from any floor with up/down direction
- **Internal Floor Selection**: Select destination floors from inside elevators
- **Door Control**: Manual door open/close functionality
- **Real-time Status**: Live updates of elevator position, direction, and door state

### 🎨 User Interface

- **Modern GUI**: Beautiful PySide6-based interface with smooth animations
- **Multi-language Support**: English and Chinese language support
- **Visual Feedback**: Real-time elevator visualization with door animations
- **Interactive Panels**: Separate building panel and elevator panels for intuitive control
- **Status Indicators**: Clear display of elevator states and floor information

### 🔧 Advanced Features

- **Asynchronous Architecture**: Non-blocking operations with async/await
- **Event-driven System**: Reactive programming with event bus
- **Animation System**: Smooth elevator movement and door animations
- **ZeroMQ Communication**: Network-based client-server architecture for testing
- **Comprehensive Logging**: Rich logging with colored output
- **State Machine**: Robust elevator state management

## Project Structure

```
Elevator/
├── src/
│   ├── main.py              # Main application entry point
│   ├── controller.py        # Core elevator control logic
│   ├── elevator.py          # Elevator state machine and behavior
│   ├── gui/
│   │   ├── main_window.py   # Main GUI window and panels
│   │   ├── gui_controller.py # GUI-specific controller
│   │   ├── visualizer.py    # Elevator visualization component
│   │   ├── i18n.py          # Internationalization support
│   │   └── translations/    # Language files (EN/CN)
│   └── utils/
│       ├── common.py        # Common types and enums
│       ├── event_bus.py     # Event system implementation
│       └── zmq_async.py     # ZeroMQ async client/server
├── test/
│   └── main.py              # Test server for automated testing
├── docs/
│   └── requirement/         # Project requirements and diagrams
├── pyproject.toml           # Project configuration and dependencies
└── README.md                # This file
```

## Requirements

- Python 3.12 or higher
- uv package manager

## Installation

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd Elevator
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

## Usage

### Run the Main Application

To start the elevator control system with GUI:

```bash
uv run src/main.py
```

To start without GUI (for testing purposes):

```bash
uv run src/main.py --headless
```

This launches the main application with:

- Building panel for calling elevators
- Two elevator panels for floor selection and door control
- Real-time elevator visualization
- Language switching (English/Chinese)

### Run the Test Server

To start the test server for automated testing:

```bash
uv run test/main.py
```

This starts a ZeroMQ server that:

- Simulates passenger requests
- Provides automated test scenarios
- Allows external testing of the elevator system
- Supports multiple concurrent test cases

### Controls

#### Building Panel

- **Up/Down Buttons**: Call elevator to current floor
- **Floor Selection**: Choose which floor to call from
- **Status Display**: See which elevator is dispatched

#### Elevator Panel

- **Floor Buttons**: Select destination floor
- **Door Controls**: Manual open/close door buttons
- **Status Display**: Current floor, direction, and door state
- **Target Floors**: View all selected destination floors

## System Architecture

### Core Components

1. **Controller**: Central control logic for elevator dispatching and coordination
2. **Elevator**: Individual elevator state machines with movement and door control
3. **GUI Controller**: Bridges the core logic with the user interface
4. **Animation Manager**: Handles smooth visual transitions and movements
5. **Event Bus**: Decoupled communication between components

### Key Design Patterns

- **State Machine**: Each elevator maintains its state (moving, stopped, door operations)
- **Observer Pattern**: Event-driven updates between components
- **Command Pattern**: User actions translated to elevator commands
- **MVC Architecture**: Separation of model, view, and controller logic

## Configuration

The system supports various configuration options in `src/controller.py`:

- **Elevator Count**: Number of elevators (default: 2)
- **Floor Travel Duration**: Time to move between floors
- **Door Operation Duration**: Time for door open/close operations
- **Acceleration Settings**: Elevator movement acceleration parameters

## License

This project is part of CS132 coursework at ShanghaiTech University.

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed with `uv sync`
2. **GUI Not Starting**: Check PySide6 installation and Qt dependencies
3. **Animation Issues**: Verify graphics drivers support Qt animations
4. **Network Errors**: Ensure ZeroMQ ports are available for testing

### Performance Tips

- Use the async version for better responsiveness
- Adjust animation durations for system performance
- Monitor memory usage with multiple elevators running
