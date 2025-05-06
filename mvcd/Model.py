import can
import cantools
import logging

logging.basicConfig(level=logging.INFO)

class Model:
    """
    Exposes 'process_can_message(msg)' if the controller/GUI wants to feed
    incoming CAN messages to the model for decoding and value updates.
    """
    def __init__(self, can_bus=None, dbc_path="H19_CAN_dbc.dbc"):
        # Default initial values
        self.values = {
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
            "TC" : 5,
            "Traction Control Mode" : 0,
            "TV" : 2,
            "Torque Vectoring Mode" : 0,
            "DRS" : "On"
        }

        # Optional units for display
        self.units = {
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
        }


        # Screens for different events
        self.event_screens = {
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
            "TS Off Screen": [
                
            ]
        }

        self.current_event = "autocross"

        # Callbacks for when a value changes or an event changes
        self.value_changed_callbacks = []
        self.event_changed_callbacks = []

        # Mapping of message names to ID ranges (if you use them for fallback)
        self.message_id = {
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

        self.can_bus = can_bus if can_bus else self.setup_can_bus()

        self.dbc_path = dbc_path
        self.db = self.load_dbc_file(self.dbc_path)

    def load_dbc_file(self, path):
        """
        Load a DBC file using cantools.
        """
        try:
            db = cantools.database.load_file(path)
            logging.info(f"DBC file loaded successfully: {path}")
            return db
        except Exception as e:
            logging.error(f"Error loading DBC file '{path}': {e}")
            return None

    def setup_can_bus(self):
        """
        Default bus setup (vcan0 in this example).
        Adjust channel / bustype / bitrate as needed for real hardware.
        """
        try:
            c = can.Bus(channel="vcan0", interface="socketcan")
            logging.info("CAN Bus initialized successfully on vcan0.")
            return c
        except OSError as e:
            logging.error(f"Failed to initialize CAN bus: {e}")
            return None

    def bind_value_changed(self, callback):
        """
        Register a function to be called whenever a model value is updated.
        """
        self.value_changed_callbacks.append(callback)

    def bind_event_changed(self, callback):
        """
        Register a function to be called whenever the current event changes.
        """
        self.event_changed_callbacks.append(callback)

    def update_value(self, key, value):
        """
        Update a single value in self.values and call any bound callbacks.
        """
        if key in self.values:
            self.values[key] = value
            for cb in self.value_changed_callbacks:
                cb(key, value)

    def change_event(self, event_name):
        """
        Change the 'current_event' context.
        """
        if event_name in self.event_screens:
            self.current_event = event_name
            for cb in self.event_changed_callbacks:
                cb(event_name)

    def get_values_for_event(self, event_name):
        """
        Return the list of values relevant for the given event (for UI display).
        """
        return self.event_screens.get(event_name, [])

    def get_unit(self, key):
        """
        Return the unit string for a given value key, or None if no unit is defined.
        """
        return self.units.get(key, None)

    def get_value(self, key):
        """
        Return the current stored value for the given key, or None if not found.
        """
        return self.values.get(key, None)

    def process_can_message(self, msg):
        """
        Decode a CAN message (if the DBC is loaded) and update model values
        accordingly..
        This method should be called by the controller/GUI whenever a new
        CAN frame is received.
        """
        if self.db:
            try:
                decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                for signal_name, value in decoded.items():
                    # Only update if it's a known model field
                    if signal_name in self.values:
                        self.update_value(signal_name, value)
            except Exception as e:
                logging.debug(f"DBC decode failed for ID {hex(msg.arbitration_id)}: {e}")
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

    def get_value_key_from_msg(self, msg):
        """
        Helper method to map a message ID to a known key if it falls within
        the defined ranges in self.message_id.
        """
        for key, (low_id, high_id) in self.message_id.items():
            if low_id <= msg.arbitration_id <= high_id:
                return key
        return None

    def send_can_message(self, arbitration_id, data):
        """
        Send a CAN message. Typically called by the controller or GUI.
        """
        if not self.can_bus:
            logging.error("CAN bus is not initialized. Cannot send message.")
            return

        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)
        try:
            self.can_bus.send(msg)
            logging.info(f"Message sent on CAN bus: {msg}")
        except can.CanError as e:
            logging.error(f"CAN send error: {e}")
