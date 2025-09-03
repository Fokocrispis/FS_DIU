import sys
import can
import cantools
import logging
import tkinter as tk
from tkinter import ttk
import time
import threading
from queue import Queue
import random
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_dbc_file(file_path):
    """
    Load a DBC file using cantools.
    Returns the loaded database or None if there was an error.
    """
    try:
        db = cantools.database.load_file(file_path)
        logger.info(f"DBC file loaded successfully: {file_path}")
        return db
    except Exception as e:
        logger.error(f"Error loading DBC file '{file_path}': {e}")
        return None

def decode_message(db, message):
    """
    Decode a CAN message using the provided DBC database.
    Returns a dictionary of signal_name -> value, or None on error.
    """
    try:
        decoded = db.decode_message(message.arbitration_id, message.data)
        return decoded
    except Exception as e:
        logger.debug(f"Error decoding message {hex(message.arbitration_id)}: {e}")
        return None

class CANModel:
    """
    Core CAN functionality with dual bus support (Control and Logging).
    Handles sending messages on the appropriate bus based on message ID.
    """
    def __init__(self, arbitration_id=0xC0FFEE, data=None, is_extended_id=True, 
                 dbc_path="H20_CAN_dbc.dbc", 
                 control_channel="can0", logging_channel="can1"):
        self.arbitration_id = arbitration_id
        self.data = data if data else [0x00] * 8
        self.is_extended_id = is_extended_id
        self.dbc_path = dbc_path
        self.control_channel = control_channel
        self.logging_channel = logging_channel

        # Load the DBC file
        self.db = load_dbc_file(dbc_path)

        # Initialize both CAN buses
        self.control_bus, self.logging_bus = self.setup_dual_can_buses()

    def setup_dual_can_buses(self):
        """
        Setup both control and logging CAN buses with fallback to virtual buses.
        Returns tuple of (control_bus, logging_bus).
        """
        control_bus = None
        logging_bus = None
        
        # Try to setup control bus
        try:
            control_bus = can.Bus(channel=self.control_channel, bustype="socketcan", bitrate=1000000)
            logger.info(f"Control CAN bus initialized on {self.control_channel}")
        except Exception as e:
            logger.warning(f"Failed to initialize control bus on {self.control_channel}: {e}")
            
        # Try to setup logging bus
        try:
            logging_bus = can.Bus(channel=self.logging_channel, bustype="socketcan", bitrate=1000000)
            logger.info(f"Logging CAN bus initialized on {self.logging_channel}")
        except Exception as e:
            logger.warning(f"Failed to initialize logging bus on {self.logging_channel}: {e}")
            
        # Fallback to virtual buses if real ones fail
        if not control_bus:
            try:
                control_bus = can.Bus(channel="vcan0", bustype="socketcan")
                logger.info("Control bus using vcan0 (virtual)")
            except Exception as e:
                logger.error(f"Failed to initialize virtual control bus: {e}")
                
        if not logging_bus:
            try:
                logging_bus = can.Bus(channel="vcan1", bustype="socketcan") 
                logger.info("Logging bus using vcan1 (virtual)")
            except Exception as e:
                logger.error(f"Failed to initialize virtual logging bus: {e}")
                
        return control_bus, logging_bus

    def determine_message_bus(self, msg_id):
        """
        Determine which bus a message should be sent on based on H20 CAN ID specification.
        """
        if 0x240 <= msg_id <= 0x32F:
            return "control"
        elif 0x330 <= msg_id <= 0x4FF:
            return "logging" 
        elif msg_id in [0x516, 0x022, 0x023, 0x025]:  # Special control bus messages
            return "control"
        elif msg_id in range(0x518, 0x521):  # Software versions on logging
            return "logging"
        elif 0x420 <= msg_id <= 0x42F:  # DIU range on control
            return "control"
        else:
            return "unknown"

    def send_message_on_correct_bus(self, msg_id, data):
        """
        Send message on the appropriate bus based on message ID.
        """
        bus_type = self.determine_message_bus(msg_id)
        
        if bus_type == "control" and self.control_bus:
            return self._send_on_bus(self.control_bus, msg_id, data, "control")
        elif bus_type == "logging" and self.logging_bus:
            return self._send_on_bus(self.logging_bus, msg_id, data, "logging")
        else:
            logger.warning(f"Cannot send message 0x{msg_id:03X} - bus not available or unknown")
            return False

    def _send_on_bus(self, bus, msg_id, data, bus_name):
        """
        Helper method to send message on specific bus.
        """
        try:
            msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=self.is_extended_id)
            bus.send(msg)
            logger.info(f"Message sent on {bus_name} bus: {msg}")
            return True
        except Exception as e:
            logger.error(f"Error sending message on {bus_name} bus: {e}")
            return False

    def send_control_message(self, arbitration_id=None, data=None):
        """
        Send message on control bus (legacy method for compatibility).
        """
        msg_id = arbitration_id or self.arbitration_id
        msg_data = data or self.data
        return self.send_message_on_correct_bus(msg_id, msg_data)

    def create_message(self):
        """
        Construct a can.Message object using the stored arbitration ID, data, and ID type.
        """
        return can.Message(
            arbitration_id=self.arbitration_id,
            data=self.data,
            is_extended_id=self.is_extended_id
        )

    def send_message(self):
        """
        Send a single CAN message on the appropriate bus based on stored arbitration_id.
        """
        return self.send_message_on_correct_bus(self.arbitration_id, self.data)

    def shutdown(self):
        """
        Clean up both CAN buses when shutting down.
        """
        for bus_name, bus in [("control", self.control_bus), ("logging", self.logging_bus)]:
            if bus:
                try:
                    bus.shutdown()
                    logger.info(f"{bus_name.capitalize()} bus shut down cleanly")
                except Exception as e:
                    logger.error(f"Error shutting down {bus_name} bus: {e}")

class CANDispatcher:
    """
    A dispatcher to decouple event handling from message processing.
    Supports both general callbacks and bus-specific callbacks.
    """
    def __init__(self):
        self.callbacks = {}  # (msg_id, signal_name) -> [callback, callback...]
        self.bus_specific_callbacks = {}  # (msg_id, signal_name, bus_type) -> [callback, callback...]

    def register_callback(self, msg_id, signal_name, callback):
        """
        Register a callback to be invoked when 'signal_name' of message 'msg_id' is decoded.
        """
        key = (msg_id, signal_name)
        if key not in self.callbacks:
            self.callbacks[key] = []
        self.callbacks[key].append(callback)

    def register_bus_callback(self, msg_id, signal_name, callback, bus_type=None):
        """
        Register callback for specific bus type.
        """
        key = (msg_id, signal_name, bus_type)
        if key not in self.bus_specific_callbacks:
            self.bus_specific_callbacks[key] = []
        self.bus_specific_callbacks[key].append(callback)

    def dispatch(self, msg_id, decoded_signals, bus_type=None):
        """
        Dispatch events for each signal in decoded_signals if there's a matching registered callback.
        """
        for signal_name, value in decoded_signals.items():
            # Regular callbacks
            key = (msg_id, signal_name)
            if key in self.callbacks:
                for callback in self.callbacks[key]:
                    try:
                        callback(value)
                    except Exception as e:
                        logger.error(f"Error in callback for {signal_name}: {e}")
            
            # Bus-specific callbacks
            bus_key = (msg_id, signal_name, bus_type)
            if bus_key in self.bus_specific_callbacks:
                for callback in self.bus_specific_callbacks[bus_key]:
                    try:
                        callback(value)
                    except Exception as e:
                        logger.error(f"Error in bus-specific callback for {signal_name}: {e}")

class AllMsg:
    """
    GUI class to display messages in a secondary window and manage callbacks for certain signals.
    Supports dual CAN bus monitoring with proper message routing.
    """
    def __init__(self, root, controller, dbc_path="H20_CAN_dbc.dbc",
                 control_channel="can0", logging_channel="can1"):
        self.root = root
        self.root.title("CAN Messages and Values - Dual Bus Monitor")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        self.controller = controller
        self.running = True
        self.msg_data = {}  # Dictionary to store messages and their signals for display

        # Create a dispatcher instance to manage callbacks
        self.dispatcher = CANDispatcher()
        
        # Message routing configuration based on H20 specification
        self.control_message_ids = self._get_control_message_ids()
        self.logging_message_ids = self._get_logging_message_ids()
        
        # Register callbacks for the important signals
        self.register_all_callbacks()
        
        # Create the GUI components
        self.create_gui()
        
        # Attempt to create dual ThreadSafeBus instances
        self.db = load_dbc_file(dbc_path)
        self.control_bus, self.logging_bus = self.setup_dual_threadsafe_buses(
            control_channel, logging_channel)

        # Schedule message reception every 50ms for dual bus monitoring
        self.root.after(50, self.receive_messages)

    def _get_control_message_ids(self):
        """
        Define which message IDs belong to control bus based on H20 specification (0x240-0x32F).
        """
        return {
            # AMS Control (0x240-0x24F)
            *range(0x240, 0x250),
            
            # IVTS Control (0x250-0x25F)
            *range(0x250, 0x260),
            
            # CCU Control (0x260-0x26F)
            *range(0x260, 0x270),
            
            # PDU Control (0x270-0x27F)
            *range(0x270, 0x280),
            
            # VCU Control (0x280-0x28F) 
            *range(0x280, 0x290),
            
            # ASPU Control (0x290-0x29F)
            *range(0x290, 0x2A0),
            
            # ASCU Control (0x2A0-0x2AF)
            *range(0x2A0, 0x2B0),
            
            # DIU Control (0x2B0-0x2BF)
            *range(0x2B0, 0x2C0),
            
            # DRS Control (0x2C0-0x2CF)
            *range(0x2C0, 0x2D0),
            
            # DTU Control (0x2D0-0x2DF)
            *range(0x2D0, 0x2E0),
            
            # SEN Control (0x2E0-0x2EF)
            *range(0x2E0, 0x2F0),
            
            # SWU Control (0x2F0-0x2FF)
            *range(0x2F0, 0x300),
            
            # Kistler Control (0x300-0x30F)
            *range(0x300, 0x310),
            
            # DIU Range (0x420-0x42F) - includes heartbeat
            *range(0x420, 0x430),
            
            # Software Version Requests (0x516)
            0x516,
            
            # Heartbeats that are on control bus
            0x022, 0x023, 0x025,  # AMS_Control, ASCU_Heartbeat, DIU_Heartbeat
        }
    
    def _get_logging_message_ids(self):
        """
        Define which message IDs belong to logging bus based on H20 specification (0x330-0x4FF).
        """
        return {
            # AMS Logging (0x330-0x35F)
            *range(0x330, 0x360),
            
            # IVTS Logging (0x360-0x36F)
            *range(0x360, 0x370),
            
            # CCU Logging (0x370-0x37F)
            *range(0x370, 0x380),
            
            # PDU Logging (0x380-0x38F)
            *range(0x380, 0x390),
            
            # VCU Logging (0x3A0-0x3DF)
            *range(0x3A0, 0x3E0),
            
            # ASPU Logging (0x3E0-0x3FF)
            *range(0x3E0, 0x400),
            
            # ASCU Logging (0x400-0x41F)
            *range(0x400, 0x420),
            
            # FSG Logger (0x430)
            0x430,
            
            # DRS Logging (0x431-0x43F)
            *range(0x431, 0x440),
            
            # DTU Logging (0x440-0x44F)
            *range(0x440, 0x450),
            
            # SEN Logging (0x450-0x48F)
            *range(0x450, 0x490),
            
            # Kistler Logging (0x4D0-0x4DF)
            *range(0x4D0, 0x4E0),
            
            # Software version responses
            *range(0x518, 0x521),
        }

    def setup_dual_threadsafe_buses(self, control_channel, logging_channel):
        """
        Setup dual ThreadSafeBus instances for concurrent access.
        Returns tuple of (control_bus, logging_bus).
        """
        control_bus = None
        logging_bus = None
        
        # Setup control bus
        try:
            control_bus = can.ThreadSafeBus(channel=control_channel, bustype="socketcan", bitrate=1000000)
            logger.info(f"Control ThreadSafeBus initialized on {control_channel}")
        except Exception as e:
            logger.warning(f"Control bus fallback to vcan0: {e}")
            try:
                control_bus = can.ThreadSafeBus(channel="vcan0", bustype="socketcan")
                logger.info("Control ThreadSafeBus using vcan0 (virtual)")
            except Exception as e2:
                logger.error(f"Control bus setup failed: {e2}")
        
        # Setup logging bus
        try:
            logging_bus = can.ThreadSafeBus(channel=logging_channel, bustype="socketcan", bitrate=1000000)
            logger.info(f"Logging ThreadSafeBus initialized on {logging_channel}")
        except Exception as e:
            logger.warning(f"Logging bus fallback to vcan1: {e}")
            try:
                logging_bus = can.ThreadSafeBus(channel="vcan1", bustype="socketcan")
                logger.info("Logging ThreadSafeBus using vcan1 (virtual)")
            except Exception as e2:
                logger.error(f"Logging bus setup failed: {e2}")
                
        return control_bus, logging_bus

    def create_gui(self):
        """Create the GUI components for displaying CAN messages from both buses"""
        # Main frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top frame for filters and controls
        top_frame = tk.Frame(main_frame, bg="#f0f0f0")
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Add filter by message ID
        tk.Label(top_frame, text="Filter by ID:").pack(side=tk.LEFT, padx=5)
        self.id_filter = tk.Entry(top_frame, width=10)
        self.id_filter.pack(side=tk.LEFT, padx=5)
        
        # Add filter by signal name
        tk.Label(top_frame, text="Filter by Signal:").pack(side=tk.LEFT, padx=5)
        self.signal_filter = tk.Entry(top_frame, width=15)
        self.signal_filter.pack(side=tk.LEFT, padx=5)
        
        # Add bus filter
        tk.Label(top_frame, text="Filter by Bus:").pack(side=tk.LEFT, padx=5)
        self.bus_filter = ttk.Combobox(top_frame, values=["All", "Control", "Logging"], width=10)
        self.bus_filter.set("All")
        self.bus_filter.pack(side=tk.LEFT, padx=5)
        
        # Add filter button
        filter_button = tk.Button(top_frame, text="Apply Filter", command=self.apply_filter)
        filter_button.pack(side=tk.LEFT, padx=5)
        
        # Add clear filter button
        clear_button = tk.Button(top_frame, text="Clear Filter", command=self.clear_filter)
        clear_button.pack(side=tk.LEFT, padx=5)

        # Add simulate toggle button
        self.sim_running = False
        self.simulate_button = tk.Button(top_frame, text="Start Simulation", command=self.toggle_simulation)
        self.simulate_button.pack(side=tk.LEFT, padx=5)
        
        # Tree frame for displaying messages
        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create a Treeview with columns for the message data (including bus info)
        self.tree = ttk.Treeview(tree_frame, columns=("Message", "Signal", "Value", "Unit", "Bus", "Time"), show="headings")
        self.tree.heading("Message", text="ID")
        self.tree.heading("Signal", text="Signal")
        self.tree.heading("Value", text="Value")
        self.tree.heading("Unit", text="Unit")
        self.tree.heading("Bus", text="Bus")
        self.tree.heading("Time", text="Last Update")
        
        # Set column widths
        self.tree.column("Message", width=80)
        self.tree.column("Signal", width=150)
        self.tree.column("Value", width=100)
        self.tree.column("Unit", width=80)
        self.tree.column("Bus", width=80)
        self.tree.column("Time", width=150)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack the tree and scrollbar
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add a status bar
        self.status_bar = tk.Label(main_frame, text="Ready - Monitoring both Control and Logging buses", 
                                  bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def register_all_callbacks(self):
        """Register callbacks for all relevant signals from the DBC file based on H20 specification"""
        
        # === CONTROL BUS SIGNALS (0x240-0x32F) ===
        
        # DIU Heartbeat monitoring (Control Bus: 0x420)
        self.dispatcher.register_callback(
            0x420, "DIU_Heartbeat",
            lambda value: self.controller.update_value("DIU_Heartbeat_Counter", value)
        )
        
        # AMS Control Signals (0x240-0x24F)
        self.dispatcher.register_callback(
            0x240, "AMS_State",
            lambda value: self.controller.update_value("AMS_Status", value)
        )
        self.dispatcher.register_callback(
            0x241, "AMS_Error_Code",
            lambda value: self.controller.update_value("AMS_Error", value)
        )
        self.dispatcher.register_callback(
            0x243, "AMS_SOC_percentage",
            lambda value: self.controller.model.update_value("SOC", value)
        )
        
        # VCU Control Signals (0x280-0x28F)
        self.dispatcher.register_callback(
            0x280, "VCU_Motor_Speed",
            lambda value: self.controller.model.update_value("Speed", value * 3.6)  # Convert to km/h
        )
        self.dispatcher.register_callback(
            0x281, "VCU_Temperature_motor",
            lambda value: self.controller.model.update_value("Motor Temp", value)
        )
        self.dispatcher.register_callback(
            0x282, "VCU_Temperature_inverter_L",
            lambda value: self.controller.model.update_value("Inverter L Temp", value)
        )
        self.dispatcher.register_callback(
            0x282, "VCU_Temperature_inverter_R",
            lambda value: self.controller.model.update_value("Inverter R Temp", value)
        )
        
        # PDU Control Signals (0x270-0x27F)
        self.dispatcher.register_callback(
            0x270, "PDU_HV_Voltage",
            lambda value: self.controller.model.update_value("DC Voltage", value)
        )
        self.dispatcher.register_callback(
            0x271, "PDU_HV_Current",
            lambda value: self.controller.model.update_value("DC Current", value)
        )
        
        # SWU Button States (Control Bus: 0x2F0)
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_1_Menu", 
            lambda value: self.controller.handle_button_press("menu", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_2_OK",
            lambda value: self.controller.handle_button_press("ok", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_3_TC",
            lambda value: self.controller.handle_button_press("tc", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_4_TV",
            lambda value: self.controller.handle_button_press("tv", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_5_DRS",
            lambda value: self.controller.handle_button_press("drs", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_6_R2D",
            lambda value: self.controller.handle_button_press("r2d", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_7_Up",
            lambda value: self.controller.handle_button_press("up", value)
        )
        self.dispatcher.register_callback(
            0x2F0, "SWU_Button_8_Down",
            lambda value: self.controller.handle_button_press("down", value)
        )
        
        # SWU Rotary Encoders (0x2F1)
        self.dispatcher.register_callback(
            0x2F1, "SWU_Rotary_1",
            lambda value: self.controller.handle_rotary_change(1, value)
        )
        self.dispatcher.register_callback(
            0x2F1, "SWU_Rotary_2",
            lambda value: self.controller.handle_rotary_change(2, value)
        )
        
        # DRS Control (0x2C0-0x2CF)
        self.dispatcher.register_callback(
            0x2C0, "DRS_Status",
            lambda value: self.controller.model.update_value("DRS", "Active" if value else "Inactive")
        )
        
        # === LOGGING BUS SIGNALS (0x330+) ===
        
        # AMS Cell Voltages (0x330-0x337)
        for msg_idx in range(8):  # 8 messages
            msg_id = 0x330 + msg_idx
            for cell_idx in range(8):  # 8 cells per message
                signal_name = f"AMS_Cell_V_{msg_idx*8 + cell_idx + 1:03d}"
                global_idx = msg_idx * 8 + cell_idx + 1
                self.dispatcher.register_callback(
                    msg_id, signal_name,
                    lambda value, idx=global_idx: self.controller.model.map_cell_voltage(idx, value)
                )
        
        # AMS Temperatures (0x340-0x34F)
        for msg_idx in range(16):  # 16 messages
            msg_id = 0x340 + msg_idx
            for temp_idx in range(4):  # 4 temperatures per message
                signal_name = f"AMS_Temp_{msg_idx*4 + temp_idx + 1:03d}"
                global_idx = msg_idx * 4 + temp_idx + 1
                self.dispatcher.register_callback(
                    msg_id, signal_name,
                    lambda value, idx=global_idx: self.controller.model.map_temp_value(idx, value)
                )
        
        # AMS Logging Data (0x350)
        self.dispatcher.register_callback(
            0x350, "AMS_Pack_Voltage",
            lambda value: self.controller.model.update_value("DC Voltage", value)
        )
        self.dispatcher.register_callback(
            0x350, "AMS_Pack_Current", 
            lambda value: self.controller.model.update_value("DC Current", value)
        )
        self.dispatcher.register_callback(
            0x351, "AMS_Lowest_Cell_Voltage",
            lambda value: self.controller.model.update_value("Cell Min V", value)
        )
        self.dispatcher.register_callback(
            0x351, "AMS_Highest_Cell_Voltage",
            lambda value: self.controller.model.update_value("Cell Max V", value)
        )
        
        # VCU Logging Data (0x3A0-0x3DF)
        self.dispatcher.register_callback(
            0x3A0, "VCU_Wheel_Speed_FL",
            lambda value: self.controller.model.update_value("Front Left Wheel", value)
        )
        self.dispatcher.register_callback(
            0x3A0, "VCU_Wheel_Speed_FR",
            lambda value: self.controller.model.update_value("Front Right Wheel", value)
        )
        self.dispatcher.register_callback(
            0x3A1, "VCU_Wheel_Speed_RL",
            lambda value: self.controller.model.update_value("Rear Left Wheel", value)
        )
        self.dispatcher.register_callback(
            0x3A1, "VCU_Wheel_Speed_RR",
            lambda value: self.controller.model.update_value("Rear Right Wheel", value)
        )
        self.dispatcher.register_callback(
            0x3A2, "VCU_Yaw_Rate",
            lambda value: self.controller.model.update_value("Yaw Rate", value)
        )
        self.dispatcher.register_callback(
            0x3A3, "VCU_Lateral_G",
            lambda value: self.controller.model.update_value("Lateral G", value)
        )
        self.dispatcher.register_callback(
            0x3A3, "VCU_Longitudinal_G",
            lambda value: self.controller.model.update_value("Longitudinal G", value)
        )
        
        # PDU Logging Data (0x380-0x38F)
        self.dispatcher.register_callback(
            0x380, "PDU_Watt_Hours",
            lambda value: self.controller.model.update_value("Watt Hours", value)
        )
        self.dispatcher.register_callback(
            0x381, "PDU_Energy_Used",
            lambda value: self.controller.model.update_value("Energy Used", value / 1000)  # Convert to kWh
        )
        
        # IVTS Data (0x360-0x36F)
        self.dispatcher.register_callback(
            0x360, "IVTS_Throttle_Position",
            lambda value: self.controller.model.update_value("Throttle", value)
        )
        self.dispatcher.register_callback(
            0x360, "IVTS_Brake_Pressure",
            lambda value: self.controller.model.update_value("Brake", value)
        )
        self.dispatcher.register_callback(
            0x361, "IVTS_Steering_Angle",
            lambda value: self.controller.model.update_value("Steering", value)
        )
        
        # Sensor Data (0x450-0x48F)
        self.dispatcher.register_callback(
            0x450, "SEN_IMU_Yaw_Rate",
            lambda value: self.controller.model.update_value("Yaw Rate", value)
        )
        self.dispatcher.register_callback(
            0x451, "SEN_IMU_Accel_Lat",
            lambda value: self.controller.model.update_value("Lateral G", value / 9.81)  # Convert to g
        )
        self.dispatcher.register_callback(
            0x451, "SEN_IMU_Accel_Long",
            lambda value: self.controller.model.update_value("Longitudinal G", value / 9.81)  # Convert to g
        )
        
        # ECU Heartbeats (various IDs)
        heartbeat_ecus = {
            0x022: "AMS",
            0x023: "ASCU", 
            0x025: "DIU",
            0x240: "AMS",
            0x250: "IVTS",
            0x260: "CCU",
            0x270: "PDU",
            0x280: "VCU",
            0x290: "ASPU",
            0x2A0: "ASCU",
            0x2B0: "DIU",
            0x2C0: "DRS",
            0x2D0: "DTU",
            0x2E0: "SEN",
            0x2F0: "SWU"
        }
        
        for msg_id, ecu_name in heartbeat_ecus.items():
            self.dispatcher.register_callback(
                msg_id, f"{ecu_name}_Heartbeat",
                lambda value, name=ecu_name: self.controller.handle_heartbeat(name, value)
            )
        
        # Software Version Messages (0x516 request, 0x518-0x520 responses)
        version_ecus = {
            0x518: "AMS",
            0x519: "VCU",
            0x51A: "PDU",
            0x51B: "IVTS",
            0x51C: "CCU",
            0x51D: "ASPU",
            0x51E: "ASCU",
            0x51F: "DIU",
            0x520: "DRS"
        }
        
        for msg_id, ecu_name in version_ecus.items():
            self.dispatcher.register_callback(
                msg_id, f"{ecu_name}_SW_Version",
                lambda value, name=ecu_name: self.controller.model.update_value(f"{name}_Version", value)
            )
        
        logger.info(f"Registered {len(self.dispatcher.callbacks)} callbacks for CAN signal processing")

    def receive_messages(self):
        """Receive messages from both CAN buses"""
        if not self.running:
            return
            
        # Check control bus
        if self.control_bus:
            try:
                msg = self.control_bus.recv(timeout=0.01)
                if msg:
                    self.process_message(msg, bus_type="control")
            except can.CanError:
                pass
                
        # Check logging bus
        if self.logging_bus:
            try:
                msg = self.logging_bus.recv(timeout=0.01)
                if msg:
                    self.process_message(msg, bus_type="logging")
            except can.CanError:
                pass
        
        # Schedule next check
        self.root.after(50, self.receive_messages)

    def process_message(self, msg, bus_type="unknown"):
        """Process a CAN message, update the display and dispatch to callbacks"""
        if not self.db:
            return
            
        try:
            decoded = decode_message(self.db, msg)
            if decoded:
                current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                if msg.arbitration_id not in self.msg_data:
                    self.msg_data[msg.arbitration_id] = {}
                    
                for signal_name, value in decoded.items():
                    # Get signal unit
                    unit = ""
                    try:
                        signal = self.db.get_message_by_frame_id(msg.arbitration_id).get_signal_by_name(signal_name)
                        unit = signal.unit if hasattr(signal, 'unit') else ""
                    except:
                        pass
                        
                    # Store with bus information
                    self.msg_data[msg.arbitration_id][signal_name] = {
                        'value': value,
                        'unit': unit,
                        'time': current_time,
                        'bus': bus_type.capitalize()
                    }
                
                # Dispatch callbacks
                self.dispatcher.dispatch(msg.arbitration_id, decoded, bus_type)
                
                # Update display
                self.update_display()
        except Exception as e:
            logger.debug(f"Error processing message: {e}")

    def update_display(self):
        """Update the tree view with current message data"""
        # Clear all items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Get filter values
        id_filter = self.id_filter.get().strip().lower()
        signal_filter = self.signal_filter.get().strip().lower()
        bus_filter = self.bus_filter.get().strip().lower()
        
        # Insert filtered messages and their signals
        row_count = 0
        for msg_id, signals in self.msg_data.items():
            hex_id = hex(msg_id) if isinstance(msg_id, int) else str(msg_id)
            
            # Check if the message ID matches the filter
            if id_filter and id_filter not in hex_id.lower():
                continue
                
            for signal_name, signal_info in signals.items():
                signal_value = signal_info.get('value', 'N/A')
                signal_unit = signal_info.get('unit', '')
                signal_time = signal_info.get('time', 'N/A')
                signal_bus = signal_info.get('bus', 'unknown')
                
                # Check filters
                if signal_filter and signal_filter not in signal_name.lower():
                    continue
                if bus_filter != "all" and bus_filter != signal_bus.lower():
                    continue
                    
                # Insert the item
                self.tree.insert("", "end", values=(hex_id, signal_name, signal_value, signal_unit, signal_bus, signal_time))
                row_count += 1
        
        # Update status bar
        self.status_bar.config(text=f"Showing {row_count} signals from {len(self.msg_data)} message IDs")

    def apply_filter(self):
        """Apply the filter by updating the display"""
        self.update_display()

    def clear_filter(self):
        """Clear all filters"""
        self.id_filter.delete(0, tk.END)
        self.signal_filter.delete(0, tk.END)
        self.bus_filter.set("All")
        self.update_display()

    def toggle_simulation(self):
        """Toggle simulation mode"""
        if self.sim_running:
            self.stop_simulation()
        else:
            self.start_simulation()

    def start_simulation(self):
        """Start simulating CAN messages"""
        self.sim_running = True
        self.simulate_button.config(text="Stop Simulation")
        self.simulation_thread = threading.Thread(target=self._simulate_messages, daemon=True)
        self.simulation_thread.start()
        logger.info("Simulation started")

    def stop_simulation(self):
        """Stop simulating CAN messages"""
        self.sim_running = False
        self.simulate_button.config(text="Start Simulation")
        logger.info("Simulation stopped")

    def _simulate_messages(self):
        """Generate simulated CAN messages for testing"""
        # Get message IDs for both buses
        control_message_ids = list(self.control_message_ids)
        logging_message_ids = list(self.logging_message_ids)
        
        # State variables for realistic simulation
        soc = 100.0
        speed = 0.0
        motor_temp = 20.0
        inverter_temp = 20.0
        diu_heartbeat = 0
        switch_states = [0, 0, 0, 0, 0]  # 5 switches
        
        while self.sim_running:
            # Simulate control bus messages
            if random.random() < 0.8:  # 80% chance
                msg_id = random.choice(control_message_ids)
                
                if msg_id == 0x420:  # DIU heartbeat
                    # Simulate DIU heartbeat - increment counter every time
                    diu_heartbeat = (diu_heartbeat + 1) % 256
                    data = bytearray([diu_heartbeat, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    
                elif msg_id == 0x2F0:  # SWU buttons
                    if random.random() < 0.1:  # 10% chance to press a button
                        button_states = 1 << random.randint(0, 7)
                    else:
                        button_states = 0
                    data = bytearray([button_states])
                    
                elif msg_id == 0x2F1:  # SWU switches
                    # Occasionally change switch positions
                    if random.random() < 0.05:  # 5% chance
                        switch_idx = random.randint(0, 4)
                        switch_states[switch_idx] = random.randint(0, 15)
                    
                    # Pack switch states (4 bits each)
                    data = bytearray([
                        (switch_states[1] << 4) | switch_states[0],  # Switches 1-2
                        (switch_states[3] << 4) | switch_states[2],  # Switches 3-4
                        switch_states[4],  # Switch 5
                        0x00, 0x00, 0x00, 0x00, 0x00
                    ])
                    
                else:
                    data = bytearray([random.randint(0, 255) for _ in range(8)])
                
                # Create and process control bus message
                message = can.Message(
                    arbitration_id=msg_id,
                    data=data,
                    is_extended_id=False,
                    timestamp=time.time()
                )
                self.process_message(message, bus_type="control")
            
            # Simulate logging bus messages
            if random.random() < 0.7:  # 70% chance
                msg_id = random.choice(logging_message_ids)
                
                if msg_id == 0x330:  # AMS SOC
                    soc = max(0, soc - random.uniform(0, 0.1))
                    data = bytearray([int(soc), int(soc), 0, 0, 0, 0, 0, 0])
                    
                elif msg_id == 0x333:  # Cell voltages
                    # Update cell voltages with slight variation
                    base_voltage = 3.7 + (soc / 100.0) * 0.5
                    cell_voltages = [base_voltage + random.uniform(-0.05, 0.05) for _ in range(8)]
                    data = bytearray()
                    for v in cell_voltages:
                        # Pack as 16-bit value (voltage * 1000)
                        v_int = int(v * 1000)
                        data.extend([(v_int >> 8) & 0xFF, v_int & 0xFF])
                    data = data[:8]  # Ensure 8 bytes
                    
                elif msg_id in range(0x3A0, 0x3A4):  # VCU data
                    if msg_id == 0x3A0:  # Wheel speeds
                        speed += random.uniform(-5, 10)
                        speed = max(0, min(200, speed))
                        data = bytearray([int(speed), int(speed), int(speed), int(speed), 0, 0, 0, 0])
                    else:
                        data = bytearray([random.randint(0, 255) for _ in range(8)])
                        
                else:
                    data = bytearray([random.randint(0, 255) for _ in range(8)])
                
                # Create and process logging bus message
                message = can.Message(
                    arbitration_id=msg_id,
                    data=data,
                    is_extended_id=False,
                    timestamp=time.time()
                )
                self.process_message(message, bus_type="logging")
            
            time.sleep(0.1)  # 10Hz simulation rate

    def stop(self):
        """Stop the monitor and cleanup"""
        self.running = False
        if hasattr(self, 'simulation_thread') and self.simulation_thread.is_alive():
            self.sim_running = False
            self.simulation_thread.join(timeout=1.0)
        
        # Close both buses
        if self.control_bus:
            try:
                self.control_bus.shutdown()
            except:
                pass
                
        if self.logging_bus:
            try:
                self.logging_bus.shutdown()
            except:
                pass
                
        self.root.destroy()