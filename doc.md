# DIU Documentation

## Overview

The DIU Display is a Python application that implements a digital dashboard for FS racing. It communicates with the car's systems via CAN bus, displays real-time telemetry data, and allows configuration of various vehicle parameters.

The application follows the Model-View-Controller (MVC) architecture pattern:
- **Model**: Manages data, business logic, and CAN communication
- **View**: Displays the data and handles user interface
- **Controller**: Processes user input and coordinates between Model and View

## System Architecture

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│                 │      │                 │      │                 │
│      Model      │◄────►│    Controller   │◄────►│      View       │
│                 │      │                 │      │                 │
└────────┬────────┘      └─────────────────┘      └─────────────────┘
         │                                                  ▲
         │                                                  │
         │                                                  │
         │                                                  │
         │                                         User Interaction
         ▼
┌─────────────────┐
│                 │
│     CAN Bus     │
│                 │
└─────────────────┘
```

### Key Components

#### 1. Main Module (`main.py`)
Entry point that initializes all components and starts the application.

#### 2. Configuration System (`Config.py`)
Manages application settings with support for multiple profiles.

#### 3. CAN Utilities (`can_utils.py`)
Handles CAN bus communication, message encoding/decoding, and simulation.

#### 4. Model (`Model.py`)
Manages the data and business logic of the application.

#### 5. View (`View.py`)
Implements the graphical user interface using Tkinter.

#### 6. Controller (`Controller.py`)
Handles user input and coordinates model and view updates.

## Installation and Setup

### Prerequisites

- Python 3.8 or higher
- CAN interface hardware (for real hardware deployment)
- Virtual CAN interface (for development without hardware)

### Required Python Packages

- tkinter (GUI library)
- python-can (CAN bus communication)
- cantools (DBC file parsing)
- Pillow (Image handling for logos)

### Basic Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/formula-student-car-display.git
   cd formula-student-car-display
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up virtual CAN for development (Linux only):
   ```
   sudo modprobe vcan
   sudo ip link add dev vcan0 type vcan
   sudo ip link set up vcan0
   ```

4. Run the application:
   ```
   python main.py
   ```

### Command Line Options

The application supports various command line options:

- `--virtual`: Use virtual CAN bus instead of real hardware
- `--demo`: Run in demo mode with simulated values
- `--dbc FILE`: Specify path to DBC file
- `--debug`: Enable debug logging

Example:
```
python main.py --virtual --demo --debug
```

## Module Documentation

### 1. Config Module

The Config module provides a configuration management system for the application.

#### Class: `Config`

Handles loading, saving, and accessing configuration options.

##### Methods:

- `__init__(config_dir="config", profile="default")`: Initialize configuration system
- `get(section, key, default=None)`: Get a configuration value
- `set(section, key, value)`: Set a configuration value
- `load()`: Load configuration from file
- `save()`: Save configuration to file
- `switch_profile(profile_name)`: Switch to a different configuration profile
- `get_available_profiles()`: Get list of available profiles
- `export_config(export_path)`: Export configuration to file
- `import_config(import_path)`: Import configuration from file

##### Example:

```python
from Config import Config

# Initialize configuration with default profile
config = Config()

# Get a configuration value
debug_mode = config.get("app", "debug", False)

# Set a configuration value
config.set("app", "fullscreen", True)

# Save changes
config.save()

# Switch to a different profile
config.switch_profile("race_day")
```

### 2. CAN Utilities Module

The CAN Utilities module provides functionality for working with CAN bus messages.

#### Class: `CANUtils`

Handles CAN bus setup, message sending/receiving, and simulation.

##### Methods:

- `__init__(config=None)`: Initialize CAN utilities
- `setup()`: Set up CAN bus and load DBC file
- `setup_can_bus()`: Set up CAN bus interface
- `load_dbc_file(dbc_path)`: Load DBC file for message decoding
- `start_listener(callback)`: Start CAN message listener
- `stop_listener()`: Stop CAN message listener
- `send_message(arbitration_id, data, is_extended_id=False)`: Send CAN message
- `decode_message(msg)`: Decode CAN message using DBC file
- `encode_message(message_name, data)`: Encode data into CAN message
- `start_simulation(callback, message_rate_hz=10.0)`: Start CAN message simulation
- `stop_simulation()`: Stop CAN message simulation
- `get_message_info(msg_id)`: Get information about a message
- `get_signal_info(msg_id, signal_name)`: Get information about a signal
- `create_signal_map()`: Create mapping of parameter names to signals
- `cleanup()`: Clean up resources

##### Example:

```python
from can_utils import CANUtils

# Initialize CAN utilities
can_utils = CANUtils()

# Set up CAN bus and load DBC file
can_utils.setup()

# Define callback for received messages
def on_message(msg):
    decoded = can_utils.decode_message(msg)
    if decoded:
        print(f"Received message: {decoded}")

# Start listener
can_utils.start_listener(on_message)

# Send a message
can_utils.send_message(0x123, [0x01, 0x02, 0x03, 0x04])

# Clean up when done
can_utils.cleanup()
```

### 3. Model Module

The Model module manages the data and business logic of the application.

#### Class: `Model`

Handles data storage, updates, and CAN message processing.

##### Methods:

- `__init__(can_bus=None, dbc_path="H19_CAN_dbc.dbc", config_path="config.json")`: Initialize model
- `update_value(key, value)`: Update a value in the model
- `change_event(event_name)`: Change the current event context
- `get_values_for_event(event_name)`: Get values for a specific event
- `get_unit(key)`: Get the unit for a value
- `get_value(key)`: Get a value from the model
- `process_can_message(msg)`: Process a CAN message
- `send_can_message(arbitration_id, data)`: Send a CAN message
- `save_config()`: Save model state to file
- `load_config()`: Load model state from file
- `cleanup()`: Clean up resources
- `map_cell_voltage(global_idx, value)`: Process a cell voltage update
- `map_temp_value(global_idx, value)`: Process a temperature update

##### Events and Callbacks:

- `bind_value_changed(callback)`: Register callback for value changes
- `bind_event_changed(callback)`: Register callback for event changes

##### Example:

```python
from Model import Model

# Initialize model
model = Model()

# Update a value
model.update_value("SOC", 80)

# Get a value
soc = model.get_value("SOC")
print(f"Current SOC: {soc}%")

# Change event
model.change_event("endurance")

# Define callback for value changes
def on_value_changed(key, value):
    print(f"Value changed: {key} = {value}")

# Register callback
model.bind_value_changed(on_value_changed)
```

### 4. View Module

The View module implements the graphical user interface using Tkinter.

#### Class: `Display`

Main window of the application.

##### Methods:

- `__init__(model)`: Initialize display with model
- `create_header_frame(parent)`: Create header frame with logo and mode label
- `create_menu_frame(parent, title="Menu")`: Create a menu frame
- `create_main_menu_buttons(parent)`: Create buttons for main menu
- `create_debug_screen(parent)`: Create debugging screen layout
- `create_ecu_screen(parent)`: Create ECU version screen layout
- `show_debug_message(message)`: Show a debug message popup
- `show_menu_screen(menu_frame)`: Show a specific menu screen
- `return_to_event_screen()`: Return to the main event screen
- `create_event_screen(event_name)`: Create the appropriate event screen
- `menu_pop()`: Toggle between main screen and menu
- `handle_value_update(panel_id, value)`: Update a value in the current screen

##### Example:

```python
import tkinter as tk
from Model import Model
from View import Display

# Create root window
root = tk.Tk()

# Initialize model
model = Model()

# Create display
view = Display(model)

# Start main loop
view.mainloop()
```

#### Class: `EventScreen`

Represents a screen for a specific driving event.

##### Methods:

- `__init__(event_name, model, parent, layout)`: Initialize event screen
- `create_panels(layout)`: Create panels based on layout
- `update_value(panel_id, value)`: Update a value in the screen

#### Class: `PanelGroup`

Container for multiple display panels.

##### Methods:

- `__init__(parent, model, items, group_bg)`: Initialize panel group
- `add_item(item)`: Add an item to the group
- `update_panel_value(panel_id, new_value)`: Update a panel value

#### Class: `DisplayPanel`

Panel showing a single value with its name and unit.

##### Methods:

- `__init__(parent, panel_id, name, value, unit, model, ...)`: Initialize display panel
- `update_value(new_value)`: Update the displayed value
- `get_value_color(val)`: Determine color based on value thresholds

### 5. Controller Module

The Controller module handles user input and coordinates model and view updates.

#### Class: `Controller`

Manages interaction between model and view.

##### Methods:

- `__init__(model, view, can_bus=None)`: Initialize controller
- `setup_button_actions()`: Configure button actions
- `setup_can_listener()`: Set up CAN message listener
- `process_can_message(msg)`: Process CAN messages
- `toggle_demo_mode()`: Toggle demo mode
- `update_value(key, value)`: Update a value in the model
- `change_event(event_name)`: Change the current event
- `menu_toggle()`: Toggle menu visibility
- `handle_key_press(event)`: Handle keyboard shortcuts
- `change_max_torque(amount)`: Change maximum torque setting
- `change_max_power(amount)`: Change maximum power setting
- `calibrate_throttle_upper()`: Calibrate upper throttle position
- `calibrate_throttle_lower()`: Calibrate lower throttle position
- `cycle_tc_mode()`: Cycle through traction control modes
- `cycle_tv_mode()`: Cycle through torque vectoring modes

##### Example:

```python
from Model import Model
from View import Display
from Controller import Controller
from can_utils import CANUtils

# Initialize components
can_utils = CANUtils()
can_utils.setup()

model = Model(can_utils.bus)
view = Display(model)
controller = Controller(model, view, can_utils.bus)

# Toggle demo mode
controller.toggle_demo_mode()

# Start main loop
view.mainloop()
```

## Usage Guide

### Basic Usage

1. **Starting the Application**:
   Launch the application using `python main.py`

2. **Viewing Telemetry**:
   The main screen shows current telemetry data for the selected event type.

3. **Navigating Screens**:
   - Press `n` to move to the next event screen
   - Press `p` to move to the previous event screen
   - Press `h` or `Escape` to access the menu

4. **Using the Menu**:
   - Use keyboard or touchscreen to select menu options
   - Access vehicle configuration options
   - View debugging information
   - Check ECU versions

### Advanced Usage

#### Keyboard Shortcuts

| Key       | Function                      |
|-----------|-------------------------------|
| `Space`   | Toggle demo mode              |
| `n`       | Next event screen             |
| `p`       | Previous event screen         |
| `h`/`Esc` | Toggle menu                   |
| `t`       | Cycle traction control mode   |
| `v`       | Cycle torque vectoring mode   |
| `d`       | Toggle DRS state              |
| `q`       | Quit application              |

#### Configuration Files

Configuration files are stored in the `config` directory as JSON files. You can create multiple configuration profiles for different scenarios.

Example configuration file:

```json
{
  "app": {
    "name": "Formula Student Car Display",
    "fullscreen": false,
    "width": 800,
    "height": 480,
    "demo_mode": false
  },
  "can": {
    "interface": "socketcan",
    "channel": "can0",
    "bitrate": 1000000,
    "dbc_file": "H19_CAN_dbc.dbc"
  }
}
```

#### DBC Files

The application uses DBC files to decode CAN messages. Make sure your DBC file includes all the signals you want to display.

Example DBC file excerpt:

```
BO_ 579 AMS_SOC: 8 Vector__XXX
 SG_ AMS_SOC_Wh_since_last_calib : 16|32@1- (1,0) [0|0] "Wh" Vector__XXX
 SG_ AMS_SOC_percentage_from_volt : 8|8@1+ (1,0) [0|0] "%" Vector__XXX
 SG_ AMS_SOC_percentage : 0|8@1+ (1,0) [0|0] "%" Vector__XXX
```

## Troubleshooting

### Common Issues

1. **CAN Bus Connection Errors**:
   - Ensure CAN hardware is properly connected
   - Verify kernel modules are loaded
   - Check if interface is up and running
   - Try using virtual CAN for testing

2. **Missing DBC File**:
   - Ensure the DBC file exists in the specified path
   - Verify the DBC file is properly formatted

3. **GUI Display Issues**:
   - Check if Tkinter is properly installed
   - Verify screen resolution settings
   - Try running in windowed mode instead of fullscreen

### Logging

The application logs information to both the console and a log file. Enable debug logging for more detailed information:

```
python main.py --debug
```

Log files are stored in the application directory as `formula_student_gui.log`.

## Development Guide

### Adding a New Parameter

To add a new parameter to the display:

1. Add the parameter to the `values` dictionary in `Model.py`:
   ```python
   self.values = {
       # Existing parameters...
       "New Parameter": 0,
   }
   ```

2. Add a unit for the parameter if needed:
   ```python
   self.units = {
       # Existing units...
       "New Parameter": "unit",
   }
   ```

3. Add the parameter to the event screen layout in `_get_event_screens()`:
   ```python
   "endurance": [
       # Existing layout...
       [
           {"id": "New Parameter",
            "font_value": ("Segoe UI", 28, "bold"),
            "font_name": ("Segoe UI", 12)},
       ]
   ]
   ```

4. If the parameter comes from CAN, add a mapping in `can_utils.py`:
   ```python
   param_patterns = {
       # Existing patterns...
       'New Parameter': ['new_param', 'param_new'],
   }
   ```

### Adding a New Screen Layout

To add a new screen layout:

1. Add the new event type to the `event_screens` dictionary in `Model.py`:
   ```python
   self.event_screens = {
       # Existing screens...
       "new_event": [
           # Layout definition...
       ]
   }
   ```

2. Implement display logic in `View.py` if needed:
   ```python
   def _build_new_event_layout(self):
       return {
           "left": [
               # Left panel layout...
           ],
           "right": [
               # Right panel layout...
           ]
       }
   ```

### Simulation for Testing

The application includes a simulation mode for testing without real hardware:

```python
# Start simulation
can_utils.start_simulation(controller.process_can_message)

# Or use the built-in demo mode
controller.toggle_demo_mode()
```

## Appendix

### Class Diagram

```
┌────────────┐         ┌────────────┐         ┌────────────┐
│   Config   │         │ CANUtils   │         │   Model    │
├────────────┤         ├────────────┤         ├────────────┤
│ load()     │         │ setup()    │         │ values     │
│ save()     │         │ send_msg() │         │ units      │
│ get()      │         │ decode()   │         │ update()   │
│ set()      │         │ simulate() │         │ get_value()│
└────────────┘         └────────────┘         └────────────┘
      │                      │                       │
      │                      │                       │
      └──────────────┬──────┘                       │
                     │                              │
                     ▼                              ▼
               ┌────────────┐               ┌────────────┐
               │    main    │───────────────▶ Controller │
               └────────────┘               ├────────────┤
                     │                      │ handle_key()│
                     │                      │ process_msg()│
                     ▼                      └────────────┘
               ┌────────────┐                     │
               │   Display  │◄────────────────────┘
               ├────────────┤
               │ EventScreen│
               │ PanelGroup │
               │ DisplayPanel│
               └────────────┘
```

### Dependencies

- **python-can**: CAN bus interface
- **cantools**: DBC file parsing
- **tkinter**: GUI library
- **Pillow**: Image processing

### References

- Python-CAN Documentation: https://python-can.readthedocs.io/
- Cantools Documentation: https://cantools.readthedocs.io/
- Tkinter Documentation: https://docs.python.org/3/library/tkinter.html
- Formula Student Rules: https://www.formulastudent.de/