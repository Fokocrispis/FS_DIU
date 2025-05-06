import sys
import can
import cantools
import logging
import tkinter as tk
from tkinter import ttk

logging.basicConfig(level=logging.INFO)

def load_dbc_file(file_path):
    """
    Load a DBC file using cantools.
    Returns the loaded database or None if there was an error.
    """
    try:
        db = cantools.database.load_file(file_path)
        logging.info(f"DBC file loaded successfully: {file_path}")
        return db
    except Exception as e:
        logging.error(f"Error loading DBC file '{file_path}': {e}")
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
        logging.error(f"Error decoding message {hex(message.arbitration_id)}: {e}")
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

        # Load the DBC file (only needed if you want to decode in this class as well)
        self.db = load_dbc_file(dbc_path)

        # Attempt to initialize CAN bus
        self.bus = self.setup_can_bus()

    def setup_can_bus(self):
        """
        Create and return a can.Bus instance, or None if unavailable.
        On Windows (or other non-socketcan environments), this will likely fail
        unless you have a supported interface. We catch that and return None.
        """
        try:
            # If you're on Windows, this likely won't work unless you have an
            # appropriate driver (e.g., 'pcan', 'vector', etc.) installed.
            bus = can.Bus(channel="can0", bustype="socketcan", bitrate=1000000)
            logging.info("CAN Bus (can0) initialized successfully.")
            return bus
        except (OSError, ValueError) as e:
            logging.error(f"Failed to initialize CAN bus on can0: {e}")
            logging.info("Falling back to no-op CAN mode (no real bus).")
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
                logging.info(f"CAN message sent: {msg}")
            except can.CanError as e:
                logging.error(f"Error sending CAN message: {e}")
        else:
            logging.warning("No CAN bus available. Skipping send_message().")

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
                    callback(value)

class AllMsg:
    """
    GUI class to display messages in a secondary window and manage callbacks for certain signals.
    Periodically receives messages via root.after scheduling.
    If on Windows without a SocketCAN interface, 'bus' will be None and receive_messages() won't do anything.
    """
    def __init__(self, root, controller, dbc_path="H18_CAN_dbc.dbc"):
        self.root = root
        self.root.title("All Messages and Values")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        self.controller = controller
        self.running = True
        self.msg_data = {}  # Dictionary to store messages and their signals for display

        # Create a dispatcher instance to manage callbacks
        self.dispatcher = CANDispatcher()

        # Register callbacks for message 690 signals (example)
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
        
        """
        Callback for lowest cell voltage. Searches 127 cells and registers smallest value.
        """
        for msg_id in range(819, 835):
            message_offset = (msg_id - 819) * 8

            # Each message has 8 signals
            for local_idx in range(8):
                # The global cell index across all messages (0..119)
                global_cell_idx = message_offset + local_idx

                signal_name = f"AMS_Cell_V_{global_cell_idx:03d}"

                self.dispatcher.register_callback(
                    msg_id,
                    signal_name,
                    # Pass global_cell_idx into the callback
                    lambda value, cidx=global_cell_idx: self.controller._on_cell_voltage_update(cidx, value)
        )
                
        """
        Callback for AMS percentage
        """
        self.dispatcher.register_callback(
            579, "AMS_SOC_percentage",
            lambda value: self.controller.update_value("SOC", value)
        )
        
        """
        Callback for menu control
        """
        self.dispatcher.register_callback(
            696, "DIU_Menu_open",
            lambda value: self.controller.menu_toggle() if value == 1 else None
        )


        # Create a Treeview to display signals
        self.tree = ttk.Treeview(root, columns=("Message", "Signal", "Value"), show="headings")
        self.tree.heading("Message", text="ID")
        self.tree.heading("Signal", text="Signal")
        self.tree.heading("Value", text="Value")
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Attempt to create a ThreadSafeBus (may fail on Windows w/o a suitable interface)
        self.db = load_dbc_file(dbc_path)
        self.bus = self.setup_threadsafe_bus()

        # Schedule message reception every 100 ms
        self.root.after(100, self.receive_messages)

    def setup_threadsafe_bus(self):
        """
        Attempt to create a ThreadSafeBus. If it fails, we return None and log a warning.
        """
        try:
            bus = can.ThreadSafeBus(channel="can0", bustype="socketcan", bitrate=1000000)
            logging.info("ThreadSafeBus (can0) initialized successfully.")
            return bus
        except (OSError, ValueError) as e:
            logging.warning(f"Failed to create ThreadSafeBus on can0: {e}")
            logging.info("Running in no-op mode on Windows or unsupported environment.")
            return None

    def update_tree(self):
        """
        Refresh the Treeview with current message data.
        """
        # Clear existing entries
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Insert all stored messages and their signals
        for msg_id, signals in self.msg_data.items():
            for signal_name, signal_value in signals.items():
                self.tree.insert("", "end", values=(hex(msg_id), signal_name, signal_value))

    def receive_messages(self):
        """
        Periodically receive CAN messages (if bus is available),
        decode them, update the table, and dispatch events.
        """
        if not self.running:
            return

        if self.bus and self.db:
            try:
                message = self.bus.recv(timeout=0.1)
                if message:
                    decoded = decode_message(self.db, message)
                    if decoded:
                        # Store/Update decoded signal values
                        if message.arbitration_id not in self.msg_data:
                            self.msg_data[message.arbitration_id] = {}
                        for signal, value in decoded.items():
                            self.msg_data[message.arbitration_id][signal] = value

                        # Update the display
                        self.update_tree()

                        # Dispatch events for callbacks
                        self.dispatcher.dispatch(message.arbitration_id, decoded)
            except Exception as e:
                logging.error(f"Error receiving message: {e}")

        # Schedule the next reception
        self.root.after(100, self.receive_messages)

    def stop(self):
        """
        Stop receiving messages and shut down the CAN bus if available.
        """
        self.running = False
        if self.bus:
            self.bus.shutdown()
        self.root.destroy()
