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
    Model component in MVC architecture with dual CAN bus support.
    Handles all data management and CAN bus communication.
    
    Responsibilities:
    - Store and update car parameters (values)
    - Define UI layouts for different events
    - Process CAN messages
    - Notify observers of changes
    - Track DIU heartbeat and system health
    
    Always starts with default values - no persistence between sessions.
    """
    def __init__(self, can_model=None, dbc_path="H20_CAN_dbc.dbc", config_path="config.json"):
        self.can_model = can_model  # Store CANModel instead of single bus
        self.dbc_path = dbc_path
        self.config_path = config_path
        
        # Thread safety for value updates
        self._lock = threading.RLock()
        
        # Always start with default values (never load from config)
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

        # Load DBC file only
        self.db = self.load_dbc_file(self.dbc_path)
        
        # Signal processing storage
        self.cell_voltages = {}  # Dict of cell_index -> voltage
        self.temperatures = {'accu': [], 'motor': [], 'inverter': []}
        self.wheel_speeds = {'fl': 0, 'fr': 0, 'rl': 0, 'rr': 0}
        
        # System health tracking
        self.system_faults = {}
        self.last_heartbeat = {'diu': 0, 'timestamp': 0}
        self.ecu_versions = {}
        
        # Performance tracking
        self.performance_data = {
            'max_speed': 0,
            'max_acceleration': 0,
            'lap_times': [],
            'energy_consumption': 0
        }

    def _get_default_values(self) -> Dict[str, Any]:
        """Return default values for all model parameters"""
        return {
            # Primary display values
            "Speed": "unknown",
            "SOC": "unknown",
            "Motor Temp": "unknown",
            "Inverter L Temp": "unknown",
            "Inverter R Temp": "unknown",
            "Max Torque": "unknown",
            "Max_Torque": "unknown",  # Alternative key
            "Max Power": "unknown",
            "Max_Power": "unknown",    # Alternative key
            "Lap Time": "0",
            "Last Lap Time": "0",
            "TC Mode": "unknown",
            "TC_Mode": "unknown",       # Alternative key
            "TV Mode": "unknown",
            "TV_Mode": "unknown",       # Alternative key
            "DRS": "unknown",
            "R2D": "unknown",
            "Status": "unknown",
            "Accu Temp": "unknown",
            "Battery Temp": "unknown",
            "Lowest Cell": "unknown",
            "Highest Cell": "unknown",
            "Watt Hours": "unknown",
            "Energy Used": "unknown",
            "Throttle": "unknown",
            "Brake": "unknown",
            "Steering": "unknown",
            "Traction Control Mode": "unknown",
            "Torque Vectoring Mode": "unknown",
            "Drivemode": "unknown",
            "Max Torque": "unknown",
            "Warning": "",
            
            # ECU Status
            "AMS_Status": "Unknown",
            "VCU_Status": "Unknown", 
            "PDU_Status": "Unknown",
            "IVTS_Status": "Unknown",
            "CCU_Status": "Unknown",
            "DTU_Status": "Unknown",
            "DRS_Status": "Unknown",
            
            # Heartbeat counters
            "DIU_Heartbeat_Counter": 0,
            "AMS_Heartbeat_Counter": 0,
            "VCU_Heartbeat_Counter": 0,
            
            # Software versions
            "AMS_Version": "0.0.0",
            "VCU_Version": "0.0.0",
            "PDU_Version": "0.0.0",
            "DIU_Version": "1.0.0",
            
            # Additional telemetry
            "Front Left Wheel": "unknown",
            "Front Right Wheel": "unknown",
            "Rear Left Wheel": "unknown",
            "Rear Right Wheel": "unknown",
            "Yaw Rate": "unknown",
            "Lateral G": "unknown",
            "Longitudinal G": "unknown",
            
            # Power metrics
            "DC Voltage": "unknown",
            "DC Current": "unknown",
            "AC Power": "unknown",
            "Regen Power": "unknown",
            
            # Fault indicators
            "IMD Fault": False,
            "AMS Fault": False,
            "BSPD Fault": False,
            "TS Active": False,
            "Precharge": False,
            
            # Cell voltages (will be populated dynamically)
            "Cell Min V": "unknown",
            "Cell Max V": "unknown",
            "Cell Avg V": "unknown",
            
            # Temperatures (will be populated dynamically)
            "Temp Min": "unknown",
            "Temp Max": "unknown",
            "Temp Avg": "unknown",
        }

    def _get_units(self) -> Dict[str, str]:
        """Return units for values that have them"""
        return {
            "Speed": "km/h",
            "SOC": "%",
            "Motor L Temp": "°C",
            "Motor R Temp": "°C",
            "Inverter L Temp": "°C",
            "Inverter R Temp": "°C",
            "Max Torque": "Nm",
            "Max_Torque": "Nm",
            "Max Power": "kW",
            "Max_Power": "kW",
            "Accu Temp": "°C",
            "Battery Temp": "°C",
            "Lowest Cell": "V",
            "Highest Cell": "V",
            "Energy Used": "kWh",
            "Throttle": "%",
            "Brake": "%",
            "Steering": "°",
            "Front Left Wheel": "rpm",
            "Front Right Wheel": "rpm",
            "Rear Left Wheel": "rpm",
            "Rear Right Wheel": "rpm",
            "Yaw Rate": "°/s",
            "Lateral G": "g",
            "Longitudinal G": "g",
            "DC Voltage": "V",
            "DC Current": "A",
            "AC Power": "kW",
            "Regen Power": "kW",
            "Cell Min V": "V",
            "Cell Max V": "V",
            "Cell Avg V": "V",
            "Temp Min": "°C",
            "Temp Max": "°C",
            "Temp Avg": "°C",
            "Lap Time": "s",
        }

    def _get_event_screens(self) -> Dict[str, List[List[Dict[str, Any]]]]:
        """
        Return layout configurations for different event screens.
        Each event has a 2D list representing the grid layout.
        """
        return {
            "autocross": [
                # Row 1
                [
                    {"id": "Speed", "font_value": ("Segoe UI", 52, "bold"), "font_name": ("Segoe UI", 16)},
                    {"id": "Max Torque", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)}
                ],
                # Row 2
                [
                    {"id": "SOC", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)},
                    {"id": "Lap Time", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)}
                ],
                # Row 3
                [
                    {"id": "Motor Temp", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)},
                    {"id": "DRS", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)}
                ]
            ],
            "endurance": [
                # Row 1
                [
                    {"id": "SOC", "font_value": ("Segoe UI", 42, "bold"), "font_name": ("Segoe UI", 16)},
                    {"id": "Motor Temp", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)},
                    {"id": "Inverter L Temp", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)}
                ],
                # Row 2
                [
                    {"id": "Watt Hours", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)},
                    {"id": "Battery Temp", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)},
                    {"id": "Inverter R Temp", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)}
                ],
                # Row 3
                [
                    {"id": "Accu Temp", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)},
                    {"id": "Lowest Cell", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)},
                    {"id": "Lap Time", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)}
                ]
            ],
            "acceleration": [
                # Same as autocross for now
                [
                    {"id": "Speed", "font_value": ("Segoe UI", 52, "bold"), "font_name": ("Segoe UI", 16)},
                    {"id": "Max Torque", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)}
                ],
                [
                    {"id": "SOC", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)},
                    {"id": "Lap Time", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)}
                ],
                [
                    {"id": "Motor Temp", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)},
                    {"id": "DRS", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)}
                ]
            ],
            "skidpad": [
                # Same as autocross for now
                [
                    {"id": "Speed", "font_value": ("Segoe UI", 52, "bold"), "font_name": ("Segoe UI", 16)},
                    {"id": "Max Torque", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)}
                ],
                [
                    {"id": "SOC", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)},
                    {"id": "Lap Time", "font_value": ("Segoe UI", 32, "bold"), "font_name": ("Segoe UI", 14)}
                ],
                [
                    {"id": "Motor Temp", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)},
                    {"id": "DRS", "font_value": ("Segoe UI", 28, "bold"), "font_name": ("Segoe UI", 12)}
                ]
            ]
        }

    def _get_message_id_map(self) -> Dict[str, Tuple[int, int]]:
        """Map message types to ID ranges for quick lookup"""
        return {
            "AMS_Control": (0x240, 0x24F),
            "IVTS_Control": (0x250, 0x25F),
            "CCU_Control": (0x260, 0x26F),
            "PDU_Control": (0x270, 0x27F),
            "VCU_Control": (0x000, 0x28F),
            "ASPU_Control": (0x290, 0x29F),
            "ASCU_Control": (0x2A0, 0x2AF),
            "DIU_Control": (0x2B0, 0x2BF),
            "DRS_Control": (0x2C0, 0x2CF),
            "DTU_Control": (0x2D0, 0x2DF),
            "SEN_Control": (0x2E0, 0x2EF),
            "SWU_Control": (0x2F0, 0x2FF),
            "Kistler_Control": (0x300, 0x30F),
            "AMS_Logging": (0x240, 0x35F),
            "IVTS_Logging": (0x360, 0x36F),
            "CCU_Logging": (0x370, 0x37F),
            "PDU_Logging": (0x380, 0x38F),
            "VCU_Logging": (0x000, 0x3DF),
            "ASPU_Logging": (0x3E0, 0x3FF),
            "ASCU_Logging": (0x400, 0x41F),
            "DIU_Logging": (0x420, 0x42F),
            "FSG_Logger": (0x430, 0x430),
            "DRS_Logging": (0x431, 0x43F),
            "DTU_Logging": (0x440, 0x44F),
            "SEN_Logging": (0x450, 0x48F),
            "Kistler_Logging": (0x4D0, 0x4DF),
        }

    def load_dbc_file(self, file_path: str) -> Optional[cantools.database.can.Database]:
        """Load a DBC file and return the database object"""
        try:
            db = cantools.database.load_file(file_path)
            logger.info(f"DBC file loaded successfully: {file_path}")
            return db
        except Exception as e:
            logger.error(f"Error loading DBC file '{file_path}': {e}")
            return None

    def update_value(self, key: str, value: Any) -> None:
        """
        Update a value in the model and notify observers.
        Thread-safe update with callbacks.
        """
        with self._lock:
            old_value = self.values.get(key)
            if old_value != value:
                self.values[key] = value
                # Notify all registered callbacks
                for callback in self.value_changed_callbacks:
                    try:
                        callback(key, value)
                    except Exception as e:
                        logger.error(f"Error in value changed callback: {e}")

    def get_value(self, key: str) -> Any:
        """Get a value from the model (thread-safe)"""
        with self._lock:
            return self.values.get(key)

    def get_values_for_event(self, event_name: str) -> List[str]:
        """Get list of value IDs displayed for a specific event"""
        layout = self.event_screens.get(event_name, [])
        value_ids = []
        for row in layout:
            for item in row:
                value_ids.append(item["id"])
        return value_ids

    def change_event(self, event_name: str) -> None:
        """Change current event and notify observers"""
        if event_name in self.event_screens:
            self.current_event = event_name
            # Notify all registered callbacks
            for callback in self.event_changed_callbacks:
                try:
                    callback(event_name)
                except Exception as e:
                    logger.error(f"Error in event changed callback: {e}")

    def bind_value_changed(self, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for value changes"""
        self.value_changed_callbacks.append(callback)

    def bind_event_changed(self, callback: Callable[[str], None]) -> None:
        """Register a callback for event changes"""
        self.event_changed_callbacks.append(callback)

    def get_unit(self, key: str) -> str:
        """Get the unit for a value, if it has one"""
        return self.units.get(key, "")

    def process_can_message(self, msg: can.Message) -> None:
        """
        Process incoming CAN message and update values accordingly.
        This is called by the controller when messages are received.
        """
        if not self.db:
            return

        try:
            # Decode the message using the DBC file
            decoded = self.db.decode_message(msg.arbitration_id, msg.data)
            
            # Map signals to model values based on message ID
            message_type = self._get_message_type(msg)
            
            # Process based on message type
            if message_type:
                self._process_decoded_signals(message_type, decoded)
                
        except Exception as e:
            # Debug level for unknown messages (common in CAN networks)
            logger.debug(f"Could not decode message {hex(msg.arbitration_id)}: {e}")

    def _get_message_type(self, msg: can.Message) -> Optional[str]:
        """Determine message type based on ID"""
        for key, (low_id, high_id) in self.message_id.items():
            if low_id <= msg.arbitration_id <= high_id:
                return key
        return None

    def send_can_message(self, arbitration_id: int, data: List[int]) -> bool:
        """
        Send a CAN message using proper bus routing.
        """
        if not self.can_model:
            logger.error("CAN model is not initialized. Cannot send message.")
            return False

        try:
            # Use CANModel's automatic routing
            return self.can_model.send_message_on_correct_bus(arbitration_id, data)
        except Exception as e:
            logger.error(f"CAN send error: {e}")
            return False
    
    # Signal mapping helpers for CAN message processing
    
    def map_cell_voltage(self, global_idx: int, value: float) -> None:
        """
        Process a cell voltage and update the "Lowest Cell" value if needed
        """
        try:
            # Store the voltage in the persistent dictionary
            self.cell_voltages[global_idx] = value
            
            # Update the lowest cell voltage value
            if self.cell_voltages:
                lowest = min(self.cell_voltages.values())
                self.update_value("Lowest Cell", round(lowest, 3))
                
            # Track highest cell voltage for diagnostics
            if self.cell_voltages:
                highest = max(self.cell_voltages.values())
                voltage_spread = highest - lowest
                
                # Alert if voltage spread is too high
                if voltage_spread > 0.1:  # 100mV spread threshold
                    logger.warning(f"High cell voltage spread: {voltage_spread:.3f}V")
                    
        except Exception as e:
            logger.error(f"Error processing cell voltage {global_idx}: {e}")
    
    def map_temp_value(self, global_idx: int, value: float) -> None:
        """
        Process a temperature value and update temperature values as needed
        """
        try:
            # Determine temperature type based on global_idx
            if global_idx < 48:  # Assuming first 48 are accumulator temps
                self.temperatures['accu'].append(value)
                # Keep only recent temperatures (sliding window)
                if len(self.temperatures['accu']) > 10:
                    self.temperatures['accu'].pop(0)
                    
                # Update highest accumulator temperature
                if self.temperatures['accu']:
                    highest = max(self.temperatures['accu'])
                    self.update_value("Accu Temp", highest)
                    
        except Exception as e:
            logger.error(f"Error processing temperature {global_idx}: {e}")

    def _process_decoded_signals(self, message_type: str, decoded: Dict[str, Any]) -> None:
        """
        Process decoded signals based on message type.
        This is where we map CAN signals to model values.
        """
        # Example mappings - extend based on your DBC file
        logger.info("Processing message, type : %s", message_type)

        drivemode_map = {
            0: "autocross",
            1: "acceleration",
            2: "endurance",
            3: "skidpad",
            4: "autonomous",
            5: "emergency"
        }

        signal_mapping = {

            # AMS signals
            "AMS_SOC": "SOC", # adjusted
            "AMS_Pack_Voltage": "DC Voltage",
            "AMS_Pack_Current": "DC Current",
            "AMS_Cell_V_lowest": "Lowest Cell", # adjusted
            "AMS_Cell_V_highest": "Highest Cell", # adjusted
            "AMS_Cell_T_highest": "Highest Cell Temp", # adjusted
            "AMS_TS_On": "TS On", # adjusted
            
            # VCU signals
            "VCU_motor_rotation_speed_l": "Speed", # adjusted
            "VCU_motor_temp_l": "Motor L Temp", # adjusted
            "VCU_motor_temp_r": "Motor R Temp", # adjusted

            "VCU_inverter_temp_igbt_l": "Inverter L Temp", # adjusted
            "VCU_inverter_temp_igbt_r": "Inverter R Temp", # adjusted
            "VCU_Torque_Actual": "Actual Torque", 
            
            "VCU_tc_mode": "Traction Control Mode", # adjusted
            "VCU_tv_mode": "Torque Vectoring Mode", # adjusted
            "VCU_drivemode" : "Drivemode", # adjusted
            "VCU_enabled_torque": "Max Torque", # adjusted
            
            "IVT_Result_Wh": "Wh",
	
            "VCU_in_R2D": "R2D Status", # adjusted
            "VCU_driver_num": "Driver Nr", #adjusted
            	
            "VCU_apps_modified": "apps_modified", # adjusted
            "VCU_brake_pressure_rear": "bp_rear",
            "VCU_brake_pressure_front": "bp_front",

            "VCU_laptime_display": "Laptime", # adjusted
            "Last_Lap_Time": "Last Lap Time", # Internal Value, changed, when VCU_Laptime hits zero

            # PDU signals
            "PDU_Watt_Hours": "Watt Hours",
            
            # SEN signals
            "SEN_SDC_SNS_PDU": "SDC_PDU",
            "SEN_SDC_SNS_VCU": "SDC_VCU",
            "SEN_SDC_SNS_Inertia": "SDC_Inertia",
            "SEN_SDC_SNS_ESB_Front": "SDC_ESB_Front",
            "SEN_SDC_SNS_BSPD": "SDC_BSPD",
            "SEN_SDC_SNS_BOTS": "SDC_BOTS",
            "SEN_SDC_SNS_TS_Interlock": "SDC_TS_Interlock",
            "SEN_SDC_SNS_AMS_IMD": "SDC_AMS_IMD",
            "SEN_SDC_SNS_ESB_Right": "SDC_ESB_Right",
            "SEN_SDC_SNS_HVD_Interlock": "SDC_HVD_Interlock",
            "SEN_SDC_SNS_ESB_Left": "SDC_ESB_Left",
            "SEN_SDC_SNS_TSMS": "SDC_TSMS",

            # SWU signals only map signals relevant for the DIU
            # "SWU_Button_8_Up_DRS": "Up",
            # "SWU_Button_6_9_Down_RadioActive": "Down",
            # "SWU_Button_1_Menu": "Menu",
            # "SWU_Button_2_OK": "Menu ok",
            # "SWU_Button_3_Cooling": "alt",
            # "SWU_Button_4_Overall_Reset": "Reset",
            # "SWU_Button_5_TS_On": "TS On Button",
            # "SWU_Button_6_R2D": "R2D Button",

            # Add more mappings based on your DBC
        }
        
        # Update values based on mapping
        for signal_name, value in decoded.items():
            if signal_name in signal_mapping:
                logger.info(f"Updating value for signal: {signal_name} -> {value}")
                model_key = signal_mapping[signal_name]
                # Handle special cases like drivemode mapping
                if signal_name == "VCU_drivemode":
                    value = drivemode_map.get(value)
                if signal_name == "AMS_Cell_V_lowest":
                    if value < 10: # Soometimes wrong values are sent
                        value = round(value, 2)  # Round to 2 decimal places
                    else:
                        break  # Skip if value is not valid
                if signal_name == "AMS_Cell_T_highest":
                    if value < 1000: # Sometimes wrong values are sent
                        value = round(value, 1)  # Round to 1 decimal place
                    else:
                        break  # Skip if value is not valid
                if signal_name == "IVT_Result_Wh" and abs(value) < 100000:
                        value = value * -1
                        value = round(value / 1000, 2)
                if model_key:  # Only update if we have a mapping
                    self.update_value(model_key, value)

    # Demo mode functionality
    
    def start_demo_mode(self) -> None:
        """Start demo mode with random value updates"""
        try:
            self.demo_thread = threading.Thread(target=self._demo_update_loop, daemon=True)
            self.demo_running = True
            self.demo_thread.start()
            logger.info("Demo mode started")
        except Exception as e:
            logger.error(f"Error starting demo mode: {e}")

    def stop_demo_mode(self) -> None:
        """Stop demo mode"""
        try:
            self.demo_running = False
            if hasattr(self, 'demo_thread'):
                self.demo_thread.join(timeout=1.0)
            logger.info("Demo mode stopped")
        except Exception as e:
            logger.error(f"Error stopping demo mode: {e}")

    def _demo_update_loop(self) -> None:
        """Demo mode update loop"""
        import time
        import math
        import random
        
        counter = 0
        while getattr(self, 'demo_running', False):
            try:
                # Simulate realistic value changes
                counter += 1
                
                # Speed oscillation
                speed = 50 + 30 * math.sin(counter * 0.1)
                self.update_value("Speed", int(speed))
                
                # SOC gradual decrease
                current_soc = self.get_value("SOC") or 100
                new_soc = max(0, current_soc - 0.1)
                self.update_value("SOC", round(new_soc, 1))
                
                # Temperature variations
                base_temp = 40
                motor_temp = base_temp + 10 * math.sin(counter * 0.05) + random.uniform(-2, 2)
                self.update_value("Motor Temp", round(motor_temp, 1))
                
                # Lap time simulation
                if counter % 50 == 0:  # Update every 5 seconds
                    lap_seconds = 60 + random.uniform(-5, 5)
                    lap_time = f"{int(lap_seconds // 60)}:{lap_seconds % 60:05.2f}"
                    self.update_value("Lap Time", lap_time)
                
                # Cell voltage simulation
                base_voltage = 3.7 + (new_soc / 100) * 0.5
                lowest_cell = base_voltage - random.uniform(0, 0.05)
                self.update_value("Lowest Cell", round(lowest_cell, 3))
                
                time.sleep(0.1)  # 10Hz update rate
                
            except Exception as e:
                logger.error(f"Error in demo update loop: {e}")
                break

    def cleanup(self) -> None:
        """Clean up resources"""
        try:
            # Stop demo mode if running
            if hasattr(self, 'demo_running') and self.demo_running:
                self.stop_demo_mode()
                
            logger.info("Model cleanup completed")
        except Exception as e:
            logger.error(f"Error during model cleanup: {e}")
