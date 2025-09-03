import can
import cantools
import logging
import threading
import time
import os
import random
from typing import Dict, List, Optional, Callable, Any, Tuple, Union

# Configure logging
logger = logging.getLogger(__name__)

class CANUtils:
    """
    Utility class for working with CAN bus messages.
    
    Provides:
    - Functions for setting up CAN interfaces
    - Message sending/receiving helpers
    - Simulation mode for development
    - DBC file handling
    - ID filtering
    
    This separates CAN-specific functionality from the Model class.
    """
    
    def __init__(self, config=None):
        """
        Initialize CAN utilities.
        
        Args:
            config: Configuration object (optional)
        """
        self.config = config
        self.bus = None
        self.db = None
        self.notifier = None
        self.callbacks = []
        self.simulation_running = False
        self.simulation_thread = None
        
        # Load settings from config or use defaults
        if config:
            self.interface = config.get('can', 'interface', 'socketcan')
            self.channel = config.get('can', 'channel', 'can0')
            self.bitrate = config.get('can', 'bitrate', 1000000)
            self.dbc_file = config.get('can', 'dbc_file', 'H19_CAN_dbc.dbc')
            self.use_virtual = config.get('can', 'use_virtual', False)
        else:
            self.interface = 'socketcan'
            self.channel = 'can0'
            self.bitrate = 1000000
            self.dbc_file = 'H19_CAN_dbc.dbc'
            self.use_virtual = False
        
    def setup(self) -> bool:
        """
        Set up CAN bus and load DBC file.
        
        Returns:
            True if setup successful, False otherwise
        """
        success = self.setup_can_bus()
        if success:
            success = self.load_dbc_file(self.dbc_file)
        return success
    
    def setup_can_bus(self) -> bool:
        """
        Set up CAN bus interface.
        
        Returns:
            True if successful, False otherwise
        """
        # Clean up any existing bus
        if self.bus:
            try:
                self.bus.shutdown()
            except:
                pass
        
        # Try to connect to primary bus first
        if not self.use_virtual:
            try:
                self.bus = can.Bus(channel=self.channel, interface=self.interface, bitrate=self.bitrate)
                logger.info(f"CAN bus initialized successfully on {self.channel}")
                return True
            except Exception as e:
                logger.warning(f"Failed to initialize CAN bus on {self.channel}: {e}")
                # Fall back to virtual bus if requested
                if self.use_virtual:
                    logger.info("Falling back to virtual CAN bus")
                else:
                    logger.error("CAN bus initialization failed and virtual mode not enabled")
                    return False
        
        # Try virtual bus (vcan0)
        try:
            self.bus = can.Bus(channel='vcan0', interface='socketcan')
            logger.info("CAN bus initialized successfully on vcan0 (virtual)")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize virtual CAN bus: {e}")
            return False
    
    def load_dbc_file(self, dbc_path: str) -> bool:
        """
        Load DBC file for message decoding.
        
        Args:
            dbc_path: Path to DBC file
            
        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(dbc_path):
            logger.error(f"DBC file not found: {dbc_path}")
            return False
            
        try:
            self.db = cantools.database.load_file(dbc_path)
            logger.info(f"DBC file loaded successfully: {dbc_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading DBC file: {e}")
            return False
    
    def start_listener(self, callback: Callable[[can.Message], None]) -> bool:
        """
        Start CAN message listener.
        
        Args:
            callback: Function to call when message is received
            
        Returns:
            True if successful, False otherwise
        """
        if not self.bus:
            logger.error("Cannot start listener: CAN bus not initialized")
            return False
            
        self.callbacks.append(callback)
        
        try:
            if self.notifier:
                # Stop existing notifier
                self.notifier.stop()
                
            # Create new notifier
            self.notifier = can.Notifier(self.bus, [self._callback_wrapper])
            logger.info("CAN message listener started")
            return True
        except Exception as e:
            logger.error(f"Error starting CAN message listener: {e}")
            return False
    
    def _callback_wrapper(self, msg: can.Message):
        """
        Wrapper for callbacks to handle exceptions.
        
        Args:
            msg: CAN message
        """
        for callback in self.callbacks:
            try:
                callback(msg)
            except Exception as e:
                logger.error(f"Error in CAN message callback: {e}")
    
    def stop_listener(self) -> bool:
        """
        Stop CAN message listener.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.notifier:
            logger.warning("Cannot stop listener: No active notifier")
            return False
            
        try:
            self.notifier.stop()
            self.notifier = None
            logger.info("CAN message listener stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping CAN message listener: {e}")
            return False
    
    def send_message(self, arbitration_id: int, data: List[int],
                     is_extended_id: bool = False) -> bool:
        """
        Send CAN message.
        
        Args:
            arbitration_id: CAN message ID
            data: CAN message data (list of bytes)
            is_extended_id: Whether to use extended ID format
            
        Returns:
            True if successful, False otherwise
        """
        if not self.bus:
            logger.error("Cannot send message: CAN bus not initialized")
            return False
            
        try:
            msg = can.Message(
                arbitration_id=arbitration_id,
                data=data,
                is_extended_id=is_extended_id
            )
            self.bus.send(msg)
            logger.debug(f"CAN message sent: {msg}")
            return True
        except Exception as e:
            logger.error(f"Error sending CAN message: {e}")
            return False
    
    def decode_message(self, msg: can.Message) -> Optional[Dict[str, Any]]:
        """
        Decode CAN message using DBC file.
        
        Args:
            msg: CAN message to decode
            
        Returns:
            Dictionary of signal names and values, or None if decoding failed
        """
        if not self.db:
            logger.debug("Cannot decode message: No DBC file loaded")
            return None
            
        try:
            decoded = self.db.decode_message(msg.arbitration_id, msg.data)
            return decoded
        except Exception as e:
            logger.debug(f"Error decoding CAN message: {e}")
            return None
    
    def encode_message(self, message_name: str, data: Dict[str, Any]) -> Optional[Tuple[int, bytes]]:
        """
        Encode data into CAN message using DBC file.
        
        Args:
            message_name: Name of message in DBC file
            data: Dictionary of signal names and values
            
        Returns:
            Tuple of (arbitration_id, data) or None if encoding failed
        """
        if not self.db:
            logger.error("Cannot encode message: No DBC file loaded")
            return None
            
        try:
            message = self.db.get_message_by_name(message_name)
            encoded_data = message.encode(data)
            return (message.frame_id, encoded_data)
        except Exception as e:
            logger.error(f"Error encoding CAN message: {e}")
            return None
    
    def send_encoded_message(self, message_name: str, data: Dict[str, Any],
                            is_extended_id: bool = False) -> bool:
        """
        Encode and send CAN message.
        
        Args:
            message_name: Name of message in DBC file
            data: Dictionary of signal names and values
            is_extended_id: Whether to use extended ID format
            
        Returns:
            True if successful, False otherwise
        """
        encoded = self.encode_message(message_name, data)
        if not encoded:
            return False
            
        arbitration_id, encoded_data = encoded
        return self.send_message(arbitration_id, encoded_data, is_extended_id)
    
    def start_simulation(self, callback: Callable[[can.Message], None],
                        message_rate_hz: float = 10.0) -> bool:
        """
        Start CAN message simulation for testing.
        
        Args:
            callback: Function to call with simulated messages
            message_rate_hz: Rate of message generation in Hz
            
        Returns:
            True if successful, False otherwise
        """
        if self.simulation_running:
            logger.warning("Simulation already running")
            return False
            
        self.simulation_running = True
        self.callbacks.append(callback)
        
        # Start simulation thread
        self.simulation_thread = threading.Thread(
            target=self._simulation_loop,
            args=(message_rate_hz,),
            daemon=True
        )
        self.simulation_thread.start()
        
        logger.info("CAN message simulation started")
        return True
    
    def stop_simulation(self) -> bool:
        """
        Stop CAN message simulation.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.simulation_running:
            logger.warning("Simulation not running")
            return False
            
        self.simulation_running = False
        
        # Wait for simulation thread to stop
        if self.simulation_thread and self.simulation_thread.is_alive():
            self.simulation_thread.join(timeout=1.0)
            
        logger.info("CAN message simulation stopped")
        return True
    
    def _simulation_loop(self, message_rate_hz: float):
        """
        Simulation loop that generates random CAN messages.
        
        Args:
            message_rate_hz: Rate of message generation in Hz
        """
        # Message IDs to simulate (based on DBC file)
        message_ids = [
            0x330,  # AMS
            0x3A0,  # VCU
            0x3E0,  # ASPU
            0x420,  # DIU
            0x431,  # DRS
            0x440,  # DTU
            0x450,  # SN1
            0x490,  # SN2
            0x4D0   # Kistler
        ]
        
        # State variables for simulation
        soc = 100.0  # Battery state of charge
        cell_voltages = [4.2] * 128  # 128 cells at 4.2V
        temps = [25.0] * 48  # 48 temperature sensors
        motor_temp = 30.0
        inverter_temp = 25.0
        speed = 0.0
        drs_state = 0  # 0 = off, 1 = on
        tc_mode = 5  # Default TC mode (Auto)
        tv_mode = 2  # Default TV mode (Medium)
        
        # Map of message ID to simulated data generator
        data_generators = {
            0x330: lambda: self._generate_ams_data(soc),
            0x3A0: lambda: self._generate_vcu_data(motor_temp, inverter_temp),
            0x3E0: lambda: self._generate_aspu_data(speed),
            0x420: lambda: self._generate_diu_data(),
            0x431: lambda: self._generate_drs_data(drs_state),
            0x440: lambda: self._generate_dtu_data(),
            0x450: lambda: self._generate_sn_data(),
            0x490: lambda: self._generate_sn_data(),
            0x4D0: lambda: self._generate_kistler_data(speed)
        }
        
        # Sleep time between messages
        sleep_time = 1.0 / message_rate_hz
        sim_time = 0.0  # Simulation time in seconds
        
        while self.simulation_running:
            # Update simulation state
            sim_time += sleep_time
            
            # Slowly discharge battery (faster under acceleration)
            discharge_rate = 0.01 * (1.0 + speed / 50.0)
            soc = max(0.0, soc - discharge_rate * sleep_time)
            
            # Randomly update a cell voltage
            cell_idx = random.randint(0, 127)
            # Voltage decreases with SOC
            target_voltage = 3.0 + (4.2 - 3.0) * (soc / 100.0)
            # Add some random variation
            cell_voltages[cell_idx] = target_voltage + random.uniform(-0.1, 0.1)
            
            # Update temperatures based on speed
            heat_factor = 1.0 + (speed / 30.0)
            motor_temp = min(90.0, motor_temp + heat_factor * random.uniform(-0.1, 0.2))
            inverter_temp = min(80.0, inverter_temp + heat_factor * random.uniform(-0.1, 0.2))
            
            # Randomly update a temperature sensor
            temp_idx = random.randint(0, 47)
            temps[temp_idx] = min(60.0, temps[temp_idx] + heat_factor * random.uniform(-0.2, 0.3))
            
            # Update speed with some randomness
            if random.random() < 0.1:  # 10% chance to change speed significantly
                speed_change = random.uniform(-10.0, 15.0)
            else:
                speed_change = random.uniform(-2.0, 3.0)
            speed = max(0.0, min(200.0, speed + speed_change))
            
            # Toggle DRS state occasionally
            if random.random() < 0.05:  # 5% chance to change state
                drs_state = 1 if drs_state == 0 else 0
            
            # Randomly select a message ID
            msg_id = random.choice(message_ids)
            
            # Generate data for the message
            if msg_id in data_generators:
                data = data_generators[msg_id]()
            else:
                # Default: random data
                data = [random.randint(0, 255) for _ in range(8)]
            
            # Create and send message
            msg = can.Message(
                arbitration_id=msg_id,
                data=data,
                is_extended_id=False,
                timestamp=time.time()
            )
            
            # Call all callbacks
            self._callback_wrapper(msg)
            
            # Sleep before next message
            time.sleep(sleep_time)
    
    def _generate_ams_data(self, soc: float) -> List[int]:
        """
        Generate simulated AMS data.
        
        Args:
            soc: Battery state of charge
            
        Returns:
            List of bytes for CAN message
        """
        # Format for AMS_SOC message (ID 579):
        # - Byte 0: SOC percentage (0-100)
        # - Byte 1: SOC percentage from voltage
        # - Bytes 2-5: Wh since last calibration (32-bit)
        data = [
            int(soc),  # SOC percentage
            int(soc),  # SOC percentage from voltage
            0, 0, 0, 0,  # Wh since last calibration (0)
            0, 0  # Padding
        ]
        return data
    
    def _generate_vcu_data(self, motor_temp: float, inverter_temp: float) -> List[int]:
        """
        Generate simulated VCU data.
        
        Args:
            motor_temp: Motor temperature
            inverter_temp: Inverter temperature
            
        Returns:
            List of bytes for CAN message
        """
        # Format for VCU_Temperatures message (ID 933):
        # - Bytes 0-1: Inverter air temperature (16-bit)
        # - Bytes 2-3: Motor temperature (16-bit)
        # - Bytes 4-5: Inverter IGBT temperature (16-bit)
        motor_temp_int = int(motor_temp)
        inverter_temp_int = int(inverter_temp)
        data = [
            inverter_temp_int & 0xFF, (inverter_temp_int >> 8) & 0xFF,  # Inverter air temp
            motor_temp_int & 0xFF, (motor_temp_int >> 8) & 0xFF,  # Motor temp
            inverter_temp_int & 0xFF, (inverter_temp_int >> 8) & 0xFF,  # Inverter IGBT temp
            0, 0  # Padding
        ]
        return data
    
    def _generate_aspu_data(self, speed: float) -> List[int]:
        """
        Generate simulated ASPU data.
        
        Args:
            speed: Vehicle speed in km/h
            
        Returns:
            List of bytes for CAN message
        """
        # Format for ASPU_Vehicle_Data message (ID 1001):
        # - Bytes 0-1: Speed in km/h * 100 (16-bit)
        # - Bytes 2-5: Mission distance in mm (32-bit)
        speed_int = int(speed * 100)  # Convert to km/h * 100
        distance = int(speed * 1000)  # Simple distance calculation in mm
        
        data = [
            speed_int & 0xFF, (speed_int >> 8) & 0xFF,  # Speed
            distance & 0xFF, (distance >> 8) & 0xFF,  # Distance (low bytes)
            (distance >> 16) & 0xFF, (distance >> 24) & 0xFF,  # Distance (high bytes)
            0, 0  # Padding
        ]
        return data
    
    def _generate_diu_data(self) -> List[int]:
        """
        Generate simulated DIU data.
        
        Returns:
            List of bytes for CAN message
        """
        # Format for DIU_Menu_Control message (ID 696):
        # - Bit 0: Menu open flag
        data = [
            random.randint(0, 1),  # Randomly toggle menu state
            0, 0, 0, 0, 0, 0, 0  # Padding
        ]
        return data
    
    def _generate_drs_data(self, drs_state: int) -> List[int]:
        """
        Generate simulated DRS data.
        
        Args:
            drs_state: DRS state (0 = off, 1 = on)
            
        Returns:
            List of bytes for CAN message
        """
        # Format for MCU_DRS_DIU_Information message (ID 705):
        # - Bits 0-1: Position state
        # - Bits 2-5: FSM mode selection state
        # - Bits 6-13: Temperature
        position = drs_state & 0x03
        fsm_mode = random.randint(0, 15) & 0x0F
        temperature = random.randint(20, 50) & 0xFF
        
        data = [
            position | (fsm_mode << 2),  # Position and FSM mode
            temperature,  # Temperature
            0, 0, 0, 0, 0, 0  # Padding
        ]
        return data
    
    def _generate_dtu_data(self) -> List[int]:
        """
        Generate simulated DTU data.
        
        Returns:
            List of bytes for CAN message
        """
        # No specific format for DTU messages, generate random data
        data = [random.randint(0, 255) for _ in range(8)]
        return data
    
    def _generate_sn_data(self) -> List[int]:
        """
        Generate simulated sensor node data.
        
        Returns:
            List of bytes for CAN message
        """
        # Format for SN1_Analog1 message (ID 1106):
        # - Bytes 0-3: ADC1 value (32-bit float)
        # - Bytes 4-7: ADC2 value (32-bit float)
        # Simple random value for now
        data = [random.randint(0, 255) for _ in range(8)]
        return data
    
    def _generate_kistler_data(self, speed: float) -> List[int]:
        """
        Generate simulated Kistler data.
        
        Args:
            speed: Vehicle speed in km/h
            
        Returns:
            List of bytes for CAN message
        """
        # Format for Kistler_DF1 message (ID 768):
        # - Bytes 0-1: Timestamp (16-bit)
        # - Bytes 2-3: Absolute velocity (16-bit)
        # - Bytes 4-7: Distance (32-bit)
        
        # Convert speed from km/h to m/s and multiply by 100 for fixed-point
        speed_ms = int((speed / 3.6) * 100)
        # Simple distance calculation
        distance = int(speed * 1000)  # in mm
        # Timestamp just increments
        timestamp = int(time.time() * 4) & 0xFFFF  # 0.25ms units
        
        data = [
            timestamp & 0xFF, (timestamp >> 8) & 0xFF,  # Timestamp
            speed_ms & 0xFF, (speed_ms >> 8) & 0xFF,  # Speed
            distance & 0xFF, (distance >> 8) & 0xFF,  # Distance (low bytes)
            (distance >> 16) & 0xFF, (distance >> 24) & 0xFF  # Distance (high bytes)
        ]
        return data
    
    def get_message_info(self, msg_id: int) -> Optional[Dict[str, Any]]:
        """
        Get information about a message from the DBC file.
        
        Args:
            msg_id: CAN message ID
            
        Returns:
            Dictionary with message information or None if not found
        """
        if not self.db:
            return None
            
        try:
            message = self.db.get_message_by_frame_id(msg_id)
            return {
                'name': message.name,
                'frame_id': message.frame_id,
                'is_extended_frame': message.is_extended_frame,
                'length': message.length,
                'signals': [signal.name for signal in message.signals],
                'comment': message.comment
            }
        except KeyError:
            return None
        except Exception as e:
            logger.error(f"Error getting message info: {e}")
            return None
    
    def get_signal_info(self, msg_id: int, signal_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a signal from the DBC file.
        
        Args:
            msg_id: CAN message ID
            signal_name: Signal name
            
        Returns:
            Dictionary with signal information or None if not found
        """
        if not self.db:
            return None
            
        try:
            message = self.db.get_message_by_frame_id(msg_id)
            signal = message.get_signal_by_name(signal_name)
            
            return {
                'name': signal.name,
                'start': signal.start,
                'length': signal.length,
                'byte_order': signal.byte_order,
                'is_signed': signal.is_signed,
                'scale': signal.scale,
                'offset': signal.offset,
                'minimum': signal.minimum,
                'maximum': signal.maximum,
                'unit': signal.unit,
                'is_multiplexer': signal.is_multiplexer,
                'multiplexer_ids': signal.multiplexer_ids,
                'comment': signal.comment
            }
        except (KeyError, AttributeError):
            return None
        except Exception as e:
            logger.error(f"Error getting signal info: {e}")
            return None

    def create_signal_map(self) -> Dict[str, List[Tuple[int, str]]]:
        """
        Create a mapping of parameter names to signal information.
        
        This is useful for automatically mapping model parameters to CAN signals.
        
        Returns:
            Dictionary mapping parameter names to list of (message_id, signal_name) tuples
        """
        if not self.db:
            return {}
            
        # Common parameter names and patterns to look for in signal names
        param_patterns = {
            'SOC': ['soc', 'state_of_charge'],
            'Lowest Cell': ['cell_v', 'min_cell', 'lowest_cell'],
            'Accu Temp': ['accu_temp', 'battery_temp', 'ams_temp'],
            'Motor Temp': ['motor_temp', 'motor_temperature'],
            'Inverter Temp': ['inverter_temp', 'inverter_temperature'],
            'Speed': ['speed', 'velocity'],
            'Max Torque': ['max_torque', 'torque_max'],
            'DRS': ['drs_', 'drag_reduction'],
            'TC': ['traction_control', 'tc_'],
            'TV': ['torque_vectoring', 'tv_']
        }
        
        # Create the mapping
        signal_map = {}
        
        try:
            # Iterate through all messages in the DBC file
            for message in self.db.messages:
                # Iterate through all signals in the message
                for signal in message.signals:
                    # Check if signal name matches any parameter pattern
                    for param, patterns in param_patterns.items():
                        signal_name_lower = signal.name.lower()
                        for pattern in patterns:
                            if pattern in signal_name_lower:
                                # Add to mapping
                                if param not in signal_map:
                                    signal_map[param] = []
                                signal_map[param].append((message.frame_id, signal.name))
                                break
        except Exception as e:
            logger.error(f"Error creating signal map: {e}")
        
        return signal_map

    def list_available_messages(self) -> List[Dict[str, Any]]:
        """
        Get a list of all available messages in the DBC file.
        
        Returns:
            List of dictionaries with message information
        """
        if not self.db:
            return []
            
        messages = []
        try:
            for message in self.db.messages:
                messages.append({
                    'name': message.name,
                    'frame_id': message.frame_id,
                    'is_extended_frame': message.is_extended_frame,
                    'length': message.length,
                    'signal_count': len(message.signals)
                })
        except Exception as e:
            logger.error(f"Error listing messages: {e}")
            
        return messages
    
    def list_signals_for_message(self, msg_id: int) -> List[Dict[str, Any]]:
        """
        Get a list of all signals for a specific message.
        
        Args:
            msg_id: CAN message ID
            
        Returns:
            List of dictionaries with signal information
        """
        if not self.db:
            return []
            
        signals = []
        try:
            message = self.db.get_message_by_frame_id(msg_id)
            for signal in message.signals:
                signals.append({
                    'name': signal.name,
                    'length': signal.length,
                    'scale': signal.scale,
                    'offset': signal.offset,
                    'unit': signal.unit
                })
        except Exception as e:
            logger.error(f"Error listing signals: {e}")
            
        return signals
    
    def record_messages(self, duration_seconds: float, filter_ids: List[int] = None) -> List[Dict[str, Any]]:
        """
        Record CAN messages for a specific duration.
        
        Args:
            duration_seconds: Duration to record in seconds
            filter_ids: List of message IDs to record (None = all)
            
        Returns:
            List of recorded messages
        """
        if not self.bus:
            logger.error("Cannot record messages: CAN bus not initialized")
            return []
            
        recorded_messages = []
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        logger.info(f"Recording CAN messages for {duration_seconds} seconds...")
        
        try:
            while time.time() < end_time:
                msg = self.bus.recv(timeout=0.1)
                if msg:
                    # Filter by ID if requested
                    if filter_ids is None or msg.arbitration_id in filter_ids:
                        # Try to decode the message
                        decoded = self.decode_message(msg)
                        
                        # Store the message data
                        recorded_message = {
                            'timestamp': msg.timestamp,
                            'arbitration_id': msg.arbitration_id,
                            'is_extended_id': msg.is_extended_id,
                            'data': [b for b in msg.data],
                            'decoded': decoded
                        }
                        recorded_messages.append(recorded_message)
        except Exception as e:
            logger.error(f"Error recording messages: {e}")
            
        logger.info(f"Recorded {len(recorded_messages)} messages")
        return recorded_messages
    
    def replay_messages(self, messages: List[Dict[str, Any]], speed_factor: float = 1.0) -> bool:
        """
        Replay recorded CAN messages.
        
        Args:
            messages: List of messages to replay
            speed_factor: Replay speed factor (1.0 = real-time)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.bus:
            logger.error("Cannot replay messages: CAN bus not initialized")
            return False
            
        if not messages:
            logger.warning("No messages to replay")
            return False
            
        logger.info(f"Replaying {len(messages)} messages at {speed_factor}x speed")
        
        try:
            # Sort messages by timestamp
            sorted_messages = sorted(messages, key=lambda m: m['timestamp'])
            
            # Get start time
            start_time = time.time()
            first_msg_time = sorted_messages[0]['timestamp']
            
            for i, message_dict in enumerate(sorted_messages):
                # Calculate delay
                if i > 0:
                    delay = (message_dict['timestamp'] - sorted_messages[i-1]['timestamp']) / speed_factor
                    time.sleep(max(0, delay))
                
                # Create CAN message
                msg = can.Message(
                    arbitration_id=message_dict['arbitration_id'],
                    data=bytearray(message_dict['data']),
                    is_extended_id=message_dict['is_extended_id'],
                    timestamp=time.time()
                )
                
                # Send message
                self.bus.send(msg)
                
            logger.info("Message replay completed")
            return True
        except Exception as e:
            logger.error(f"Error replaying messages: {e}")
            return False

    def export_messages_to_file(self, messages: List[Dict[str, Any]], filename: str) -> bool:
        """
        Export recorded messages to a file.
        
        Args:
            messages: List of messages to export
            filename: Name of file to export to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import json
            
            # Convert messages to JSON-serializable format
            serializable_messages = []
            for msg in messages:
                serializable_msg = {
                    'timestamp': msg['timestamp'],
                    'arbitration_id': msg['arbitration_id'],
                    'is_extended_id': msg['is_extended_id'],
                    'data': [b for b in msg['data']],
                }
                
                # Add decoded data if available
                if 'decoded' in msg and msg['decoded']:
                    serializable_msg['decoded'] = msg['decoded']
                    
                serializable_messages.append(serializable_msg)
            
            # Write to file
            with open(filename, 'w') as f:
                json.dump(serializable_messages, f, indent=2)
                
            logger.info(f"Exported {len(messages)} messages to {filename}")
            return True
        except Exception as e:
            logger.error(f"Error exporting messages: {e}")
            return False

    def import_messages_from_file(self, filename: str) -> List[Dict[str, Any]]:
        """
        Import messages from a file.
        
        Args:
            filename: Name of file to import from
            
        Returns:
            List of imported messages
        """
        try:
            import json
            
            with open(filename, 'r') as f:
                messages = json.load(f)
                
            # Convert data from lists to bytearrays
            for msg in messages:
                if 'data' in msg:
                    msg['data'] = bytearray(msg['data'])
                    
            logger.info(f"Imported {len(messages)} messages from {filename}")
            return messages
        except Exception as e:
            logger.error(f"Error importing messages: {e}")
            return []

    def monitor_bus_activity(self, duration_seconds: float) -> Dict[int, int]:
        """
        Monitor CAN bus activity and return message counts by ID.
        
        Args:
            duration_seconds: Duration to monitor in seconds
            
        Returns:
            Dictionary of message ID -> count
        """
        if not self.bus:
            logger.error("Cannot monitor bus: CAN bus not initialized")
            return {}
            
        message_counts = {}
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        logger.info(f"Monitoring CAN bus for {duration_seconds} seconds...")
        
        try:
            while time.time() < end_time:
                msg = self.bus.recv(timeout=0.1)
                if msg:
                    if msg.arbitration_id not in message_counts:
                        message_counts[msg.arbitration_id] = 0
                    message_counts[msg.arbitration_id] += 1
        except Exception as e:
            logger.error(f"Error monitoring bus: {e}")
            
        # Sort by message count (descending)
        sorted_counts = {k: v for k, v in sorted(
            message_counts.items(), 
            key=lambda item: item[1], 
            reverse=True
        )}
        
        logger.info(f"Detected {len(sorted_counts)} different message IDs")
        return sorted_counts

    def generate_test_message(self, msg_id: int, signal_values: Dict[str, Any] = None) -> Optional[can.Message]:
        """
        Generate a test message with the specified ID and signal values.
        
        Args:
            msg_id: CAN message ID
            signal_values: Dictionary of signal name -> value (optional)
            
        Returns:
            CAN message or None if generation failed
        """
        if not self.db:
            logger.error("Cannot generate test message: No DBC file loaded")
            return None
            
        try:
            # Get message from DBC
            message = self.db.get_message_by_frame_id(msg_id)
            
            # If no signal values provided, use defaults
            if signal_values is None:
                signal_values = {}
                for signal in message.signals:
                    # Use middle of signal range as default
                    if signal.minimum is not None and signal.maximum is not None:
                        default_value = (signal.minimum + signal.maximum) / 2
                    else:
                        # If no range defined, use a safe default
                        default_value = 0
                    signal_values[signal.name] = default_value
            
            # Encode the message
            data = message.encode(signal_values)
            
            # Create CAN message
            msg = can.Message(
                arbitration_id=msg_id,
                data=data,
                is_extended_id=message.is_extended_frame
            )
            
            return msg
        except Exception as e:
            logger.error(f"Error generating test message: {e}")
            return None

    def calculate_bus_load(self, duration_seconds: float) -> float:
        """
        Calculate CAN bus load as a percentage of maximum capacity.
        
        Args:
            duration_seconds: Duration to measure in seconds
            
        Returns:
            Bus load as a percentage (0-100)
        """
        if not self.bus:
            logger.error("Cannot calculate bus load: CAN bus not initialized")
            return 0.0
            
        # CAN bus capacity (bits per second)
        bus_capacity = self.bitrate
        
        # Monitor bus activity
        message_counts = self.monitor_bus_activity(duration_seconds)
        
        # Calculate total bits transmitted
        total_bits = 0
        for msg_id, count in message_counts.items():
            # Each CAN frame consists of:
            # - 1 start bit
            # - 11 or 29 bits for standard/extended ID
            # - 1 RTR bit
            # - 1 IDE bit
            # - 1 reserved bit
            # - 4 DLC bits
            # - 0-64 data bits (8 bytes maximum)
            # - 15 CRC bits
            # - 1 CRC delimiter
            # - 1 ACK bit
            # - 1 ACK delimiter
            # - 7 end of frame bits
            # Total: 44 + 8*8 = 108 bits for standard ID with 8 data bytes
            
            # Try to get message length from DBC
            try:
                message = self.db.get_message_by_frame_id(msg_id)
                data_length = message.length
                is_extended = message.is_extended_frame
            except:
                # Default to 8 bytes and standard ID if not found
                data_length = 8
                is_extended = False
                
            # Calculate frame size in bits
            id_bits = 29 if is_extended else 11
            overhead_bits = 1 + id_bits + 1 + 1 + 1 + 4 + 15 + 1 + 1 + 1 + 7
            data_bits = data_length * 8
            frame_bits = overhead_bits + data_bits
            
            # Add to total
            total_bits += frame_bits * count
            
        # Calculate bus load
        bus_load = (total_bits / duration_seconds) / bus_capacity * 100
        
        logger.info(f"Bus load: {bus_load:.2f}% ({total_bits} bits in {duration_seconds} seconds)")
        return bus_load

    def cleanup(self):
        """
        Clean up resources.
        """
        # Stop simulation if running
        if self.simulation_running:
            self.stop_simulation()
            
        # Stop listener if running
        if self.notifier:
            self.stop_listener()
            
        # Close CAN bus if open
        if self.bus:
            try:
                self.bus.shutdown()
                logger.info("CAN bus shut down cleanly")
            except Exception as e:
                logger.error(f"Error shutting down CAN bus: {e}")