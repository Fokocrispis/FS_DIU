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
    Core CAN functionality (non-GUI). Handles sending messages.
    If the system doesn't support SocketCAN (e.g., Windows), it falls back to no-op.
    """
    def __init__(self, arbitration_id=0xC0FFEE, data=None, is_extended_id=True, dbc_path="H20_CAN_dbc.dbc"):
        self.arbitration_id = arbitration_id
        self.data = data if data else [0x00] * 8
        self.is_extended_id = is_extended_id
        self.dbc_path = dbc_path

        # Load the DBC file
        self.db = load_dbc_file(dbc_path)

        # Attempt to initialize CAN bus
        self.bus = self.setup_can_bus()

    def setup_can_bus(self):
        """
        Create and return a can.Bus instance, or None if unavailable.
        Tries real CAN first, then virtual CAN, then falls back to None.
        """
        try:
            # Try real CAN bus first
            bus = can.Bus(channel="can0", bustype="socketcan", bitrate=1000000)
            logger.info("CAN Bus (can0) initialized successfully.")
            return bus
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to initialize CAN bus on can0: {e}")
            
            # Try virtual CAN (vcan0)
            try:
                bus = can.Bus(channel="vcan0", bustype="socketcan")
                logger.info("CAN Bus (vcan0) initialized successfully.")
                return bus
            except Exception as e2:
                logger.error(f"Failed to initialize virtual CAN bus: {e2}")
                logger.info("Falling back to no-op CAN mode (no real bus).")
                return None

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
        Send a single CAN message if the bus is available. Otherwise, do nothing.
        """
        msg = self.create_message()
        if self.bus:
            try:
                self.bus.send(msg)
                logger.info(f"CAN message sent: {msg}")
                return True
            except can.CanError as e:
                logger.error(f"Error sending CAN message: {e}")
                return False
        else:
            logger.warning("No CAN bus available. Skipping send_message().")
            return False
            
    def shutdown(self):
        """
        Clean up CAN resources when shutting down
        """
        if self.bus:
            try:
                self.bus.shutdown()
                logger.info("CAN bus shut down cleanly")
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")

class CANDispatcher:
    """
    A simple dispatcher to decouple event handling from message processing.
    You register callbacks per (msg_id, signal_name) pair.
    """
    def __init__(self):
        self.callbacks = {}  # (msg_id, signal_name) -> [callback, callback...]

    def register_callback(self, msg_id, signal_name, callback):
        """
        Register a callback to be invoked when 'signal_name' of message 'msg_id' is decoded.
        """
        key = (msg_id, signal_name)
        if key not in self.callbacks:
            self.callbacks[key] = []
        self.callbacks[key].append(callback)

    def dispatch(self, msg_id, decoded_signals):
        """
        Dispatch events for each signal in decoded_signals if there's a matching registered callback.
        """
        for signal_name, value in decoded_signals.items():
            key = (msg_id, signal_name)
            if key in self.callbacks:
                for callback in self.callbacks[key]:
                    try:
                        callback(value)
                    except Exception as e:
                        logger.error(f"Error in callback for {signal_name}: {e}")

class AllMsg:
    """
    GUI class to display messages in a secondary window and manage callbacks for certain signals.
    Periodically receives messages via root.after scheduling.
    If on Windows without a SocketCAN interface, 'bus' will be None and receive_messages() won't do anything.
    """
    def __init__(self, root, controller, dbc_path="H20_CAN_dbc.dbc"):
        self.root = root
        self.root.title("CAN Messages and Values")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        self.controller = controller
        self.running = True
        self.msg_data = {}  # Dictionary to store messages and their signals for display

        # Create a dispatcher instance to manage callbacks
        self.dispatcher = CANDispatcher()
        
        # Register callbacks for the important signals
        self.register_all_callbacks()
        
        # Create the GUI components
        self.create_gui()
        
        # Attempt to create a ThreadSafeBus
        self.db = load_dbc_file(dbc_path)
        self.bus = self.setup_threadsafe_bus()

        # Schedule message reception every 100 ms
        self.root.after(100, self.receive_messages)
    
    def create_gui(self):
        """Create the GUI components for displaying CAN messages"""
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
        
        # Create a Treeview with columns for the message data
        self.tree = ttk.Treeview(tree_frame, columns=("Message", "Signal", "Value", "Unit", "Time"), show="headings")
        self.tree.heading("Message", text="ID")
        self.tree.heading("Signal", text="Signal")
        self.tree.heading("Value", text="Value")
        self.tree.heading("Unit", text="Unit")
        self.tree.heading("Time", text="Last Update")
        
        # Set column widths
        self.tree.column("Message", width=80)
        self.tree.column("Signal", width=150)
        self.tree.column("Value", width=100)
        self.tree.column("Unit", width=80)
        self.tree.column("Time", width=150)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack the tree and scrollbar
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add a status bar
        self.status_bar = tk.Label(main_frame, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def register_all_callbacks(self):
        """Register callbacks for all relevant signals from the DBC file"""
    
        # === Switch Wheel Unit (SWU) signals for steering wheel buttons ===
        # SWU_Button_States (ID: 752) signals for steering wheel buttons - In H20 DBC
        self.dispatcher.register_callback(
            752, "SWU_Button_1_Menu", 
            lambda value: self.controller.menu_toggle() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_2_OK",
            lambda value: self.controller.handle_ok_button() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_3_Cooling",
            lambda value: self.controller.toggle_cooling() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_4_Overall_Reset",
            lambda value: self.controller.perform_reset() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_5_TS_On",
            lambda value: self.controller.toggle_ts() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_6_R2D",
            lambda value: self.controller.toggle_r2d() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_6_9_Down_RadioActive",
            lambda value: self.controller.handle_down_button() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            752, "SWU_Button_8_Up_DRS",
            lambda value: self.controller.handle_up_button() if value == 1 else None
        )
        
        # === Handle Switch States as well (ID: 753) ===
        # This is for more complex switch inputs
        self.dispatcher.register_callback(
            753, "SWU_Switch_1",
            lambda value: self.controller.update_switch_state(1, value)
        )
        
        self.dispatcher.register_callback(
            753, "SWU_Switch_2",
            lambda value: self.controller.update_switch_state(2, value)
        )
        
        self.dispatcher.register_callback(
            753, "SWU_Switch_3",
            lambda value: self.controller.update_switch_state(3, value)
        )
        
        self.dispatcher.register_callback(
            753, "SWU_Switch_4",
            lambda value: self.controller.update_switch_state(4, value)
        )
        
        self.dispatcher.register_callback(
            753, "SWU_Switch_5",
            lambda value: self.controller.update_switch_state(5, value)
        )
        
        # === Cell Voltages for Battery Management ===
        # Register callbacks for all cell voltages in the AMS_Cell_V messages (819-834)
        for msg_id in range(819, 835):
            message_offset = (msg_id - 819) * 8
            # Each message has 8 signals for 8 cells
            for local_idx in range(8):
                # Calculate the global cell index across all messages
                global_cell_idx = message_offset + local_idx
                # Format the signal name to match the DBC definition
                signal_name = f"AMS_Cell_V_{global_cell_idx:03d}"
                # Register a callback for each cell voltage
                self.dispatcher.register_callback(
                    msg_id, signal_name, 
                    lambda value, cidx=global_cell_idx: self.controller._on_cell_voltage_update(cidx, value)
                )
        
        # === SOC Percentage ===
        self.dispatcher.register_callback(
            579, "AMS_SOC_percentage",
            lambda value: self.controller.update_value("SOC", value)
        )
        
        # === Temperatures ===
        # Track temperatures from AMS_Temp messages (835-840)
        for msg_id in range(835, 841):
            temp_offset = (msg_id - 835) * 8
            for local_idx in range(8):
                global_temp_idx = temp_offset + local_idx
                signal_name = f"AMS_Temp_{global_temp_idx:03d}"
                self.dispatcher.register_callback(
                    msg_id, signal_name,
                    lambda value, temp_idx=global_temp_idx: 
                        self.controller.update_value("Accu Temp", value) if value > self.controller.model.get_value("Accu Temp") or 0 else None
                )
        
        # === Inverter and Motor Temperatures ===
        self.dispatcher.register_callback(
            933, "VCU_Temperature_inverter_air",
            lambda value: self.controller.update_value("Inverter Temp", value)
        )
        
        self.dispatcher.register_callback(
            933, "VCU_Temperatures_inverter_igbt",
            lambda value: self.controller.update_value("Inverter L Temp", value)
        )
        
        self.dispatcher.register_callback(
            933, "VCU_Temperatures_inverter_igbt",
            lambda value: self.controller.update_value("Inverter R Temp", value)
        )
        
        self.dispatcher.register_callback(
            933, "VCU_Temperature_motor",
            lambda value: self.controller.update_value("Motor Temp", value)
        )
        
        self.dispatcher.register_callback(
            933, "VCU_Temperature_motor",
            lambda value: self.controller.update_value("Motor L Temp", value)
        )
        
        self.dispatcher.register_callback(
            933, "VCU_Temperature_motor",
            lambda value: self.controller.update_value("Motor R Temp", value)
        )
        
        # === Vehicle Control Parameters ===
        # DRS position state
        self.dispatcher.register_callback(
            1076, "MCU_DRS_position_state",
            lambda value: self.controller.update_value("DRS", "On" if value == 1 else "Off")
        )
        
        # === Max Torque Setting ===
        self.dispatcher.register_callback(
            936, "VCU_nm_max",
            lambda value: self.controller.update_value("Max Torque", value)
        )
        
        # === Speed Information ===
        self.dispatcher.register_callback(
            1001, "ASPU_Abs_Speed_KMH100",
            lambda value: self.controller.update_value("Speed", value / 100)  # Convert to km/h
        )
        
        # === Error Codes & System State ===
        self.dispatcher.register_callback(
            1088, "DTU_ErrorCode",
            lambda value: self.controller.handle_dtu_error(value)
        )
        
        # === PDU Faults (new in H20) ===
        self.dispatcher.register_callback(
            911, "PDU_Fault_VLU",
            lambda value: self.controller.update_pdu_fault("VLU", value == 1)
        )
        
        self.dispatcher.register_callback(
            911, "PDU_Fault_InverterR",
            lambda value: self.controller.update_pdu_fault("InverterR", value == 1)
        )
        
        self.dispatcher.register_callback(
            911, "PDU_Fault_InverterL",
            lambda value: self.controller.update_pdu_fault("InverterL", value == 1)
        )
    
    # Add more fault handlers as needed
    
    def apply_filter(self):
        """Apply filters to the Treeview"""
        self.update_tree()  # Update the tree with the current filters
    
    def clear_filter(self):
        """Clear all filters"""
        self.id_filter.delete(0, tk.END)
        self.signal_filter.delete(0, tk.END)
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
        """Start the simulation of CAN messages"""
        if hasattr(self, 'sim_thread') and self.sim_thread and self.sim_thread.is_alive():
            return  # Already running
            
        self.sim_running = True
        self.sim_thread = threading.Thread(target=self.simulation_loop, daemon=True)
        self.sim_thread.start()
        self.status_bar.config(text="Simulation active")
    
    def stop_simulation(self):
        """Stop the simulation of CAN messages"""
        self.sim_running = False
        if hasattr(self, 'sim_thread') and self.sim_thread:
            self.sim_thread.join(timeout=0.5)
        self.status_bar.config(text="Simulation stopped")
    
    def simulation_loop(self):
        """Generate simulated CAN messages"""
        # Define message IDs to simulate
        message_ids = [
            579,    # AMS_SOC
            752,    # SWU_Button_States
            753,    # SWU_Switch_States (new in H20)
            819,    # AMS_Cell_V_001_008
            835,    # AMS_Temp_001_008
            911,    # PDU_Faults (new in H20)
            933,    # VCU_Temperatures
            936,    # VCU_Requested_Torque_Percentage
            1001,   # ASPU_Vehicle_Data
            1076,   # MCU_DRS_Telemetry_3
            1088    # DTU_ErrorCode (new in H20)
        ]
        
        # Simulation state
        soc = 100.0  # Start with full battery
        cell_voltages = [4.2] * 128  # 128 cells at 4.2V
        temperatures = [25.0] * 48  # 48 temperature sensors at 25°C
        motor_temp = 25.0
        inverter_temp = 25.0
        speed = 0.0
        drs_position = 0  # 0 = Off, 1 = On
        swu_buttons = 0   # All buttons off
        swu_switches = [0, 0, 0, 0, 0]  # 5 switches, values 0-15
        pdu_faults = 0    # No faults
        
        while self.sim_running:
            # Randomly pick a message to update
            msg_id = random.choice(message_ids)
            
            # Create data based on message ID
            if msg_id == 579:  # AMS_SOC
                # Slowly decrease SOC
                soc = max(0, soc - random.uniform(0, 0.1))
                data = bytearray([int(soc), 0, 0, 0, 0, 0, 0, 0])
            
            elif msg_id == 752:  # SWU_Button_States
                # Randomly trigger a button press
                if random.random() < 0.1:  # 10% chance to press a button
                    button_idx = random.randint(0, 7)
                    swu_buttons = 1 << button_idx  # Set the bit for this button
                else:
                    swu_buttons = 0  # All buttons off
                
                data = bytearray([swu_buttons & 0xFF])
                
            elif msg_id == 753:  # SWU_Switch_States (new in H20)
                # Randomly change a switch position
                if random.random() < 0.05:  # 5% chance
                    switch_idx = random.randint(0, 4)
                    swu_switches[switch_idx] = random.randint(0, 15)  # 4-bit values (0-15)
                
                # Pack switch values into message
                # Format: Switch1(0-3), Switch2(4-7), Switch3(8-11), Switch4(12-15), Switch5(16-19)
                data = bytearray([
                    swu_switches[0] | (swu_switches[1] << 4),
                    swu_switches[2] | (swu_switches[3] << 4),
                    swu_switches[4],
                    0, 0, 0, 0, 0  # Reserved
                ])
                
            elif msg_id == 911:  # PDU_Faults (new in H20)
                # Randomly trigger/clear faults
                if random.random() < 0.02:  # 2% chance to change fault status
                    fault_bit = 1 << random.randint(0, 22)  # 23 fault bits in total
                    pdu_faults ^= fault_bit  # Toggle the bit
                
                # Pack fault bits into message (3 bytes needed for 23 bits)
                data = bytearray([
                    pdu_faults & 0xFF,
                    (pdu_faults >> 8) & 0xFF,
                    (pdu_faults >> 16) & 0xFF,
                    0, 0, 0, 0, 0  # Padding
                ])
                
            elif msg_id == 1088:  # DTU_ErrorCode (new in H20)
                # Rarely trigger a DTU error
                if random.random() < 0.01:  # 1% chance
                    error_code = random.randint(0, 42)
                else:
                    error_code = 0  # No error
                    
                data = bytearray([error_code, 0, 0, 0, 0, 0, 0, 0])
            
            # [Other message handlers remain the same]
            
            # Create CAN message
            message = can.Message(
                arbitration_id=msg_id,
                data=data,
                is_extended_id=False,
                timestamp=time.time()
            )
            
            # Process the message
            self.process_message(message)
            
            # Sleep for a random time
            time.sleep(random.uniform(0.05, 0.2))

    def setup_threadsafe_bus(self):
        """
        Attempt to create a ThreadSafeBus. If it fails, we return None and log a warning.
        """
        try:
            # Try to connect to the primary CAN bus
            bus = can.ThreadSafeBus(channel="can0", bustype="socketcan", bitrate=1000000)
            logger.info("ThreadSafeBus (can0) initialized successfully.")
            return bus
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to create ThreadSafeBus on can0: {e}")
            
            # Try fallback to virtual CAN for development/testing
            try:
                bus = can.ThreadSafeBus(channel="vcan0", bustype="socketcan")
                logger.info("ThreadSafeBus (vcan0) initialized successfully.")
                return bus
            except Exception as e2:
                logger.warning(f"Failed to create virtual CAN bus: {e2}")
                logger.info("Running in view-only mode with no CAN bus.")
                return None

    def update_tree(self):
        """
        Refresh the Treeview with current message data, applying any filters.
        """
        # Clear existing entries
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Get filter values
        id_filter = self.id_filter.get().strip().lower()
        signal_filter = self.signal_filter.get().strip().lower()
        
        # Insert filtered messages and their signals
        row_count = 0
        for msg_id, signals in self.msg_data.items():
            # Convert message ID to hex for display
            hex_id = hex(msg_id) if isinstance(msg_id, int) else str(msg_id)
            
            # Check if the message ID matches the filter
            if id_filter and id_filter not in hex_id.lower():
                continue
                
            for signal_name, signal_info in signals.items():
                # Extract signal value and unit
                signal_value = signal_info.get('value', 'N/A')
                signal_unit = signal_info.get('unit', '')
                signal_time = signal_info.get('time', 'N/A')
                
                # Check if the signal name matches the filter
                if signal_filter and signal_filter not in signal_name.lower():
                    continue
                    
                # Insert the item
                self.tree.insert("", "end", values=(hex_id, signal_name, signal_value, signal_unit, signal_time))
                row_count += 1
        
        # Update status bar
        self.status_bar.config(text=f"Showing {row_count} signals from {len(self.msg_data)} message IDs")

    def process_message(self, msg):
        """Process a CAN message, update the display and dispatch to callbacks"""
        if not self.db:
            return
            
        try:
            # Try to decode the message
            decoded = decode_message(self.db, msg)
            if decoded:
                # Get current time for timestamp
                import datetime
                current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                # Store/Update decoded signal values
                if msg.arbitration_id not in self.msg_data:
                    self.msg_data[msg.arbitration_id] = {}
                    
                for signal_name, value in decoded.items():
                    # Try to get signal unit
                    unit = ""
                    try:
                        signal = self.db.get_message_by_frame_id(msg.arbitration_id).get_signal_by_name(signal_name)
                        unit = signal.unit if hasattr(signal, 'unit') else ""
                    except:
                        pass
                        
                    # Store value with metadata
                    self.msg_data[msg.arbitration_id][signal_name] = {
                        'value': value,
                        'unit': unit,
                        'time': current_time
                    }
                
                # Dispatch events for callbacks
                self.dispatcher.dispatch(msg.arbitration_id, decoded)
                
            else:
                # Store raw message data if decoding failed
                if msg.arbitration_id not in self.msg_data:
                    self.msg_data[msg.arbitration_id] = {}
                    
                self.msg_data[msg.arbitration_id]["RAW_DATA"] = {
                    'value': ' '.join(f'{b:02X}' for b in msg.data),
                    'unit': "",
                    'time': datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                }
        except Exception as e:
            logger.error(f"Error processing message: {e}")
                
        # Update the tree view
        self.update_tree()
    def receive_messages(self):
        """
        Periodically receive CAN messages (if bus is available),
        decode them, update the table, and dispatch events.
        """
        if not self.running:
            return

        if self.bus:
            try:
                message = self.bus.recv(timeout=0.1)
                if message:
                    self.process_message(message)
            except Exception as e:
                logger.error(f"Error receiving message: {e}")

        # Schedule the next reception
        self.root.after(100, self.receive_messages)

    def stop(self):
        """
        Stop receiving messages and shut down the CAN bus if available.
        """
        self.running = False
        self.sim_running = False
        
        if hasattr(self, 'sim_thread') and self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=0.5)
            
        if self.bus:
            try:
                self.bus.shutdown()
            except:
                pass
                
        self.root.destroy()