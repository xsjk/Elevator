# Elevator System Requirement

## Diagrams

### Use Case Diagram

<img src="../out/usecase.svg" alt="Use Case Diagram" style="zoom: 67%;" />

### Class Diagram

<img src="../out/class.svg" alt="Class Diagram" style="zoom:67%;" />

### Sequence Diagram

<img src="../out/sequence.svg" alt="Sequence Diagram" style="zoom:67%;" />

## Requirements

- R1: UI

    - R1.1: Floor Panel

        - R1.1.1: A user should know the current floor and moving direction of each of the two elevators at any time

        - R1.1.2: A user should be able to request for an elevator to go up/down by pressing the button on each of the three floor panel

        - R1.1.3: A user should know which elevator is being dispatched him/her

    - R1.2: Elevator Panel

        - R1.2.1: A user should be able to know which floor he/she is currently on and the moving direction of the elevator at any time

        - R1.2.2: A user should be able to see all the target floors of the elevator at any time

        - R1.2.1: A user should be able to select a floor by pressing the button on the elevator panel

        - R1.2.2: A user should be able to open/close the door by pressing the button on the elevator panel

- R2: Control

    - R2.1: Elevator

        - R2.1.1: The elevator should be able to move up/down as requested by the user

        - R2.1.2: The elevator should be able to open/close the door as requested by the user when the elevator is at a floor

    - R2.2: System

        - R2.2.1: The system should be able to dispatch the elevator to the floor where the user is waiting

        - R2.2.2: The system should be able to dispatch the elevator to the floor where the user is going

        - R2.2.3: The system should be able to handle multiple requests from different users at the same time

    - R2.3: Panel

        - R2.3.1: Invalid button presses should take no effect