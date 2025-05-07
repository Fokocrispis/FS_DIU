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
    def __init__(self, arbitration_id=0xC0FFEE, data=None, is_extended_id=True, dbc_path="H19_CAN_dbc.dbc"):
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
    def __init__(self, root, controller, dbc_path="H19_CAN_dbc.dbc"):
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
        
        # === Event Selection Buttons (DIU_Driving_Mode_Request) ===
        self.dispatcher.register_callback(
            690, "DIU_Driving_Mode_Request_Skidpad",
            lambda value: self.controller.change_event("skidpad") if value == 1 else None
        )
        self.dispatcher.register_callback(
            690, "DIU_Driving_Mode_Request_Accel",
            lambda value: self.controller.change_event("acceleration") if value == 1 else None
        )
        self.dispatcher.register_callback(
            690, "DIU_Driving_Mode_Request_AutoX",
            lambda value: self.controller.change_event("autocross") if value == 1 else None
        )
        self.dispatcher.register_callback(
            690, "DIU_Driving_Mode_Request_Endu",
            lambda value: self.controller.change_event("endurance") if value == 1 else None
        )
        
        # === AMS Cell Voltages (for lowest cell voltage determination) ===
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
        
        # === Battery/Accumulator Temperature ===
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
        
        # === Inverter Temperatures ===
        self.dispatcher.register_callback(
            933, "VCU_Temperature_inverter_air",
            lambda value: self.controller.update_value("Inverter Temp", value)
        )
        # For separate left/right inverter temperatures
        self.dispatcher.register_callback(
            933, "VCU_Temperatures_inverter_igbt",
            lambda value: self.controller.update_value("Inverter L Temp", value)
        )
        # We're using the same source for both L/R in this example - in real application, they might have separate signals
        self.dispatcher.register_callback(
            933, "VCU_Temperatures_inverter_igbt",
            lambda value: self.controller.update_value("Inverter R Temp", value)
        )
        
        # === Motor Temperature ===
        self.dispatcher.register_callback(
            933, "VCU_Temperature_motor",
            lambda value: self.controller.update_value("Motor Temp", value)
        )
        # For separate left/right motor temperatures
        self.dispatcher.register_callback(
            933, "VCU_Temperature_motor",
            lambda value: self.controller.update_value("Motor L Temp", value)
        )
        self.dispatcher.register_callback(
            933, "VCU_Temperature_motor",
            lambda value: self.controller.update_value("Motor R Temp", value)
        )
        
        # === Traction Control, Torque Vectoring, and DRS Mode Signals ===
        self.dispatcher.register_callback(
            948, "VCU_Slip_Control_P",
            lambda value: self.controller.update_value("TC", 5)  # Default value
        )
        
        self.dispatcher.register_callback(
            949, "VCU_Slip_Control_D",
            lambda value: self.controller.update_value("TV", 2)  # Default value
        )
        
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
        
        # === Menu Control ===
        self.dispatcher.register_callback(
            696, "DIU_Menu_open",
            lambda value: self.controller.menu_toggle() if value == 1 else None
        )
        
        # DIU_Button_States (ID: 688) signals for steering wheel buttons
        self.dispatcher.register_callback(
            688, "DIU_Button_1_Menu",
            lambda value: self.controller.menu_toggle() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_2_OK",
            lambda value: self.controller.handle_ok_button() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_3_Cooling",
            lambda value: self.controller.toggle_cooling() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_4_Overall_Reset",
            lambda value: self.controller.perform_reset() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_5_TS_On",
            lambda value: self.controller.toggle_ts() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_6_R2D",
            lambda value: self.controller.toggle_r2d() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_6_9_Down_RadioActive",
            lambda value: self.controller.handle_down_button() if value == 1 else None
        )
        
        self.dispatcher.register_callback(
            688, "DIU_Button_8_Up_DRS",
            lambda value: self.controller.handle_up_button() if value == 1 else None
        )
    
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
            819,    # AMS_Cell_V_001_008
            835,    # AMS_Temp_001_008
            933,    # VCU_Temperatures
            936,    # VCU_Requested_Torque_Percentage
            1001,   # ASPU_Vehicle_Data
            1076    # MCU_DRS_Telemetry_3
        ]
        
        # Simulation state
        soc = 100.0  # Start with full battery
        cell_voltages = [4.2] * 128  # 128 cells at 4.2V
        temperatures = [25.0] * 48  # 48 temperature sensors at 25°C
        motor_temp = 25.0
        inverter_temp = 25.0
        speed = 0.0
        drs_position = 0  # 0 = Off, 1 = On
        
        while self.sim_running:
            # Randomly pick a message to update
            msg_id = random.choice(message_ids)
            
            # Create data based on message ID
            if msg_id == 579:  # AMS_SOC
                # Slowly decrease SOC
                soc = max(0, soc - random.uniform(0, 0.1))
                data = bytearray([int(soc), 0, 0, 0, 0, 0, 0, 0])
                
            elif msg_id in range(819, 835):  # AMS_Cell_V messages
                # Randomly update a cell voltage
                cell_idx = random.randint(0, 127)
                cell_voltages[cell_idx] = max(3.0, min(4.2, cell_voltages[cell_idx] + random.uniform(-0.01, 0.01)))
                
                # Calculate local index within this message
                message_offset = (msg_id - 819) * 8
                local_idxs = [i for i in range(8) if (message_offset + i) < 128]
                
                # Create message with 8 cell voltages
                data = bytearray()
                for idx in local_idxs:
                    # Convert voltage to the format expected by the DBC
                    # Assuming format is (value - 2.5) / 0.01 to fit in a byte
                    v = cell_voltages[message_offset + idx]
                    v_byte = int((v - 2.5) / 0.01)
                    data.append(v_byte & 0xFF)
                
                # Pad to 8 bytes if needed
                while len(data) < 8:
                    data.append(0)
                    
            elif msg_id in range(835, 841):  # AMS_Temp messages
                # Randomly update a temperature
                temp_idx = random.randint(0, 47)
                temperatures[temp_idx] = min(60, max(20, temperatures[temp_idx] + random.uniform(-0.5, 0.5)))
                
                # Calculate local index within this message
                message_offset = (msg_id - 835) * 8
                local_idxs = [i for i in range(8) if (message_offset + i) < 48]
                
                # Create message with 8 temperatures
                data = bytearray()
                for idx in local_idxs:
                    # Convert temperature to the format expected by the DBC
                    t = temperatures[message_offset + idx]
                    data.append(int(t) & 0xFF)
                
                # Pad to 8 bytes if needed
                while len(data) < 8:
                    data.append(0)
                    
            elif msg_id == 933:  # VCU_Temperatures
                # Update motor and inverter temperatures
                motor_temp = min(90, max(20, motor_temp + random.uniform(-0.5, 0.5)))
                inverter_temp = min(80, max(20, inverter_temp + random.uniform(-0.5, 0.5)))
                
                # Pack temperatures into message
                # Assuming format: [inverter_air, 0, motor_temp, 0, inverter_igbt, 0, 0, 0]
                data = bytearray([
                    int(inverter_temp) & 0xFF, 0,
                    int(motor_temp) & 0xFF, 0,
                    int(inverter_temp) & 0xFF, 0, 0, 0
                ])
                
            elif msg_id == 936:  # VCU_Requested_Torque_Percentage
                # Simulate max torque setting
                max_torque = 100  # Fixed at 100 Nm for simulation
                data = bytearray([0, 0, 0, 0, max_torque & 0xFF, (max_torque >> 8) & 0xFF, 0, 0])
                
            elif msg_id == 1001:  # ASPU_Vehicle_Data
                # Update speed with slight variations
                speed = max(0, min(200, speed + random.uniform(-5, 5)))
                speed_kmh100 = int(speed * 100)  # Convert to km/h * 100
                
                # Pack speed into message (first 2 bytes)
                data = bytearray([
                    speed_kmh100 & 0xFF,
                    (speed_kmh100 >> 8) & 0xFF,
                    0, 0, 0, 0, 0, 0
                ])
                
            elif msg_id == 1076:  # MCU_DRS_Telemetry_3
                # Toggle DRS state occasionally
                if random.random() < 0.1:  # 10% chance to change state
                    drs_position = 1 if drs_position == 0 else 0
                
                # Pack DRS position into message
                data = bytearray([0, 0, 0, 0, drs_position & 0x03, 0, 0, 0])
                
            else:
                # Default: random data
                data = bytearray([random.randint(0, 255) for _ in range(8)])
            
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