import threading
import random
import logging
import can

logging.basicConfig(level=logging.INFO)

class Controller:
    """
    The 'Controller' in an MVC architecture.
    - Binds model and view together.
    - Listens for user interactions (button/key press).
    - Receives CAN frames (via a background thread) and updates the model accordingly.
    With the updated two-panel layout in the view, the controller logic remains largely the same.
    """
    def __init__(self, model, view, can_bus=None):
        self.model = model
        self.view = view
        self.can_bus = can_bus or self.model.can_bus  # fallback to model's bus if not provided

        # Bind model callbacks to the view's update methods
        self.model.bind_value_changed(self.view.handle_value_update)
        self.model.bind_event_changed(self.view.create_event_screen)

        # Configure view button actions
        self.view.button1.config(command=self.random_update_value)        # "Add random value"
        self.view.button2.config(command=self.menu_selector)              # "Event Selection"

        # Event menu buttons (autocross, endurance, etc.)
        self.view.button4.config(command=lambda: self.change_event_and_close_menu("autocross"))
        self.view.button5.config(command=lambda: self.change_event_and_close_menu("endurance"))
        self.view.button6.config(command=lambda: self.change_event_and_close_menu("acceleration"))
        self.view.button7.config(command=lambda: self.change_event_and_close_menu("skidpad"))
        self.view.button8.config(command=lambda: self.change_event_and_close_menu("practice"))

        # Key bindings from the view
        self.view.bind("<Key>", self.handle_key_press)
        self.view.focus_set()

        # Start CAN listener in a separate thread
        self.listener_thread = threading.Thread(target=self.setup_can_listener, daemon=True)
        self.listener_thread.start()

        # -----------------------------------------------------
        # Toggle lock variables (prevents rapid menu toggles)
        self.toggle_in_progress = False
        self.lockout_ms = 100  # Cooldown (milliseconds) before menu_toggle can trigger again
        # -----------------------------------------------------

        # Dictionary to store per-cell voltage
        self.cell_voltages = {}

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
        else:
            logging.error("No CAN bus available. Cannot listen for messages.")

    def process_can_message(self, msg):
        """
        Forward incoming CAN frames to the model for decoding and value updates.
        """
        self.model.process_can_message(msg)

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
        self.model.update_value("SOC", value)

    def _extract_param_ids(self, structure):
        """
        Recursively traverse the event_screens structure to find all valid param IDs
        (strings or dicts with an 'id'), ignoring sub-lists, etc.
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
        self.model.update_value(key, value)

    def change_event(self, event_name):
        """
        Change the current event context in the model (e.g., 'autocross').
        The model will trigger the view to rebuild the display with two columns.
        """
        self.model.change_event(event_name)

    def change_event_and_close_menu(self, event_name):
        """
        Helper to switch the event and also hide the menu UI.
        """
        self.change_event(event_name)
        self.view.menu_pop()

    def menu_selector(self):
        """
        Show the event menu in the UI.
        """
        self.view.menu_event_selector()

    def menu_toggle(self):
        """
        Opens or closes menu, but won't trigger again
        if it was just triggered within 'self.lockout_ms' ms.
        """
        if self.toggle_in_progress:
            return

        self.toggle_in_progress = True
        self.view.menu_pop()
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
        key = event.keysym.lower()
        if key == 'space':
            # Randomly update a value
            self.random_update_value()
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
        elif key == 'h':
            # Show/hide menu
            self.view.menu_pop()
        elif key == 'escape':
            # Quit the application
            self.view.quit()
        elif key == 's':
            # Example: highlight main-menu button #2, or do something else
            self.main_menu_down()

    def main_menu_down(self):
        """
        Decrement the active button index, wrapping around to the last button
        in main_menu_button_list if we go below 0. (Example function.)
        """
        self.view._highlight_main_menu_button(2)

    def main_menu_up(self):
        """
        Increment the active button index, wrapping around if needed.
        (Example function, not currently bound to a key.)
        """
        if self.view.active_button < len(self.view.main_menu_button_list) - 1:
            self.view.active_button += 1
        else:
            self.view.active_button = 0

    def _on_cell_voltage_update(self, global_idx, value):
        """
        Update the stored voltage for the cell identified by 'global_idx' (0..119).
        Then compute the lowest voltage across all known cells.
        """
        self.cell_voltages[global_idx] = value

        # Only compute min if we have at least 1 known cell
        if self.cell_voltages:
            lowest_voltage = min(self.cell_voltages.values())
            self.update_value("Lowest Cell Voltage", lowest_voltage)
