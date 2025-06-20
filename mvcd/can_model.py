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
            # AMS Logging (0x330-0x35F) - 48 IDs
            *range(0x330, 0x360),
            
            # IVTS Logging (0x360-0x36F) - 16 IDs
            *range(0x360, 0x370),
            
            # CCU Logging (0x370-0x37F) - 16 IDs  
            *range(0x370, 0x380),
            
            # PDU Logging (0x380-0x39F) - 32 IDs
            *range(0x380, 0x3A0),
            
            # VCU Logging (0x3A0-0x3DF) - 64 IDs  
            *range(0x3A0, 0x3E0),
            
            # ASPU Logging (0x3E0-0x3FF) - 32 IDs
            *range(0x3E0, 0x400),
            
            # ASCU Logging (0x400-0x41F) - 32 IDs
            *range(0x400, 0x420),
            
            # DIU Logging (0x420-0x42F) - 16 IDs
            *range(0x420, 0x430),
            
            # FSG Logger (0x430)
            0x430,
            
            # DRS Logging (0x431-0x43F) - 15 IDs
            *range(0x431, 0x440),
            
            # DTU Logging (0x440-0x44F) - 16 IDs
            *range(0x440, 0x450),
            
            # SEN Logging (0x450-0x48F) - 64 IDs
            *range(0x450, 0x490),
            
            # Free range (0x490-0x4CF) - 64 IDs
            *range(0x490, 0x4D0),
            
            # Kistler Logging (0x4D0-0x4DF) - 16 IDs
            *range(0x4D0, 0x4E0),
            
            # Software Versions (0x518-0x520)
            *range(0x518, 0x521),
        }

    def setup_dual_threadsafe_buses(self, control_channel, logging_channel):
        """
        Setup both ThreadSafeBus instances with fallback to virtual buses.
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
        
        # === CONTROL BUS SIGNALS ===
        
        # DIU Button States (Control Bus: 0x2B0)
        self.dispatcher.register_callback(
            0x2B0, "Menu", 
            lambda value: self.controller.menu_toggle() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "Ok",
            lambda value: self.controller.handle_ok_button() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "Cooling",
            lambda value: self.controller.toggle_cooling() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "Overall_Reset",
            lambda value: self.controller.perform_reset() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "TS_On",
            lambda value: self.controller.toggle_ts() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "R2D",
            lambda value: self.controller.toggle_r2d() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "9_Down_RadioActive",
            lambda value: self.controller.handle_down_button() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            0x2B0, "Up_DRS",
            lambda value: self.controller.handle_up_button() if value == 1 else None
        )
        
        # AMS Control signals (Control Bus: 0x243)
        self.dispatcher.register_callback(
            0x243, "SOC_percentage_from_Coloumb_Counting",
            lambda value: self.controller.update_value("SOC", value)
        )
        
        # === LOGGING BUS SIGNALS ===
        
        # AMS Cell Voltages (Logging Bus: 0x333-0x344)
        for msg_id in range(0x333, 0x345):  # AMS_Cell_V_000_007 to AMS_Cell_V_136_143
            message_offset = (msg_id - 0x333) * 8
            for local_idx in range(8):
                global_cell_idx = message_offset + local_idx
                signal_name = f"AMS_Cell_V_{global_cell_idx:03d}"
                self.dispatcher.register_callback(
                    msg_id, signal_name, 
                    lambda value, cidx=global_cell_idx: self.controller._on_cell_voltage_update(cidx, value)
                )
        
        # AMS Temperatures (Logging Bus: 0x345-0x34B)  
        for msg_id in range(0x345, 0x34C):  # AMS_Temp_000_007 to AMS_Temp_048_053
            temp_offset = (msg_id - 0x345) * 8
            for local_idx in range(8):
                global_temp_idx = temp_offset + local_idx
                signal_name = f"AMS_Temp_{global_temp_idx:03d}"
                self.dispatcher.register_callback(
                    msg_id, signal_name,
                    lambda value, temp_idx=global_temp_idx: 
                        self.controller.update_value("Accu Temp", value) if value > (self.controller.model.get_value("Accu Temp") or 0) else None
                )
        
        # VCU Sensor Data (Logging Bus: 0x3A0-0x3DF range)
        # These will need to be updated with actual signal names from the DBC file
        self.dispatcher.register_callback(
            0x3A0, "VCU_Temp_Motor",
            lambda value: self.controller.update_value("Motor Temp", value)
        )
        
        self.dispatcher.register_callback(
            0x3A1, "VCU_Temp_Inverter_IGBT",
            lambda value: self.controller.update_value("Inverter Temp", value)
        )
        
        # ASPU Vehicle Data (Logging Bus)
        self.dispatcher.register_callback(
            0x3E0, "speed_actual",
            lambda value: self.controller.update_value("Speed", value)
        )

    def apply_filter(self):
        """Apply filters to the Treeview"""
        self.update_tree()

    def clear_filter(self):
        """Clear all filters"""
        self.id_filter.delete(0, tk.END)
        self.signal_filter.delete(0, tk.END)
        self.bus_filter.set("All")
        self.update_tree()

    def toggle_simulation(self):
        """Toggle the simulation mode on/off"""
        self.sim_running = not self.sim_running
        
        if self.sim_running:
            self.simulate_button.config(text="Stop Simulation")
            self.start_simulation()
        else:
            self.simulate_button.config(text="Start Simulation")
            self.stop_simulation()

    def start_simulation(self):
        """Start the simulation of CAN messages for both buses"""
        if hasattr(self, 'sim_thread') and self.sim_thread and self.sim_thread.is_alive():
            return
            
        self.sim_running = True
        self.sim_thread = threading.Thread(target=self.simulation_loop, daemon=True)
        self.sim_thread.start()
        self.status_bar.config(text="Simulation active on both buses")

    def stop_simulation(self):
        """Stop the simulation of CAN messages"""
        self.sim_running = False
        if hasattr(self, 'sim_thread') and self.sim_thread:
            self.sim_thread.join(timeout=0.5)
        self.status_bar.config(text="Simulation stopped")

    def simulation_loop(self):
        """Generate simulated CAN messages for both control and logging buses"""
        # Control bus message IDs
        control_message_ids = [0x2B0, 0x243, 0x2A0]  # DIU buttons, AMS SOC, ASCU control
        
        # Logging bus message IDs  
        logging_message_ids = [0x333, 0x345, 0x3A0, 0x3E0]  # Cell voltages, temps, VCU, ASPU
        
        # Simulation state variables
        soc = 100.0
        cell_voltages = [4.2] * 144  # 144 cells
        temperatures = [25.0] * 54   # 54 temperature sensors
        motor_temp = 25.0
        speed = 0.0
        button_states = 0
        
        while self.sim_running:
            # Simulate control bus messages
            if random.random() < 0.3:  # 30% chance
                msg_id = random.choice(control_message_ids)
                if msg_id == 0x2B0:  # DIU buttons
                    if random.random() < 0.1:  # 10% chance to press a button
                        button_states = 1 << random.randint(0, 7)
                    else:
                        button_states = 0
                    data = bytearray([button_states])
                elif msg_id == 0x243:  # AMS SOC
                    soc = max(0, soc - random.uniform(0, 0.1))
                    data = bytearray([int(soc), int(soc), 0, 0, 0, 0, 0, 0])
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
                if msg_id == 0x333:  # Cell voltages
                    # Update cell voltages with slight variation
                    base_voltage = 3.7 + (soc / 100.0) * 0.5
                    data = bytearray()
                    for i in range(8):
                        voltage = base_voltage + random.uniform(-0.1, 0.1)
                        voltage_raw = int((voltage - 2.5) / 0.01)  # Convert to raw value
                        data.append(max(0, min(255, voltage_raw)))
                elif msg_id == 0x345:  # Temperatures
                    data = bytearray()
                    for i in range(8):
                        temp = 25 + random.uniform(-5, 15)
                        data.append(int(temp))
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
            
            # Sleep between messages
            time.sleep(random.uniform(0.05, 0.2))

    def update_tree(self):
        """Refresh the Treeview with current message data, applying filters"""
        # Clear existing entries
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
                        'bus': bus_type
                    }
                
                # Dispatch to callbacks
                self.dispatcher.dispatch(msg.arbitration_id, decoded, bus_type)
                
            else:
                # Store raw message data if decoding failed
                if msg.arbitration_id not in self.msg_data:
                    self.msg_data[msg.arbitration_id] = {}
                    
                self.msg_data[msg.arbitration_id]["RAW_DATA"] = {
                    'value': ' '.join(f'{b:02X}' for b in msg.data),
                    'unit': "",
                    'time': datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    'bus': bus_type
                }
        except Exception as e:
            logger.error(f"Error processing message from {bus_type} bus: {e}")
                
        # Update the tree view
        self.update_tree()

    def receive_messages(self):
        """Periodically receive CAN messages from both buses"""
        if not self.running:
            return

        # Receive from control bus
        if self.control_bus:
            try:
                message = self.control_bus.recv(timeout=0.025)
                if message:
                    self.process_message(message, bus_type="control")
            except Exception as e:
                logger.error(f"Error receiving from control bus: {e}")

        # Receive from logging bus  
        if self.logging_bus:
            try:
                message = self.logging_bus.recv(timeout=0.025)
                if message:
                    self.process_message(message, bus_type="logging")
            except Exception as e:
                logger.error(f"Error receiving from logging bus: {e}")

        # Schedule the next reception
        self.root.after(50, self.receive_messages)

    def stop(self):
        """Stop receiving messages and shut down both CAN buses"""
        self.running = False
        self.sim_running = False
        
        if hasattr(self, 'sim_thread') and self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=0.5)
            
        for bus_name, bus in [("control", self.control_bus), ("logging", self.logging_bus)]:
            if bus:
                try:
                    bus.shutdown()
                    logger.info(f"{bus_name.capitalize()} bus stopped")
                except Exception as e:
                    logger.error(f"Error stopping {bus_name} bus: {e}")
                    
        self.root.destroy()