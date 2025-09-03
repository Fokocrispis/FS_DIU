import threading
import random
import logging
import can
import time

logging.basicConfig(level=logging.INFO)

class Controller:
    """
    The 'Controller' in an MVC architecture with dual CAN bus support.
    - Binds model and view together.
    - Listens for user interactions (button/key press).
    - Receives CAN frames from both control and logging buses and updates the model accordingly.
    - Manages menu navigation and screen transitions.
    - Handles SWU (Switch Wheel Unit) button inputs from the steering wheel.
    - Routes CAN messages to appropriate bus based on H20 specification.
    """
    def __init__(self, model, view, control_bus=None, logging_bus=None):
        self.model = model
        self.view = view
        self.control_bus = control_bus
        self.logging_bus = logging_bus

        # Initialize state variables
        self.toggle_in_progress = False
        self.lockout_ms = 100  # Cooldown (milliseconds) before menu_toggle can trigger again
        self.cell_voltages = {}  # Dictionary to store per-cell voltage
        self.demo_mode = False
        self.demo_thread = None  # Initialize the demo thread reference
        
        # Screen state management
        self.current_screen_state = "tsoff"  # Track current screen: "tsoff", "event", "menu"
        self.current_event_name = None  # Track which event screen is active
        
        # State tracking for traction control and torque vectoring modes
        self.tc_modes = ["Off", "Dry", "Wet", "Snow", "Custom", "Auto"]
        self.tv_modes = ["Off", "Low", "Medium", "High", "Custom"]
        self.current_tc_mode = 0  # Index in tc_modes
        self.current_tv_mode = 2  # Index in tv_modes (Medium)
        
        # Set initial TC and TV mode values
        self.update_value("Traction Control Mode", self.tc_modes[self.current_tc_mode])
        self.update_value("Torque Vectoring Mode", self.tv_modes[self.current_tv_mode])

        # Bind model callbacks
        # Use separate callbacks to avoid interference
        self.model.bind_value_changed(self.view.handle_value_update)
        self.model.bind_event_changed(self.view.create_event_screen)
        
        # Register specific callback only for TS On changes
        self._register_ts_on_callback()

        # Configure view button actions if they exist
       # self.setup_button_actions()

        # Key bindings from the view
        self.view.bind("<Key>", self.handle_key_press)
        self.view.focus_set()

        # Start CAN listeners in separate threads for both buses
        self.setup_dual_can_listeners()

        self.toggle_fullscreen()

        # Blink logo for visual feedback
        self.logo_blink_state = True
        self.view.after(1000, self.toggle_logo)
        
        # Initialize screen state (View starts with TS off screen)
        self.current_screen_state = "tsoff"
        self.current_event_name = None

    def _register_ts_on_callback(self):
        """Register a specific callback that only triggers for TS On changes"""
        def ts_on_only_callback(key, value):
            if key == "TS On":
                self.handle_screen_change(key, value)
        
        self.model.bind_value_changed(ts_on_only_callback)

    # Callback for TS On update to change event
    def handle_screen_change(self, key, value):
        # This callback is now only called for "TS On" changes
        logging.info(f"TS On change detected: {key} = {value}")
        
        # Debug current state before processing
        self._debug_current_state()
            
        if value == 1:
            drivemode = self.model.get_value("Drivemode")
            logging.info(f"TS On = 1 detected, Drivemode = {drivemode}")
            
            # Check if we have a valid drivemode
            if drivemode and drivemode != "unknown":
                # Only switch if we're not already in the correct event screen
                if self.current_screen_state != "event" or self.current_event_name != drivemode:
                    logging.info(f"Switching to {drivemode} event due to TS On = 1")
                    self._switch_to_event_screen(drivemode)
                else:
                    logging.info(f"Already in {drivemode} event screen, no switch needed")
            else:
                # If no valid drivemode, ensure we're in TS off screen
                logging.info("No valid drivemode found, ensuring TS off screen")
                if self.current_screen_state != "tsoff":
                    self._switch_to_tsoff_screen()
                    
        elif value == 0:
            # Only show TS off screen if we're not already in TS off screen
            if self.current_screen_state != "tsoff":
                logging.info("Showing TS off screen due to TS On = 0")
                self._switch_to_tsoff_screen()
            else:
                logging.info("TS On = 0 but already in TS off screen - ignoring")
        
        # Debug state after processing
        self._debug_current_state()

    def _switch_to_event_screen(self, drivemode):
        """Switch to the event screen for the given drivemode, but only if necessary."""
        try:
            logging.info(f"Switching to event screen: {drivemode}")
            
            # Step 1: Update our state tracking
            self.current_screen_state = "event"
            self.current_event_name = drivemode
            
            # Step 2: Ensure we're not in any menu (only if necessary)
            if self._is_in_menu_screen() or self._is_in_tsoff_screen():
                logging.info("Leaving menu/TS off screen to show event screen")
                self.view.return_to_event_screen()
            
            # Step 3: Change the event in the model (only if different)
            if self.model.current_event != drivemode:
                logging.info(f"Changing model event from {self.model.current_event} to {drivemode}")
                self.model.change_event(drivemode)
            else:
                logging.info(f"Model already set to {drivemode}, no change needed")
            
            # Step 4: Create event screen only if it doesn't exist or is different
            if (not self.view.current_screen or 
                not hasattr(self.view.current_screen, 'event_name') or 
                self.view.current_screen.event_name != drivemode):
                logging.info(f"Creating new event screen for {drivemode}")
                self.view.create_event_screen(drivemode)
            else:
                logging.info(f"Event screen for {drivemode} already exists, reusing")
            
            # Step 5: Ensure the main UI is visible (only if necessary)
            if not self.view.split_frame.winfo_ismapped():
                logging.info("Showing main UI frames")
                self.view.return_to_event_screen()
                
            logging.info(f"Successfully ensured {drivemode} event screen is active")
            
        except Exception as e:
            logging.error(f"Error switching to event screen for {drivemode}: {e}")
            # Reset state on error
            self.current_screen_state = "unknown"
            self.current_event_name = None
    
    def _switch_to_tsoff_screen(self):
        """Switch to the TS off screen, but only if necessary."""
        try:
            logging.info("Switching to TS off screen")
            
            # Update our state tracking
            self.current_screen_state = "tsoff"
            self.current_event_name = None
            
            # Only switch if we're not already in TS off screen
            if not self._is_in_tsoff_screen():
                logging.info("Showing TS off screen")
                self.view.show_tsoff_screen()
            else:
                logging.info("Already in TS off screen, no switch needed")
                
        except Exception as e:
            logging.error(f"Error switching to TS off screen: {e}")
            # Reset state on error
            self.current_screen_state = "unknown"
            self.current_event_name = None

    def _debug_current_state(self):
        """Debug method to log current screen state"""
        logging.info(f"Current screen state: {self.current_screen_state}")
        logging.info(f"Current event name: {self.current_event_name}")
        logging.info(f"View current screen: {getattr(self.view.current_screen, 'event_name', 'None') if self.view.current_screen else 'None'}")
        logging.info(f"Model current event: {self.model.current_event}")
        logging.info(f"Is in TS off: {self._is_in_tsoff_screen()}")
        logging.info(f"Is in menu: {self._is_in_menu_screen()}")

    def _ensure_event_screen_visible(self, event_name):
        """Ensure that the event screen is visible and not overridden by menus"""
        try:
            # Double-check that we're showing the correct event screen
            if not self._is_in_tsoff_screen() and not self._is_in_menu_screen():
                logging.info(f"Event screen for {event_name} should be visible")
            else:
                logging.warning(f"Event screen not visible, forcing return to event screen")
                self.view.return_to_event_screen()
        except Exception as e:
            logging.error(f"Error ensuring event screen visibility: {e}")

            # DOES NOT WORK AS INTENDET ATM
            # if key == "Menu" and value == 1:
            #     # Only show debug screen if we're not already in a menu
            #     if not self._is_in_menu_screen():
            #         logging.info("Showing debug screen due to Menu button press")
            #         self.view.show_debug_screen()
            #     else:
            #         logging.info("Menu button pressed but already in menu screen - ignoring")

            # if key == "Menu" and value == 0:
            #     logging.info("Hiding debug screen due to Menu button release")
            #     self.view.hide_debug_screen()

            # if key == "Up" and value == 1 and self._is_in_menu_screen():
            #     # set upper pedal position
            #     upper_pos = self.model.get_value("apps_modified")
            # if key == "Down" and value == 1 and self._is_in_menu_screen():
            #     # set lower pedal position
            #     lower_pos = self.model.get_value("apps_modified")
            # if key == "Ok" and value == 1 and self._is_in_menu_screen():
            #     return  # Do nothing if Ok is pressed in menu
            #     # send CAN message to set upper/lower pedal position
            #     #msg_id = 0x2B6  # DIU_Calibrate_APPS_Request (Control Bus)
            #     #data = (upper_pos, lower_pos)
            #     #self.send_on_bus(self.control_bus, msg_id, data, "logging")

    def _is_in_menu_screen(self):
        """
        Check if we're currently in any menu screen.
        Returns True if any menu frame is currently mapped/visible.
        """
        return (self._is_in_screen('menu') or 
                self._is_in_screen('debug') or 
                self._is_in_screen('ecu'))

    def _is_in_tsoff_screen(self):
        """
        Check if we're currently in the TS off screen.
        Returns True if the TS off screen is currently visible.
        """
        return self._is_in_screen('tsoff')

    def _is_in_screen(self, screen_name):
        """
        Generic function to check if we're currently in a specific screen.
        
        Args:
            screen_name: Name of the screen to check (e.g., 'menu', 'tsoff', 'debug', 'ecu')
        
        Returns:
            bool: True if currently in the specified screen, False otherwise
        """
        try:
            screen_name = screen_name.lower()
            
            # Check for menu screens
            if screen_name in ['menu', 'main_menu']:
                return hasattr(self.view, 'menu_main_frame') and self.view.menu_main_frame.winfo_ismapped()
            
            elif screen_name in ['debug', 'debug_menu']:
                return hasattr(self.view, 'menu_debug_frame') and self.view.menu_debug_frame.winfo_ismapped()
            
            elif screen_name in ['ecu', 'ecu_menu']:
                return hasattr(self.view, 'menu_ecu_frame') and self.view.menu_ecu_frame.winfo_ismapped()
            
            # Check for TS off screen
            elif screen_name in ['tsoff', 'ts_off']:
                if hasattr(self.view, 'tsoff_frame') and self.view.tsoff_frame.winfo_ismapped():
                    return True
                if hasattr(self.view, 'ts_off_frame') and self.view.ts_off_frame.winfo_ismapped():
                    return True
                if hasattr(self.view, 'current_screen') and getattr(self.view, 'current_screen', None) == 'tsoff':
                    return True
            
            # Generic frame check - try common naming patterns
            else:
                # Try direct frame name
                frame_attr = f"{screen_name}_frame"
                if hasattr(self.view, frame_attr):
                    frame = getattr(self.view, frame_attr)
                    if hasattr(frame, 'winfo_ismapped') and frame.winfo_ismapped():
                        return True
                
                # Try menu_ prefix
                menu_frame_attr = f"menu_{screen_name}_frame"
                if hasattr(self.view, menu_frame_attr):
                    frame = getattr(self.view, menu_frame_attr)
                    if hasattr(frame, 'winfo_ismapped') and frame.winfo_ismapped():
                        return True
                
                # Check current_screen attribute
                if hasattr(self.view, 'current_screen') and getattr(self.view, 'current_screen', None) == screen_name:
                    return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error checking screen state for '{screen_name}': {e}")
            return False

    def handle_menu_action(self, panel_id, value):
        """
        Handle menu actions triggered by the model.
        This method is called when the model updates a value that requires a UI action.
        """
        try:
            if panel_id == "Menu":
                self.menu_toggle()
        except Exception as e:
            logging.error(f"Error handling menu action {panel_id}: {e}")

    def setup_dual_can_listeners(self):
        """
        Set up CAN message listeners for both control and logging buses.
        """
        # Start control bus listener
        if self.control_bus:
            self.control_listener_thread = threading.Thread(
                target=self.setup_can_listener, 
                args=(self.control_bus, "control"),
                daemon=True
            )
            self.control_listener_thread.start()
            logging.info("Control bus listener started")
        else:
            logging.warning("No control CAN bus available")

        # Start logging bus listener  
        if self.logging_bus:
            self.logging_listener_thread = threading.Thread(
                target=self.setup_can_listener, 
                args=(self.logging_bus, "logging"),
                daemon=True
            )
            self.logging_listener_thread.start()
            logging.info("Logging bus listener started")
        else:
            logging.warning("No logging CAN bus available")

        # Start demo mode if no real buses are available
        if not self.control_bus and not self.logging_bus:
            logging.warning("No CAN buses available. Consider starting demo mode.")

    def setup_can_listener(self, bus, bus_name):
        """
        Creates a 'can.Notifier' which will call 'self.process_can_message'
        every time a new CAN frame arrives on the specified bus.
        """
        if bus:
            try:
                notifier = can.Notifier(bus, [lambda msg: self.process_can_message(msg, bus_name)])
                logging.info(f"CAN listener successfully set up for {bus_name} bus in Controller.")
            except Exception as e:
                logging.error(f"Failed to set up CAN listener for {bus_name} bus: {e}")
        else:
            logging.error(f"No {bus_name} CAN bus available. Cannot listen for messages.")

    def process_can_message(self, msg, bus_name="unknown"):
        """
        Forward incoming CAN frames to the model for decoding and value updates.
        Includes bus identification for logging and debugging.
        """
        try:
            # Log message reception for debugging
            logging.debug(f"Received message on {bus_name} bus: ID=0x{msg.arbitration_id:03X}")
            
            # Forward to model for processing
            self.model.process_can_message(msg)
        except Exception as e:
            logging.error(f"Error processing CAN message from {bus_name} bus: {e}")

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
            logging.warning(f"Cannot send message 0x{msg_id:03X} - {bus_type} bus not available")
            return False

    def _send_on_bus(self, bus, msg_id, data, bus_name):
        """
        Helper method to send message on specific bus.
        """
        try:
            msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=False)
            bus.send(msg)
            logging.info(f"Message sent on {bus_name} bus: {msg}")
            return True
        except Exception as e:
            logging.error(f"Error sending message on {bus_name} bus: {e}")
            return False

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
                
        except Exception as e:
            logging.error(f"Error setting up menu buttons: {e}")

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
        logging.info("Demo mode stopped")
    
    def run_demo_updates(self):
        """
        Generate random updates for various car parameters.
        This simulates data that would normally come from CAN buses.
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
        except Exception as e:
            logging.error(f"Error in demo update thread: {e}")
    
    def update_with_random_variation(self, key, base_value, variation):
        """Update a value with random variation around a base value"""
        try:
            new_value = base_value + random.uniform(-variation, variation)
            self.update_value(key, round(new_value, 1))
        except Exception as e:
            logging.error(f"Error updating {key}: {e}")

    def toggle_logo(self):
        """Toggle logo blinking for visual feedback"""
        try:
            if hasattr(self.view, 'toggle_logo'):
                self.view.toggle_logo()
        except Exception as e:
            logging.error(f"Error toggling logo: {e}")
        finally:
            # Schedule next toggle regardless of errors
            self.view.after(1500, self.toggle_logo)

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
                    self.view.mode_label.config(text=f"{event_name.capitalize()}")
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
        
        # Update state tracking
        if self._is_in_menu_screen():
            # Going back to previous screen
            if self.current_event_name:
                self.current_screen_state = "event"
            else:
                self.current_screen_state = "tsoff"
        else:
            # Going to menu
            self.current_screen_state = "menu"
        
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
                # Show settings screen
                if hasattr(self.view, 'show_menu_screen') and hasattr(self.view, 'menu_main_frame'):
                    self.view.show_menu_screen(self.view.menu_main_frame)
            elif key == 'f':
                # Toggle fullscreen
                self.toggle_fullscreen()
        except Exception as e:
            logging.error(f"Error handling key press {event.keysym}: {e}")

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if hasattr(self.view, 'attributes'):
            try:
                current_state = self.view.attributes("-fullscreen")
                self.view.attributes("-fullscreen", not current_state)
                logging.info(f"Fullscreen {'enabled' if not current_state else 'disabled'}")
            except Exception as e:
                logging.error(f"Error toggling fullscreen: {e}")

    def change_max_torque(self, amount):
        """Change the maximum torque setting via CAN message"""
        current_torque = self.model.get_value("Max Torque") or 0
        new_torque = min(100, max(0, current_torque + amount))
        self.update_value("Max Torque", new_torque)
        
        # Send CAN message to update torque setting (Control Bus)
        try:
            # This uses a hypothetical message ID for torque control
            msg_id = 0x2B5  # DIU_Change_Torque_Request (Control Bus)
            torque_data = int(new_torque).to_bytes(2, 'little')
            data = list(torque_data) + [0] * 6  # Pad to 8 bytes
            self.send_message_on_correct_bus(msg_id, data)
            logging.info(f"Sent torque change request: {new_torque} Nm")
        except Exception as e:
            logging.error(f"Failed to send torque change message: {e}")
    
    def change_max_power(self, amount):
        """Change the maximum power setting via CAN message"""
        logging.info(f"Maximum power changed by {amount}")
        
        # Send CAN message for power control (Control Bus)
        try:
            msg_id = 0x2B4  # Hypothetical power control message (Control Bus)
            power_data = int(amount).to_bytes(2, 'little')
            data = list(power_data) + [0] * 6  # Pad to 8 bytes
            self.send_message_on_correct_bus(msg_id, data)
            logging.info(f"Sent power control message: {amount}")
        except Exception as e:
            logging.error(f"Failed to send power control message: {e}")
    
    def calibrate_throttle_upper(self):
        """Calibrate the upper threshold of the throttle position sensor"""
        logging.info("Calibrating throttle position upper threshold")
        
        # Send CAN message for upper throttle calibration (Control Bus)
        try:
            msg_id = 0x2B6  # DIU_Calibrate_APPS_Request (Control Bus)
            data = [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  # Command for upper calibration
            self.send_message_on_correct_bus(msg_id, data)
            logging.info("Sent throttle upper calibration message")
        except Exception as e:
            logging.error(f"Failed to send throttle calibration message: {e}")
    
    def calibrate_throttle_lower(self):
        """Calibrate the lower threshold of the throttle position sensor"""
        logging.info("Calibrating throttle position lower threshold")
        
        # Send CAN message for lower throttle calibration (Control Bus)
        try:
            msg_id = 0x2B6  # DIU_Calibrate_APPS_Request (Control Bus)
            data = [0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  # Command for lower calibration
            self.send_message_on_correct_bus(msg_id, data)
            logging.info("Sent throttle lower calibration message")
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
        """Cycle through traction control modes and send CAN message"""
        self.current_tc_mode = (self.current_tc_mode + 1) % len(self.tc_modes)
        new_mode = self.tc_modes[self.current_tc_mode]
        self.update_value("Traction Control Mode", new_mode)
        
        # Send CAN message to update TC mode (Control Bus)
        try:
            msg_id = 0x280  # VCU Control message for TC (Control Bus)
            tc_value = self.current_tc_mode
            data = [tc_value, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            self.send_message_on_correct_bus(msg_id, data)
            logging.info(f"Sent TC mode change: {new_mode}")
        except Exception as e:
            logging.error(f"Failed to send TC mode message: {e}")
    
    def cycle_tv_mode(self):
        """Cycle through torque vectoring modes and send CAN message"""
        self.current_tv_mode = (self.current_tv_mode + 1) % len(self.tv_modes)
        new_mode = self.tv_modes[self.current_tv_mode]
        self.update_value("Torque Vectoring Mode", new_mode)
        
        # Send CAN message to update TV mode (Control Bus)
        try:
            msg_id = 0x281  # VCU Control message for TV (Control Bus)
            tv_value = self.current_tv_mode
            data = [tv_value, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            self.send_message_on_correct_bus(msg_id, data)
            logging.info(f"Sent TV mode change: {new_mode}")
        except Exception as e:
            logging.error(f"Failed to send TV mode message: {e}")

    def _on_cell_voltage_update(self, global_idx, value):
        """
        Update the stored voltage for the cell identified by 'global_idx'.
        Then compute the lowest voltage across all known cells.
        """
        try:
            # Apply the conversion factor from the DBC: raw * 0.01 + 2.5
            actual_voltage = (value * 0.01) + 2.5
            self.cell_voltages[global_idx] = actual_voltage

            # Only compute min if we have at least 1 known cell
            if self.cell_voltages:
                lowest_voltage = min(self.cell_voltages.values())
                self.update_value("Lowest Cell", round(lowest_voltage, 3))
        except Exception as e:
            logging.error(f"Error updating cell voltage {global_idx}: {e}")
            
    def handle_ok_button(self):
        """
        Handle the 'OK' button press from the steering wheel (Control Bus).
        """
        logging.info("SWU: OK button pressed")
        
        # If in a menu, select the currently highlighted item
        if hasattr(self.view, 'menu_main_frame') and self.view.menu_main_frame.winfo_ismapped():
            # Find the currently highlighted button and click it
            if hasattr(self.view, 'main_menu_button_list') and hasattr(self.view, 'active_button'):
                try:
                    active_button = self.view.main_menu_button_list[self.view.active_button]
                    active_button.invoke()
                    return
                except (IndexError, AttributeError):
                    pass
            
        # Otherwise toggle menu 
        self.menu_toggle()

    def handle_up_button(self):
        """
        Handle the 'Up' button press from the steering wheel (Control Bus).
        """
        logging.info("SWU: Up button pressed")
        
        # If in a menu, move highlight up
        if hasattr(self.view, 'menu_main_frame') and self.view.menu_main_frame.winfo_ismapped():
            if hasattr(self.view, 'main_menu_button_list') and hasattr(self.view, 'active_button'):
                try:
                    new_index = (self.view.active_button - 1) % len(self.view.main_menu_button_list)
                    if hasattr(self.view, '_highlight_main_menu_button'):
                        self.view._highlight_main_menu_button(new_index)
                except AttributeError:
                    pass
        else:
            # Toggle DRS when not in menu
            current_drs = self.model.get_value("DRS")
            new_drs = "Off" if current_drs == "On" else "On"
            self.update_value("DRS", new_drs)
            
            # Send DRS control message (Control Bus)
            try:
                msg_id = 0x2C0  # DRS Control message (Control Bus)
                drs_value = 1 if new_drs == "On" else 0
                data = [drs_value, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
                self.send_message_on_correct_bus(msg_id, data)
                logging.info(f"Sent DRS control: {new_drs}")
            except Exception as e:
                logging.error(f"Failed to send DRS message: {e}")

    def handle_down_button(self):
        """
        Handle the 'Down' button press from the steering wheel (Control Bus).
        """
        logging.info("SWU: Down button pressed")
        
        # If in a menu, move highlight down
        if hasattr(self.view, 'menu_main_frame') and self.view.menu_main_frame.winfo_ismapped():
            if hasattr(self.view, 'main_menu_button_list') and hasattr(self.view, 'active_button'):
                try:
                    new_index = (self.view.active_button + 1) % len(self.view.main_menu_button_list)
                    if hasattr(self.view, '_highlight_main_menu_button'):
                        self.view._highlight_main_menu_button(new_index)
                except AttributeError:
                    pass
        else:
            # Cycle traction control mode when not in menu
            self.cycle_tc_mode()

    def toggle_cooling(self):
        """
        Toggle cooling system via the steering wheel button (Control Bus).
        """
        logging.info("SWU: Cooling button pressed")
        
        # Send CAN message to toggle the cooling system (Control Bus)
        try:
            msg_id = 0x282  # VCU PDU Control message (Control Bus)
            # Toggle bit 2 (cooling system active)
            cooling_active = 1  # Assume we want to turn it on
            data = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            data[0] |= (cooling_active << 2)
            
            self.send_message_on_correct_bus(msg_id, data)
            logging.info("Sent cooling toggle message")
        except Exception as e:
            logging.error(f"Error sending cooling toggle message: {e}")

    def toggle_ts(self):
        """
        Toggle traction system via the steering wheel button (Control Bus).
        """
        logging.info("SWU: TS button pressed")
        
        # Send TS control message (Control Bus)
        try:
            msg_id = 0x2A0  # ASCU Control message (Control Bus)
            data = [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  # TS_On_Button request
            self.send_message_on_correct_bus(msg_id, data)
            logging.info("Sent TS control message")
        except Exception as e:
            logging.error(f"Error sending TS message: {e}")

    def toggle_r2d(self):
        """
        Toggle Ready-to-Drive mode via the steering wheel button (Control Bus).
        """
        logging.info("SWU: R2D button pressed")
        
        # Send R2D control message (Control Bus)
        try:
            msg_id = 0x283  # VCU R2D Control message (Control Bus)
            data = [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  # R2D active
            self.send_message_on_correct_bus(msg_id, data)
            logging.info("Sent R2D control message")
        except Exception as e:
            logging.error(f"Error sending R2D message: {e}")

    def perform_reset(self):
        """
        Perform a general reset via the steering wheel button (Control Bus).
        """
        logging.info("SWU: Reset button pressed")
        
        # Send overall reset message (Control Bus)
        try:
            msg_id = 0x2B3  # DIU Channel_Reset_Request (Control Bus)
            # Reset all systems (set all bits)
            data = [0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00]
            self.send_message_on_correct_bus(msg_id, data)
            logging.info("Sent overall reset message")
        except Exception as e:
            logging.error(f"Error sending reset message: {e}")
        
    def update_switch_state(self, switch_num, value):
        """
        Handle switch state changes from the SWU (Switch Wheel Unit) (Control Bus).
        
        Args:
            switch_num: Which switch changed (1-5)
            value: New value (0-15, as it's a 4-bit value per switch)
        """
        logging.info(f"SWU: Switch {switch_num} changed to {value}")
        
        # Map switch positions to meaningful values
        if switch_num == 1:  # Traction Control Mode switch
            if 0 <= value < len(self.tc_modes):
                self.current_tc_mode = value
                self.update_value("Traction Control Mode", self.tc_modes[value])
                # Send TC mode via CAN
                self.cycle_tc_mode()
            else:
                self.update_value("Traction Control Mode", f"Mode {value}")
        
        elif switch_num == 2:  # Torque Vectoring Mode switch
            if 0 <= value < len(self.tv_modes):
                self.current_tv_mode = value
                self.update_value("Torque Vectoring Mode", self.tv_modes[value])
                # Send TV mode via CAN
                self.cycle_tv_mode()
            else:
                self.update_value("Torque Vectoring Mode", f"Mode {value}")
        
        # Track all switch positions in the model
        self.update_value(f"Switch_{switch_num}", value)

    def handle_dtu_error(self, error_code):
        """
        Handle DTU error codes as defined in the DBC file (Logging Bus).
        
        Args:
            error_code: The DTU error code (0-42)
        """
        # Map of error codes to descriptive messages (from H20 DBC)
        error_messages = {
            0: "RF_HW_INIT_FAILED",
            1: "RF_SPI_HAL_ERROR_CB", 
            2: "RF_SPI_TRANSM_START_FAILED",
            3: "RF_TX_PAYLOAD_OVER_MAX_LEN",
            4: "RF_INCORRECT_IRQ_FLAGS",
            5: "DTUPROT_CAN_PACKET_OVER_MAX_LEN",
            6: "DTUPROT_COMPR_CAN_FROM_STATION",
            7: "DTUPROT_COMPR_CAN_NO_ENTRY",
            8: "SETTINGS_EE_INIT_FAILED",
            9: "SETTINGS_EE_WRITE_FAILED",
            10: "SETTINGS_EE_READ_FAILED",
            11: "SETTINGS_EE_FORMAT_FAILED",
            12: "SETTINGS_RX_RECONF_FREQUENTLY",
            13: "SETTINGS_TIMEOUT_START_HAL_FAIL",
            # Add more as needed from the DBC file
        }
        
        # Get error message, or use a generic one if not found
        error_message = error_messages.get(error_code, f"UNKNOWN_ERROR_{error_code}")
        
        if error_code > 0:
            logging.warning(f"DTU Error: {error_message} (Code: {error_code})")
            
            # Update the model with the error
            self.update_value("DTU_Error", error_code)
            self.update_value("DTU_Error_Message", error_message)
            
            # Show the error on the UI if possible
            if hasattr(self.view, 'show_debug_message'):
                self.view.show_debug_message(f"DTU Error: {error_message} (Code: {error_code})")

    def update_pdu_fault(self, component, is_fault):
        """
        Update PDU fault status from Logging Bus messages.
        
        Args:
            component: Component name (e.g., "VLU", "InverterR")
            is_fault: True if fault is present, False otherwise
        """
        logging.info(f"PDU Fault: {component} {'FAULT' if is_fault else 'OK'}")
        
        # Update the model
        fault_key = f"PDU_Fault_{component}"
        self.update_value(fault_key, is_fault)
        
        # Check for critical faults and take action
        if is_fault and component in ["InverterR", "InverterL", "VCU", "AMS", "ASMS"]:
            logging.warning(f"CRITICAL FAULT DETECTED: {component}")
            if hasattr(self.view, 'show_debug_message'):
                self.view.show_debug_message(f"CRITICAL FAULT: {component}")