import can
import cantools
import logging
import threading
import json
import os
from typing import Dict, List, Optional, Callable, Any, Tuple, Union

# Configure logging with a dedicated logger for this module
logger = logging.getLogger(__name__)

class Model:
    """
    Model component in MVC architecture.
    Handles all data management and CAN bus communication.
    
    Responsibilities:
    - Store and update car parameters (values)
    - Define UI layouts for different events
    - Process CAN messages
    - Notify observers of changes
    
    For data persistence and offline development, the model can:
    - Load/save values from/to disk
    - Operate in a simulated mode without real CAN bus
    """
    def __init__(self, can_bus=None, dbc_path="H19_CAN_dbc.dbc", config_path="config.json"):
        self.can_bus = can_bus
        self.dbc_path = dbc_path
        self.config_path = config_path
        
        # Thread safety for value updates
        self._lock = threading.RLock()
        
        # Default initial values (will be overridden by load_config if available)
        self.values = self._get_default_values()

        # Optional units for display
        self.units = self._get_units()

        # Screens for different events
        self.event_screens = self._get_event_screens()

        # Current event context
        self.current_event = "autocross"

        # Callbacks for when a value changes or an event changes
        self.value_changed_callbacks = []
        self.event_changed_callbacks = []

        # Mapping of message names to ID ranges (for fallback)
        self.message_id = self._get_message_id_map()

        # Load DBC file and attempt to load saved configuration
        self.db = self.load_dbc_file(self.dbc_path)
        self.load_config()
        
        # Register periodic state saving
        self._autosave_timer = None
        self._start_autosave_timer()

    def _get_default_values(self) -> Dict[str, Any]:
        """Return default values for all model parameters"""
        return {
            "AMS": 0,
            "IMD": 0,
            "Watt Hours": 0,
            "ASPU": 0,
            "Aux Voltage": 0,
            "SOC": 0,
            "Air Temp": 0,
            "Lowest Cell": 0,
            "Inverter Temp": 0,
            "Battery Temp": 0,
            "Motor Temp": 0,
            "Max Torque": 0,
            "Speed": 0,
            "Lap Time": 0,
            "Accu Temp": 0,
            "Inverter L Temp": 0,
            "Inverter R Temp": 0,
            "Motor L Temp": 0,
            "Motor R Temp": 0,
            "TC": 5,
            "Traction Control Mode": "Auto",
            "TV": 2,
            "Torque Vectoring Mode": "Medium",
            "DRS": "On"
        }
    
    def _get_units(self) -> Dict[str, str]:
        """Return the units for values that need them"""
        return {
            "Watt Hours": "kWh",
            "Aux Voltage": "V",
            "SOC": "%",
            "Air Temp": "C",
            "Lowest Cell": "V",
            "Inverter L Temp": "C",
            "Inverter R Temp": "C",
            "Accu Temp": "C",
            "Motor L Temp": "C",
            "Motor R Temp": "C",
            "Speed": "km/h",
            "Max Torque": "Nm"
        }
    
    def _get_message_id_map(self) -> Dict[str, List[int]]:
        """Map ECU names to their CAN ID ranges"""
        return {
            "AMS": [0x330, 0x35F],
            "IVTS": [0x360, 0x36F],
            "CCU": [0x370, 0x37F],
            "PDU": [0x380, 0x39F],
            "VCU": [0x3A0, 0x3DF],
            "ASPU": [0x3E0, 0x3FF],
            "ASCU": [0x400, 0x41F],
            "DIU": [0x420, 0x42F],
            "FSG Logger": [0x430, 0x430],
            "DRS": [0x431, 0x43F],
            "DTU": [0x440, 0x44F],
            "SN1": [0x450, 0x48F],
            "SN2": [0x490, 0x4CF],
            "Kistler": [0x4D0, 0x4DF]
        }
    
    def _get_event_screens(self) -> Dict[str, List]:
        """
        Define the screen layouts for all event types.
        This is structured as a nested list/dict that will be processed by the View.
        """
        # The complete event screen configuration is quite long
        # For brevity, I'm showing just the autocross screen setup
        # Other screens would be defined similarly
        return {
            "autocross": [
                [
                    {"id": "DRS",
                    "font_value": ("Segoe UI", 50, "bold"),
                    "font_name": ("Segoe UI", 26),
                    "width": 200,
                    "height": 150},
                ],
                
                [
                    [{"id": "Traction Control Mode",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}],
                    [{"id": "Torque Vectoring Mode",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}],
                    [{"id": "Max Torque",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}]
                ],
                
                [
                    [{"id": "Lowest Cell",
                    "font_value": ("Segoe UI", 42, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady": (20,0)}, 
                    {"id": "Accu Temp",
                    "font_value": ("Segoe UI", 42, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady": (20,0), # For aesthetic lines
                    "value_padx": 37}],
                ],
                
                [
                    [{"id": "Motor L Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)},
                     {"id": "Motor R Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)}],
                    [{"id": "Inverter L Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)},
                     {"id": "Inverter R Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)}]
                ]
            ],
            "endurance": [
                # Row 1 (top-left big panel)
                [
                    {"id": "SOC",
                    "font_value": ("Segoe UI", 56, "bold"),
                    "font_name": ("Segoe UI", 36),
                    "value_pady": (13,0),
                    "width": 400,
                    "height": 150}
                ],
                
                # Row 2 (bottom-left big panel)
                [
                    {"id": "Lowest Cell",
                    "font_value": ("Segoe UI", 46, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady" : (20,0)}
                ],

                # Row 3 (top-right big panel)
                [
                    [
                        {"id": "TC",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)},
                        {"id": "TV",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)},
                        {"id": "Max Torque",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)},],
                    [{"id": "DRS",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)},
                     {"id": "Accu Temp",
                        "font_value": ("Segoe UI", 36, "bold"),
                        "font_name": ("Segoe UI", 12),
                        "colspan": 2}]
                ],

                # Row 4 (bottom-right 2×2 sub-layout)
                [
                    [{"id": "Motor L Temp",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)},
                     {"id": "Motor R Temp",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)}],
                    [{"id": "Inverter L Temp",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)},
                     {"id": "Inverter R Temp",
                        "font_value": ("Segoe UI", 28, "bold"),
                        "font_name": ("Segoe UI", 12)}]
                ]
            ],
            "skidpad": [
                # Layout mimics autocross for now but could be customized
                [
                    {"id": "DRS",
                    "font_value": ("Segoe UI", 50, "bold"),
                    "font_name": ("Segoe UI", 30),
                    "width": 200,
                    "height": 150},
                ],
                
                [
                    [{"id": "Traction Control Mode",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}],
                    [{"id": "Torque Vectoring Mode",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}],
                    [{"id": "Max Torque",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}]
                ],
                
                [
                    [{"id": "Lowest Cell",
                    "font_value": ("Segoe UI", 42, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady": (20,0)},
                    {"id": "Accu Temp",
                    "font_value": ("Segoe UI", 42, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady": (20,0),
                    "value_padx": 37}],
                ],
                
                [
                    [{"id": "Motor L Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)},
                     {"id": "Motor R Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)}],
                    [{"id": "Inverter L Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)},
                     {"id": "Inverter R Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)}]
                ]
            ],
            "acceleration": [
                # Layout mimics autocross for now but could be customized
                [
                    {"id": "DRS",
                    "font_value": ("Segoe UI", 50, "bold"),
                    "font_name": ("Segoe UI", 30),
                    "width": 200,
                    "height": 150},
                ],
                
                [
                    [{"id": "Traction Control Mode",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}],
                    [{"id": "Torque Vectoring Mode",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}],
                    [{"id": "Max Torque",
                    "font_value": ("Segoe UI", 20, "bold"),
                    "font_name": ("Segoe UI", 10)}]
                ],
                
                [
                    [{"id": "Lowest Cell",
                    "font_value": ("Segoe UI", 42, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady": (20,0)},
                    {"id": "Accu Temp",
                    "font_value": ("Segoe UI", 42, "bold"),
                    "font_name": ("Segoe UI", 22),
                    "value_pady": (20,0),
                    "value_padx": 37}],
                ],
                
                [
                     [{"id": "Motor L Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)},
                     {"id": "Motor R Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)}],
                    [{"id": "Inverter L Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)},
                     {"id": "Inverter R Temp",
                        "font_value": ("Segoe UI", 32, "bold"),
                        "font_name": ("Segoe UI", 16),
                        "value_pady": (10,0)}]
                ]
            ],
            "debugging": [
                # Debugging screen with more technical information
                [
                    {"id": "SOC",
                     "font_value": ("Segoe UI", 36, "bold"),
                     "font_name": ("Segoe UI", 18),
                     "value_pady": (10,0)}
                ],
                [
                    {"id": "Lowest Cell",
                     "font_value": ("Segoe UI", 36, "bold"),
                     "font_name": ("Segoe UI", 18),
                     "value_pady": (10,0)}
                ],
                [
                    [{"id": "Motor L Temp",
                      "font_value": ("Segoe UI", 24, "bold"),
                      "font_name": ("Segoe UI", 12)},
                     {"id": "Motor R Temp",
                      "font_value": ("Segoe UI", 24, "bold"),
                      "font_name": ("Segoe UI", 12)}],
                    [{"id": "Inverter L Temp",
                      "font_value": ("Segoe UI", 24, "bold"),
                      "font_name": ("Segoe UI", 12)},
                     {"id": "Inverter R Temp",
                      "font_value": ("Segoe UI", 24, "bold"),
                      "font_name": ("Segoe UI", 12)}]
                ]
            ],
            "TS Off Screen": [
                # Empty screen for when TS is off
                [
                    {"id": "AMS",
                     "font_value": ("Segoe UI", 36, "bold"),
                     "font_name": ("Segoe UI", 18),
                     "value_pady": (10,0)}
                ]
            ]
        }

    def _start_autosave_timer(self, interval_ms: int = 30000):
        """Start a timer to periodically save model state"""
        if hasattr(self, '_autosave_timer') and self._autosave_timer:
            self._autosave_timer.cancel()
            
        def _autosave():
            self.save_config()
            self._autosave_timer = threading.Timer(interval_ms / 1000, _autosave)
            self._autosave_timer.daemon = True
            self._autosave_timer.start()
        
        self._autosave_timer = threading.Timer(interval_ms / 1000, _autosave)
        self._autosave_timer.daemon = True
        self._autosave_timer.start()
        logger.debug("Autosave timer started")

    def load_dbc_file(self, path: str) -> Optional[Any]:
        """
        Load a DBC file using cantools.
        Returns the loaded database or None if there was an error.
        """
        try:
            db = cantools.database.load_file(path)
            logger.info(f"DBC file loaded successfully: {path}")
            return db
        except Exception as e:
            logger.error(f"Error loading DBC file '{path}': {e}")
            return None

    def setup_can_bus(self) -> Optional[can.Bus]:
        """
        Default bus setup (vcan0 in this example).
        Adjust channel / bustype / bitrate as needed for real hardware.
        """
        try:
            c = can.Bus(channel="vcan0", interface="socketcan")
            logger.info("CAN Bus initialized successfully on vcan0.")
            return c
        except OSError as e:
            logger.error(f"Failed to initialize CAN bus: {e}")
            return None

    def bind_value_changed(self, callback: Callable[[str, Any], None]) -> None:
        """
        Register a function to be called whenever a model value is updated.
        """
        self.value_changed_callbacks.append(callback)

    def bind_event_changed(self, callback: Callable[[str], None]) -> None:
        """
        Register a function to be called whenever the current event changes.
        """
        self.event_changed_callbacks.append(callback)

    def update_value(self, key: str, value: Any) -> None:
        """
        Update a single value in self.values and call any bound callbacks.
        Thread-safe.
        """
        with self._lock:
            if key in self.values:
                old_value = self.values[key]
                self.values[key] = value
                
                # Only notify if value actually changed
                if old_value != value:
                    for cb in self.value_changed_callbacks:
                        try:
                            cb(key, value)
                        except Exception as e:
                            logger.error(f"Error in value_changed callback: {e}")

    def change_event(self, event_name: str) -> None:
        """
        Change the 'current_event' context.
        """
        with self._lock:
            if event_name in self.event_screens:
                old_event = self.current_event
                self.current_event = event_name
                
                # Only notify if event actually changed
                if old_event != event_name:
                    for cb in self.event_changed_callbacks:
                        try:
                            cb(event_name)
                        except Exception as e:
                            logger.error(f"Error in event_changed callback: {e}")
            else:
                logger.warning(f"Attempted to change to unknown event: {event_name}")

    def get_values_for_event(self, event_name: str) -> List:
        """
        Return the list of values relevant for the given event (for UI display).
        """
        return self.event_screens.get(event_name, [])

    def get_unit(self, key: str) -> Optional[str]:
        """
        Return the unit string for a given value key, or None if no unit is defined.
        """
        return self.units.get(key, None)

    def get_value(self, key: str) -> Any:
        """
        Return the current stored value for the given key, or None if not found.
        Thread-safe.
        """
        with self._lock:
            return self.values.get(key, None)

    def process_can_message(self, msg: can.Message) -> None:
        """
        Decode a CAN message (if the DBC is loaded) and update model values accordingly.
        This method should be called by the controller/GUI whenever a new CAN frame is received.
        """
        if self.db:
            try:
                decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                for signal_name, value in decoded.items():
                    # Only update if it's a known model field
                    if signal_name in self.values:
                        self.update_value(signal_name, value)
            except Exception as e:
                logger.debug(f"DBC decode failed for ID {hex(msg.arbitration_id)}: {e}")
                # Optionally do fallback to handle unknown IDs
                fallback_key = self.get_value_key_from_msg(msg)
                if fallback_key:
                    # Example fallback: store the first byte
                    self.update_value(fallback_key, msg.data[0])
        else:
            # No DBC loaded, fallback approach
            fallback_key = self.get_value_key_from_msg(msg)
            if fallback_key:
                self.update_value(fallback_key, msg.data[0])

    def get_value_key_from_msg(self, msg: can.Message) -> Optional[str]:
        """
        Helper method to map a message ID to a known key if it falls within
        the defined ranges in self.message_id.
        """
        for key, (low_id, high_id) in self.message_id.items():
            if low_id <= msg.arbitration_id <= high_id:
                return key
        return None

    def send_can_message(self, arbitration_id: int, data: List[int]) -> bool:
        """
        Send a CAN message. Typically called by the controller or GUI.
        Returns True if successful, False otherwise.
        """
        if not self.can_bus:
            logger.error("CAN bus is not initialized. Cannot send message.")
            return False

        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)
        try:
            self.can_bus.send(msg)
            logger.info(f"Message sent on CAN bus: {msg}")
            return True
        except can.CanError as e:
            logger.error(f"CAN send error: {e}")
            return False
    
    def save_config(self) -> bool:
        """
        Save the current model state to a JSON file.
        Returns True if successful, False otherwise.
        """
        try:
            with self._lock:
                config = {
                    'values': self.values,
                    'current_event': self.current_event
                }
                
                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                    
                logger.debug("Configuration saved successfully")
                return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def load_config(self) -> bool:
        """
        Load model state from a JSON file.
        Returns True if successful, False otherwise.
        """
        if not os.path.exists(self.config_path):
            logger.debug(f"Configuration file not found: {self.config_path}")
            return False
            
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                
                with self._lock:
                    # Update values from config, preserving any values not in the config
                    if 'values' in config:
                        for key, value in config['values'].items():
                            if key in self.values:  # Only update existing keys
                                self.values[key] = value
                    
                    # Update current event if valid
                    if 'current_event' in config and config['current_event'] in self.event_screens:
                        self.current_event = config['current_event']
                
                logger.info("Configuration loaded successfully")
                return True
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing configuration file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False
    
    def cleanup(self):
        """
        Clean up resources before application exit.
        This should be called when the application is shutting down.
        """
        # Save current config
        self.save_config()
        
        # Cancel the autosave timer
        if hasattr(self, '_autosave_timer') and self._autosave_timer:
            self._autosave_timer.cancel()
            
        # Close CAN bus if open
        if self.can_bus:
            try:
                self.can_bus.shutdown()
                logger.info("CAN bus shut down cleanly")
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")
    
    # Signal mapping helpers for CAN message processing
    
    def map_cell_voltage(self, global_idx: int, value: float) -> None:
        """
        Process a cell voltage and update the "Lowest Cell" value if needed
        """
        # Store the voltage in a persistent dictionary
        if not hasattr(self, '_cell_voltages'):
            self._cell_voltages = {}
            
        self._cell_voltages[global_idx] = value
        
        # Update the lowest cell voltage value
        if self._cell_voltages:
            lowest = min(self._cell_voltages.values())
            self.update_value("Lowest Cell", lowest)
    
    def map_temp_value(self, global_idx: int, value: float) -> None:
        """
        Process a temperature value and update temperature values as needed
        """
        # Store temperatures in a persistent dictionary
        if not hasattr(self, '_temperatures'):
            self._temperatures = {'accu': [], 'motor': [], 'inverter': []}
            
        # Determine temperature type based on global_idx
        if global_idx < 48:  # Assuming first 48 are accumulator temps
            self._temperatures['accu'].append(value)
            # Update highest accumulator temperature
            if self._temperatures['accu']:
                highest = max(self._temperatures['accu'])
                self.update_value("Accu Temp", highest)
        
        # Other temperature mappings could be added as needed
    
    def create_signal_to_value_mapping(self) -> Dict[str, Tuple[str, Callable]]:
        """
        Create a mapping from CAN signal names to model value keys.
        This is used to automatically map signals from the DBC file to model values.
        
        Returns a dictionary where:
            - Key: Signal name from DBC file
            - Value: Tuple of (model_key, optional_transform_function)
        """
        # Direct mappings (signal name -> model key)
        direct_mappings = {
            "AMS_SOC_percentage": "SOC",
            "VCU_Temperature_motor": "Motor Temp",
            "VCU_Temperatures_inverter_igbt": "Inverter Temp",
            "VCU_nm_max": "Max Torque",
            "ASPU_Abs_Speed_KMH100": ("Speed", lambda x: x / 100),  # Convert to km/h
            "MCU_DRS_position_state": ("DRS", lambda x: "On" if x == 1 else "Off"),
            # Add more mappings as needed
        }
        
        return direct_mappings