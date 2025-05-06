import threading
import random
import logging
import can
import time

logging.basicConfig(level=logging.INFO)

class Controller:
    """
    The 'Controller' in an MVC architecture.
    - Binds model and view together.
    - Listens for user interactions (button/key press).
    - Receives CAN frames (via a background thread) and updates the model accordingly.
    - Manages menu navigation and screen transitions.
    """
    def __init__(self, model, view, can_bus=None):
        self.model = model
        self.view = view
        self.can_bus = can_bus or self.model.can_bus  # fallback to model's bus if not provided

        # Initialize state variables
        self.toggle_in_progress = False
        self.lockout_ms = 100  # Cooldown (milliseconds) before menu_toggle can trigger again
        self.cell_voltages = {}  # Dictionary to store per-cell voltage
        self.demo_mode = False
        self.demo_thread = None  # Initialize the demo thread reference
        
        # State tracking for traction control and torque vectoring modes
        self.tc_modes = ["Off", "Dry", "Wet", "Snow", "Custom", "Auto"]
        self.tv_modes = ["Off", "Low", "Medium", "High", "Custom"]
        self.current_tc_mode = 0  # Index in tc_modes
        self.current_tv_mode = 2  # Index in tv_modes (Medium)
        
        # Set initial TC and TV mode values
        self.update_value("Traction Control Mode", self.tc_modes[self.current_tc_mode])
        self.update_value("Torque Vectoring Mode", self.tv_modes[self.current_tv_mode])

        # Bind model callbacks to the view's update methods
        self.model.bind_value_changed(self.view.handle_value_update)
        self.model.bind_event_changed(self.view.create_event_screen)

        # Configure view button actions if they exist
        self.setup_button_actions()

        # Key bindings from the view
        self.view.bind("<Key>", self.handle_key_press)
        self.view.focus_set()

        # Start CAN listener in a separate thread if CAN bus is available
        if self.can_bus:
            self.listener_thread = threading.Thread(target=self.setup_can_listener, daemon=True)
            self.listener_thread.start()
        else:
            logging.warning("No CAN bus available. Starting in demo mode.")
            self.start_demo_mode()

    def setup_button_actions(self):
        """
        Configure button actions in the view if the buttons exist.
        Safely handles missing UI elements.
        """
        try:
            # Main app buttons - using safe attribute access to avoid errors
            if hasattr(self.view, 'button1') and self.view.button1 is not None:
                self.view.button1.config(command=self.toggle_demo_mode)
            
            if hasattr(self.view, 'button2') and self.view.button2 is not None:
                self.view.button2.config(command=self.menu_toggle)
                
            # Menu navigation buttons
            self.setup_menu_buttons()
            
        except Exception as e:
            logging.error(f"Error setting up button actions: {e}")
    
    def setup_menu_buttons(self):
        """
        Configure menu-specific buttons if they exist.
        """
        try:
            # Main menu buttons
            if hasattr(self.view, 'button3') and self.view.button3 is not None:
                self.view.button3.config(command=lambda: self.change_max_torque(10))
                
            if hasattr(self.view, 'button4') and self.view.button4 is not None:
                self.view.button4.config(command=lambda: self.change_max_power(10))
                
            if hasattr(self.view, 'button5') and self.view.button5 is not None:
                self.view.button5.config(command=self.calibrate_throttle_upper)
                
            if hasattr(self.view, 'button6') and self.view.button6 is not None:
                self.view.button6.config(command=self.calibrate_throttle_lower)
                
            if hasattr(self.view, 'button7') and self.view.button7 is not None:
                self.view.button7.config(command=self.show_debug_screen)
                
            if hasattr(self.view, 'button8') and self.view.button8 is not None:
                self.view.button8.config(command=self.show_ecu_screen)
                
            # Event selection buttons
            if hasattr(self.view, 'button4') and self.view.button4 is not None:
                self.view.button4.config(command=lambda: self.change_event_and_close_menu("autocross"))
                
            if hasattr(self.view, 'button5') and self.view.button5 is not None:
                self.view.button5.config(command=lambda: self.change_event_and_close_menu("endurance"))
                
            if hasattr(self.view, 'button6') and self.view.button6 is not None:
                self.view.button6.config(command=lambda: self.change_event_and_close_menu("acceleration"))
                
            if hasattr(self.view, 'button7') and self.view.button7 is not None:
                self.view.button7.config(command=lambda: self.change_event_and_close_menu("skidpad"))
                
            if hasattr(self.view, 'button8') and self.view.button8 is not None:
                self.view.button8.config(command=lambda: self.change_event_and_close_menu("practice"))
                
        except Exception as e:
            logging.error(f"Error setting up menu buttons: {e}")

    def setup_can_listener(self):
        """
        Creates a 'can.Notifier' which will call 'self.process_can_message'
        every time a new CAN frame arrives on the bus.
        """
        if self.can_bus:
            try:
                self.notifier = can.Notifier(self.can_bus, [self.process_can_message])
                logging.info("CAN listener successfully set up in Controller.")
            except Exception as e:
                logging.error(f"Failed to set up CAN listener: {e}")
                self.start_demo_mode()  # Fall back to demo mode if CAN bus is not available
        else:
            logging.error("No CAN bus available. Cannot listen for messages.")
            self.start_demo_mode()  # Fall back to demo mode if CAN bus is not available

    def process_can_message(self, msg):
        """
        Forward incoming CAN frames to the model for decoding and value updates.
        """
        self.model.process_can_message(msg)

    def toggle_demo_mode(self):
        """
        Toggle the demo mode which generates random values for development/testing.
        """
        self.demo_mode = not self.demo_mode
        
        if self.demo_mode:
            self.start_demo_mode()
            if hasattr(self.view, 'mode_label') and self.view.mode_label is not None:
                self.view.mode_label.config(text=f"DEMO MODE - {self.model.current_event.capitalize()}")
        else:
            self.stop_demo_mode()
            if hasattr(self.view, 'mode_label') and self.view.mode_label is not None:
                self.view.mode_label.config(text=f"AMI: Manual Driving - {self.model.current_event.capitalize()}")
    
    def start_demo_mode(self):
        """Start the demo mode thread that generates random values"""
        # First check if we have a thread and if it's alive
        if self.demo_thread is None or not self.demo_thread.is_alive():
            self.demo_mode = True
            try:
                self.demo_thread = threading.Thread(target=self.run_demo_updates, daemon=True)
                self.demo_thread.start()
                logging.info("Demo mode started")
            except Exception as e:
                logging.error(f"Error starting demo mode: {e}")
    
    def stop_demo_mode(self):
        """Stop the demo mode thread"""
        self.demo_mode = False
        # Thread will exit on its own when demo_mode becomes False
        logging.info("Demo mode stopped")
    
    def run_demo_updates(self):
        """
        Generate random updates for various car parameters.
        This is used for testing when no real CAN bus is available.
        """
        try:
            while self.demo_mode:
                # Update temperatures with slight random variations
                self.update_with_random_variation("Motor L Temp", 60, 5)
                self.update_with_random_variation("Motor R Temp", 62, 5)
                self.update_with_random_variation("Inverter L Temp", 55, 5)
                self.update_with_random_variation("Inverter R Temp", 57, 5)
                self.update_with_random_variation("Accu Temp", 35, 3)
                self.update_with_random_variation("Air Temp", 25, 2)
                
                # Update SOC with a slow decrease
                current_soc = self.model.get_value("SOC") or 100
                new_soc = max(0, current_soc - random.uniform(0, 0.5))
                self.update_value("SOC", round(new_soc, 1))
                
                # Update lowest cell voltage with slight variations
                self.update_with_random_variation("Lowest Cell", 3.7, 0.05)
                
                # Update speed with variations
                self.update_with_random_variation("Speed", 60, 10)
                
                # Randomly switch TC and TV modes occasionally
                if random.random() < 0.05:  # 5% chance each update
                    self.cycle_tc_mode()
                
                if random.random() < 0.05:  # 5% chance each update
                    self.cycle_tv_mode()
                
                # Random update to max torque
                if random.random() < 0.02:  # 2% chance each update
                    self.update_value("Max Torque", random.randint(80, 100))
                
                # Simulate DRS state changes
                if random.random() < 0.1:  # 10% chance each update
                    drs_state = "On" if random.random() < 0.7 else "Off"  # 70% chance of being On
                    self.update_value("DRS", drs_state)
                
                # Wait before the next update
                time.sleep(1)
        except Exception as e:
            logging.error(f"Error in demo update thread: {e}")
    
    def update_with_random_variation(self, key, base_value, variation):
        """Update a value with random variation around a base value"""
        try:
            new_value = base_value + random.uniform(-variation, variation)
            self.update_value(key, round(new_value, 1))
        except Exception as e:
            logging.error(f"Error updating {key}: {e}")

    def random_update_value(self):
        """
        Picks a random valid param ID from the current event's layout
        and assigns it a random value (0..100).
        """
        layout = self.model.event_screens.get(self.model.current_event, [])
        # Flatten the layout to a list of strings that match model.values keys
        param_ids = self._extract_param_ids(layout)
        if not param_ids:
            return  # no valid param to update

        key = random.choice(param_ids)  # pick a random param ID (string)
        value = int(random.uniform(0, 100))
        self.model.update_value(key, value)

    def _extract_param_ids(self, structure):
        """
        Recursively traverse the event_screens structure to find all valid param IDs.
        Returns a list of strings that can be updated in self.model.values.
        """
        found = []

        # If 'structure' is a list:
        if isinstance(structure, list):
            for item in structure:
                # Recurse on each element
                found.extend(self._extract_param_ids(item))

        # If 'structure' is a dict describing a single panel:
        elif isinstance(structure, dict):
            raw_id = structure.get("id")
            # If it has an 'id' that is actually in model.values, we treat it as valid
            if raw_id and raw_id in self.model.values:
                found.append(raw_id)
            # Or if no 'id' but there's a 'name' that matches a model key
            elif not raw_id and "name" in structure and structure["name"] in self.model.values:
                found.append(structure["name"])

        # If 'structure' is a string:
        elif isinstance(structure, str):
            # If it matches a key in model.values, keep it
            if structure in self.model.values:
                found.append(structure)

        return found

    def update_value(self, key, value):
        """
        A direct method to update a specific key's value in the model.
        """
        try:
            self.model.update_value(key, value)
        except Exception as e:
            logging.error(f"Error updating value {key}: {e}")

    def change_event(self, event_name):
        """
        Change the current event context in the model (e.g., 'autocross').
        The model will trigger the view to rebuild the display.
        """
        try:
            self.model.change_event(event_name)
            
            # Update the mode label with demo mode indication if active
            if hasattr(self.view, 'mode_label') and self.view.mode_label is not None:
                if self.demo_mode:
                    self.view.mode_label.config(text=f"DEMO MODE - {event_name.capitalize()}")
                else:
                    self.view.mode_label.config(text=f"AMI: Manual Driving - {event_name.capitalize()}")
        except Exception as e:
            logging.error(f"Error changing event to {event_name}: {e}")

    def change_event_and_close_menu(self, event_name):
        """
        Helper to switch the event and also hide the menu UI.
        """
        self.change_event(event_name)
        if hasattr(self.view, 'menu_pop'):
            try:
                self.view.menu_pop()
            except Exception as e:
                logging.error(f"Error closing menu: {e}")

    def menu_toggle(self):
        """
        Opens or closes menu, but won't trigger again
        if it was just triggered within 'self.lockout_ms' ms.
        """
        if self.toggle_in_progress:
            return

        self.toggle_in_progress = True
        if hasattr(self.view, 'menu_pop'):
            try:
                self.view.menu_pop()
            except Exception as e:
                logging.error(f"Error toggling menu: {e}")
        
        self.view.after(self.lockout_ms, self._reset_toggle_lock)

    def _reset_toggle_lock(self):
        """
        Allows the menu_toggle function to be called again.
        """
        self.toggle_in_progress = False

    def handle_key_press(self, event):
        """
        Handle keyboard shortcuts for changing values/events or toggling the menu.
        """
        try:
            key = event.keysym.lower()
            if key == 'space':
                # Toggle demo mode
                self.toggle_demo_mode()
            elif key == 'n':
                # Move to next event
                event_names = list(self.model.event_screens.keys())
                current_index = event_names.index(self.model.current_event)
                next_index = (current_index + 1) % len(event_names)
                self.change_event(event_names[next_index])
            elif key == 'p':
                # Move to previous event
                event_names = list(self.model.event_screens.keys())
                current_index = event_names.index(self.model.current_event)
                prev_index = (current_index - 1) % len(event_names)
                self.change_event(event_names[prev_index])
            elif key == 'h' or key == 'escape':
                # Show/hide menu or go back to previous screen
                if hasattr(self.view, 'menu_pop'):
                    self.view.menu_pop()
            elif key == 't':
                # Cycle traction control mode
                self.cycle_tc_mode()
            elif key == 'v':
                # Cycle torque vectoring mode
                self.cycle_tv_mode()
            elif key == 'd':
                # Toggle DRS state
                current_drs = self.model.get_value("DRS")
                new_drs = "Off" if current_drs == "On" else "On"
                self.update_value("DRS", new_drs)
            elif key == 'q':
                # Quit the application
                self.view.quit()
            elif key == 's':
                # Example: highlight main-menu button #2, if the method exists
                if hasattr(self.view, '_highlight_main_menu_button'):
                    self.view._highlight_main_menu_button(2)
        except Exception as e:
            logging.error(f"Error handling key press {event.keysym}: {e}")

    def change_max_torque(self, amount):
        """Change the maximum torque setting"""
        current_torque = self.model.get_value("Max Torque") or 0
        new_torque = min(100, max(0, current_torque + amount))
        self.update_value("Max Torque", new_torque)
    
    def change_max_power(self, amount):
        """Change the maximum power setting"""
        # This setting might not have a direct parameter in the model,
        # so we log a notification and implement a direct CAN message send if needed
        logging.info(f"Maximum power changed by {amount}")
        
        # Example of sending a CAN message if we have a bus and protocol for this
        if self.can_bus:
            try:
                # This is an example - actual implementation would depend on the car's CAN protocol
                arbitration_id = 0x123  # Replace with actual ID for power control
                data = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  # Replace with actual data format
                msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
                self.can_bus.send(msg)
                logging.info(f"Sent power control message: {msg}")
            except Exception as e:
                logging.error(f"Failed to send power control message: {e}")
    
    def calibrate_throttle_upper(self):
        """Calibrate the upper threshold of the throttle position sensor"""
        logging.info("Calibrating throttle position upper threshold")
        # This would typically send a specific CAN message to the throttle controller
        if self.can_bus:
            try:
                # Example - actual implementation depends on the car's protocol
                arbitration_id = 0x694  # DIU_Calibrate_APPS_Request
                data = [0x01]  # Command for upper calibration
                msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
                self.can_bus.send(msg)
                logging.info(f"Sent throttle upper calibration message: {msg}")
            except Exception as e:
                logging.error(f"Failed to send throttle calibration message: {e}")
    
    def calibrate_throttle_lower(self):
        """Calibrate the lower threshold of the throttle position sensor"""
        logging.info("Calibrating throttle position lower threshold")
        # Similar to upper calibration but with a different command value
        if self.can_bus:
            try:
                arbitration_id = 0x694  # DIU_Calibrate_APPS_Request
                data = [0x02]  # Command for lower calibration
                msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
                self.can_bus.send(msg)
                logging.info(f"Sent throttle lower calibration message: {msg}")
            except Exception as e:
                logging.error(f"Failed to send throttle calibration message: {e}")
    
    def show_debug_screen(self):
        """Show the debugging screen"""
        if hasattr(self.view, 'menu_debug_frame') and hasattr(self.view, 'show_menu_screen'):
            try:
                self.view.show_menu_screen(self.view.menu_debug_frame)
            except Exception as e:
                logging.error(f"Error showing debug screen: {e}")
    
    def show_ecu_screen(self):
        """Show the ECU version screen"""
        if hasattr(self.view, 'menu_ecu_frame') and hasattr(self.view, 'show_menu_screen'):
            try:
                self.view.show_menu_screen(self.view.menu_ecu_frame)
            except Exception as e:
                logging.error(f"Error showing ECU screen: {e}")
    
    def cycle_tc_mode(self):
        """Cycle through traction control modes"""
        self.current_tc_mode = (self.current_tc_mode + 1) % len(self.tc_modes)
        self.update_value("Traction Control Mode", self.tc_modes[self.current_tc_mode])
    
    def cycle_tv_mode(self):
        """Cycle through torque vectoring modes"""
        self.current_tv_mode = (self.current_tv_mode + 1) % len(self.tv_modes)
        self.update_value("Torque Vectoring Mode", self.tv_modes[self.current_tv_mode])

    def _on_cell_voltage_update(self, global_idx, value):
        """
        Update the stored voltage for the cell identified by 'global_idx' (0..119).
        Then compute the lowest voltage across all known cells.
        """
        try:
            self.cell_voltages[global_idx] = value

            # Only compute min if we have at least 1 known cell
            if self.cell_voltages:
                lowest_voltage = min(self.cell_voltages.values())
                self.update_value("Lowest Cell", lowest_voltage)
        except Exception as e:
            logging.error(f"Error updating cell voltage {global_idx}: {e}")