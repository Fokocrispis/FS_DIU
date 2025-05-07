import os
import tkinter as tk
from PIL import Image, ImageTk

# --------------------------------------------------------------------------
# Color and style settings
# --------------------------------------------------------------------------
COLORS = {
    "background": "#0a0c0f",
    "panel_bg": "#1b1b1b",
    "panel_active": "#1b1b1b",  
    "border": "#666666",
    "text_primary": "#ffffff",
    "text_secondary": "#ff9900",
    "accent_critical": "#ff0000",
    "accent_warning": "#ffcc00",
    "accent_normal": "#00ff00",
    "header_bg": "#202020",
    "menu_bg": "#151515"
}

FONT_VALUE = ("Segoe UI", 36, "bold")
FONT_NAME = ("Segoe UI", 20)
FONT_HEADER = ("Segoe UI", 18, "bold")
FONT_BUTTON = ("Segoe UI", 18, "bold")

# --------------------------------------------------------------------------
# DisplayPanel - shows one parameter and its value
# --------------------------------------------------------------------------
class DisplayPanel(tk.Frame):
    """
    A panel displaying a single value, its name, and optional unit.
    Also applies color-coding logic depending on the parameter type.
    """
    def __init__(
        self,
        parent,
        panel_id,
        name,
        value,
        unit,
        model,
        font_value_override=None,
        font_name_override=None,
        value_padx=5,
        value_pady=0,
        name_padx=5,
        name_pady=(0, 0),
        width=200,   # default width if not specified
        height=100,  # default height if not specified
        bg_color=None # Optional custom background color
    ):
        super().__init__(
            parent,
            bg=bg_color if bg_color else COLORS["panel_bg"],
            highlightthickness=1,
            highlightcolor=COLORS["border"]
        )
        self.panel_id = panel_id
        self.name = name
        self.unit = unit
        self.model = model
        self.initial_font_value = font_value_override or FONT_VALUE
        self.initial_font_name = font_name_override or FONT_NAME
        self.value_padx = value_padx
        self.value_pady = value_pady
        self.name_padx = name_padx
        self.name_pady = name_pady

        # Force a static width & height
        self.config(width=width, height=height)
        self.pack_propagate(False)  # or grid_propagate(False) if using .grid()

        # Current font sizes (will be adjusted when resizing)
        self.font_value = self.initial_font_value
        self.font_name = self.initial_font_name

        # Value Label
        self.value_label = tk.Label(
            self,
            text=f"{value}{(' ' + self.unit) if self.unit else ''}",
            font=self.font_value,
            fg=self.get_value_color(value),
            bg=self["bg"],
            borderwidth=0
        )
        self.value_label.pack(
            expand=True,
            fill=tk.BOTH,
            padx=value_padx,
            pady=value_pady
        )

        # Name Label
        self.name_label = tk.Label(
            self,
            text=name,
            font=self.font_name,
            fg=COLORS["text_secondary"],
            bg=self["bg"],
            borderwidth=0
        )
        self.name_label.pack(
            expand=True,
            fill=tk.BOTH,
            padx=name_padx,
            pady=name_pady
        )
        
        # Bind to resize events
        self.bind("<Configure>", self.on_resize)
        
        # Initialize size to fit text
        self.after(10, self.adjust_font_size)

    def update_value(self, new_value):
        """
        Update the displayed value and color based on new_value.
        """
        self.value_label.config(
            text=f"{new_value}{(' ' + self.unit) if self.unit else ''}",
            fg=self.get_value_color(new_value)
        )
        self.adjust_font_size()

    def get_value_color(self, val):
        """
        Determine the foreground color based on self.panel_id and thresholds.
        """
        # Expanded thresholds based on parameter types
        if self.panel_id == "Air Temp" or self.panel_id == "Accu Temp":
            if val > 60:
                return COLORS['accent_critical']
            elif val > 40:
                return COLORS['accent_warning']
            else:
                return COLORS['accent_normal']
        elif self.panel_id in ["Motor L Temp", "Motor R Temp", "Inverter L Temp", "Inverter R Temp"]:
            if val > 80:
                return COLORS['accent_critical']
            elif val > 60:
                return COLORS['accent_warning']
            else:
                return COLORS['accent_normal']
        elif self.panel_id == "SOC":
            if val < 20:
                return COLORS['accent_critical']
            elif val < 30:
                return COLORS['accent_warning']
            else:
                return COLORS['accent_normal']
        elif self.panel_id == "Lowest Cell":
            if val < 3.2:
                return COLORS['accent_critical']
            elif val < 3.5:
                return COLORS['accent_warning']
            else:
                return COLORS['accent_normal']
                
        return COLORS['accent_normal']
        
    def on_resize(self, event=None):
        """Handle resize events to adjust font size"""
        self.adjust_font_size()
    
    def adjust_font_size(self):
        """
        Adjust font size to fit the panel size while maximizing use of space
        """
        if not hasattr(self, 'value_label') or not hasattr(self, 'name_label'):
            return
            
        # Get panel dimensions
        panel_width = self.winfo_width()
        panel_height = self.winfo_height()
        
        if panel_width <= 1 or panel_height <= 1:
            # Widget not fully initialized yet
            return
            
        # Start with initial font sizes
        family_val, size_val, weight_val = self.initial_font_value
        family_name, size_name = self.initial_font_name[0], self.initial_font_name[1]
        weight_name = self.initial_font_name[2] if len(self.initial_font_name) > 2 else "normal"
        
        # Get text content
        value_text = self.value_label['text']
        name_text = self.name_label['text']
        
        # Calculate available space (account for padding)
        if isinstance(self.value_pady, tuple):
            value_pady_total = self.value_pady[0] + self.value_pady[1]
        else:
            value_pady_total = self.value_pady * 2
            
        if isinstance(self.name_pady, tuple):
            name_pady_total = self.name_pady[0] + self.name_pady[1]
        else:
            name_pady_total = self.name_pady * 2
            
        available_height = panel_height - value_pady_total - name_pady_total
        available_width = panel_width - self.value_padx * 2
        
        # Reserve space for both labels (60% for value, 40% for name)
        value_height = available_height * 0.6
        name_height = available_height * 0.4
        
        # Find optimal font size - start with a large size and decrease until it fits
        # For value label
        new_size_val = size_val
        while new_size_val > 8:  # Minimum readable font size
            test_font = (family_val, new_size_val, weight_val)
            self.value_label.config(font=test_font)
            self.update_idletasks()
            if self.value_label.winfo_reqwidth() <= available_width and self.value_label.winfo_reqheight() <= value_height:
                break
            new_size_val -= 1
        
        # For name label
        new_size_name = size_name
        while new_size_name > 6:  # Minimum readable font size
            test_font = (family_name, new_size_name, weight_name)
            self.name_label.config(font=test_font)
            self.update_idletasks()
            if self.name_label.winfo_reqwidth() <= available_width and self.name_label.winfo_reqheight() <= name_height:
                break
            new_size_name -= 1
        
        # Save the new font configurations
        self.font_value = (family_val, new_size_val, weight_val)
        self.font_name = (family_name, new_size_name, weight_name)

# --------------------------------------------------------------------------
# PanelGroup
# --------------------------------------------------------------------------
class PanelGroup(tk.Frame):
    """
    A container for multiple items (strings, dicts, nested lists).
    If a dict has "width"/"height", we pass them to DisplayPanel so it becomes static.
    """
    def __init__(self, parent, model, items, group_bg=COLORS["panel_bg"]):
        super().__init__(parent, bg=group_bg)
        self.model = model
        self.panels = {}  # Dictionary to store panels by ID

        for item in items:
            self.add_item(item)

    def add_item(self, item):
        # 1) 2D list -> grid
        if (isinstance(item, list)
            and all(isinstance(sub, list) for sub in item)
            and len(item) > 0):
            self._create_grid(item)

        # 2) Single list -> nested PanelGroup
        elif isinstance(item, list):
            sub_group = PanelGroup(self, self.model, item, group_bg=self['bg'])
            sub_group.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 3) dict -> DisplayPanel
        elif isinstance(item, dict):
            raw_id = item.get("id", None)
            if not raw_id or raw_id == "Unknown":
                raw_name = item.get("name")
                if raw_name in self.model.values:
                    raw_id = raw_name
                else:
                    raw_id = "Unknown"

            display_name = item.get("name", raw_id)
            val = item.get("value", self.model.get_value(raw_id))
            unit = item.get("unit", self.model.get_unit(raw_id))

            font_value_override = item.get("font_value", None)
            font_name_override = item.get("font_name", None)
            value_padx = item.get("value_padx", 5)
            value_pady = item.get("value_pady", 5)
            name_padx = item.get("name_padx", 5)
            name_pady = item.get("name_pady", (0, 5))
            bg_color = item.get("bg_color", COLORS["panel_bg"])

            # If user sets "width"/"height" in the dict, we pass them along
            width = item.get("width", 200)
            height = item.get("height", 100)

            dp = DisplayPanel(
                self,
                panel_id=raw_id,
                name=display_name,
                value=val,
                unit=unit,
                model=self.model,
                font_value_override=font_value_override,
                font_name_override=font_name_override,
                value_padx=value_padx,
                value_pady=value_pady,
                name_padx=name_padx,
                name_pady=name_pady,
                width=width,
                height=height,
                bg_color=bg_color
            )
            dp.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
            self.panels[raw_id] = dp

        # 4) string -> param ID
        elif isinstance(item, str):
            panel_id = item
            val = self.model.get_value(panel_id)
            unit = self.model.get_unit(panel_id)

            # Use default size if not specified
            dp = DisplayPanel(
                self,
                panel_id=panel_id,
                name=panel_id,
                value=val,
                unit=unit,
                model=self.model
            )
            dp.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
            self.panels[panel_id] = dp
        else:
            label = tk.Label(
                self,
                text=f"Unknown item: {item}",
                bg=self['bg'],
                fg="white"
            )
            label.pack(side=tk.TOP, fill=tk.BOTH, padx=4, pady=4)

    def _create_grid(self, two_d_items):
        grid_frame = tk.Frame(self, bg=self['bg'])
        grid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        for row_idx, row_items in enumerate(two_d_items):
            col_idx = 0
            while col_idx < len(row_items):
                sub_item = row_items[col_idx]
                rowspan = 1
                colspan = 1

                if isinstance(sub_item, dict):
                    raw_id = sub_item.get("id", None)
                    if not raw_id or raw_id == "Unknown":
                        raw_name = sub_item.get("name")
                        if raw_name in self.model.values:
                            raw_id = raw_name
                        else:
                            raw_id = "Unknown"

                    disp_name = sub_item.get("name", raw_id)
                    val = sub_item.get("value", self.model.get_value(raw_id))
                    unit = sub_item.get("unit", self.model.get_unit(raw_id))

                    font_value_override = sub_item.get("font_value", None)
                    font_name_override = sub_item.get("font_name", None)
                    value_padx = sub_item.get("value_padx", 5)
                    value_pady = sub_item.get("value_pady", 5)
                    name_padx = sub_item.get("name_padx", 5)
                    name_pady = sub_item.get("name_pady", (0, 5))
                    width = sub_item.get("width", 200)
                    height = sub_item.get("height", 100)
                    bg_color = sub_item.get("bg_color", COLORS["panel_bg"])

                    if "rowspan" in sub_item:
                        rowspan = sub_item["rowspan"]
                    if "colspan" in sub_item:
                        colspan = sub_item["colspan"]

                    dp = DisplayPanel(
                        grid_frame,
                        panel_id=raw_id,
                        name=disp_name,
                        value=val,
                        unit=unit,
                        model=self.model,
                        font_value_override=font_value_override,
                        font_name_override=font_name_override,
                        value_padx=value_padx,
                        value_pady=value_pady,
                        name_padx=name_padx,
                        name_pady=name_pady,
                        width=width,
                        height=height,
                        bg_color=bg_color
                    )
                    dp.grid(row=row_idx, column=col_idx,
                            rowspan=rowspan, columnspan=colspan,
                            padx=4, pady=4, sticky='nsew')
                    self.panels[raw_id] = dp

                elif isinstance(sub_item, str):
                    val = self.model.get_value(sub_item)
                    unit = self.model.get_unit(sub_item)
                    dp = DisplayPanel(
                        grid_frame,
                        panel_id=sub_item,
                        name=sub_item,
                        value=val,
                        unit=unit,
                        model=self.model
                    )
                    dp.grid(row=row_idx, column=col_idx,
                            rowspan=rowspan, columnspan=colspan,
                            padx=4, pady=4, sticky='nsew')
                    self.panels[sub_item] = dp
                else:
                    lbl = tk.Label(
                        grid_frame,
                        text=f"Unknown sub-item: {sub_item}",
                        bg=self['bg'],
                        fg="white"
                    )
                    lbl.grid(row=row_idx, column=col_idx,
                             padx=4, pady=4, sticky='nsew')

                col_idx += colspan

        total_rows = len(two_d_items)
        max_cols = max(len(r) for r in two_d_items if isinstance(r, list))
        for r in range(total_rows):
            grid_frame.rowconfigure(r, weight=1)
        for c in range(max_cols):
            grid_frame.columnconfigure(c, weight=1)

    def update_panel_value(self, panel_id, new_value):
        # First check if we have this panel directly
        if panel_id in self.panels:
            self.panels[panel_id].update_value(new_value)
            return True
            
        # Then check for nested panels
        for child in self.winfo_children():
            if isinstance(child, PanelGroup):
                if child.update_panel_value(panel_id, new_value):
                    return True
                    
        # Then check frames that might contain DisplayPanels    
        for child in self.winfo_children():
            if isinstance(child, tk.Frame) and not isinstance(child, PanelGroup):
                for subchild in child.winfo_children():
                    if isinstance(subchild, DisplayPanel) and subchild.panel_id == panel_id:
                        subchild.update_value(new_value)
                        return True
        
        return False

# --------------------------------------------------------------------------
# EventScreen
# --------------------------------------------------------------------------
class EventScreen:
    """
    Contains a left PanelGroup and a right PanelGroup for a specific driving event.
    """
    def __init__(self, event_name, model, parent, layout):
        self.event_name = event_name
        self.model = model
        self.parent = parent
        self.left_group = None
        self.right_group = None
        self.create_panels(layout)

    def create_panels(self, layout):
        left_items = layout.get("left", [])
        right_items = layout.get("right", [])

        self.left_group = PanelGroup(self.parent, self.model, left_items)
        self.right_group = PanelGroup(self.parent, self.model, right_items)

        self.left_group.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self.right_group.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")

        self.parent.grid_columnconfigure(0, weight=1)
        self.parent.grid_columnconfigure(1, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)

    def update_value(self, panel_id, value):
        updated_left = False
        updated_right = False
        
        if self.left_group:
            updated_left = self.left_group.update_panel_value(panel_id, value)
        if self.right_group:
            updated_right = self.right_group.update_panel_value(panel_id, value)
            
        return updated_left or updated_right


# --------------------------------------------------------------------------
# Display - main application window
# --------------------------------------------------------------------------
class Display(tk.Tk):
    """
    The main application window (View).
    """
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.title("Formula Student Car Display")

        # Window size
        self.geometry("800x480")
        self.resizable(False, False)
        self.configure(bg=COLORS["background"])

        # Main container
        self.main_frame = tk.Frame(self, bg=COLORS["background"])
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create various screens, all initially hidden
        self.header_frame = self.create_header_frame(self.main_frame)
        self.header_frame.config(height=50)
        self.header_frame.pack_propagate(False)
        self.header_frame.pack(side=tk.TOP, fill=tk.X)

        # Main driving screen (event screens)
        self.split_frame = tk.Frame(self.main_frame, bg=COLORS["background"])
        self.split_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Menu screens
        self.menu_main_frame = self.create_menu_frame(self.main_frame, "Menu Screen")
        self.menu_debug_frame = self.create_menu_frame(self.main_frame, "Debugging Screen")
        self.menu_ecu_frame = self.create_menu_frame(self.main_frame, "ECU Versions and Activity")
        self.menu_tsoff_frame = self.create_menu_frame(self.main_frame, "TS OFF Screen")
        
        # Create menu button frames
        self.menu_main_buttons = self.create_main_menu_buttons(self.menu_main_frame)
        self.menu_debug_content = self.create_debug_screen(self.menu_debug_frame)
        self.menu_ecu_content = self.create_ecu_screen(self.menu_ecu_frame)
        
        # Hide all menu frames initially
        self.menu_main_frame.pack_forget()
        self.menu_debug_frame.pack_forget()
        self.menu_ecu_frame.pack_forget()
        self.menu_tsoff_frame.pack_forget()

        # Initialize current screen and set up initial event screen
        self.current_screen = None
        self.current_menu = None
        self.create_event_screen(self.model.current_event)
        
        # Button references (will be initialized later)
        self.button1 = None
        self.button2 = None
        self.button3 = None
        self.button4 = None
        self.button5 = None
        self.button6 = None
        self.button7 = None
        self.button8 = None
        
        # Button lists for menu navigation
        self.main_menu_button_list = []
        self.main_menu_frames = []
        self.event_menu_button_list = []
        self.event_menu_frames = []
        self.active_button = 0  # Track active button index

        # Blink logo for visual feedback
        self.logo_blink_state = True
        self.after(1000, self.toggle_logo)
        self.focus_set()

    def create_header_frame(self, parent):
        header_frame = tk.Frame(parent, bg=COLORS["header_bg"], highlightthickness=0)
        image_path = os.path.join("Resources", "HAWKS_LOGO.png")
        self.logo_image_full = None
        self.logo_image_blank = None
        self.logo_label = None

        if os.path.exists(image_path):
            original_image = Image.open(image_path).convert("RGBA")
            resized_image = original_image.resize((45, 45), Image.Resampling.LANCZOS)
            self.logo_image_full = ImageTk.PhotoImage(resized_image)
            from PIL import Image as PILImage
            blank_img = PILImage.new("RGBA", resized_image.size, COLORS["header_bg"])
            self.logo_image_blank = ImageTk.PhotoImage(blank_img)
            self.logo_label = tk.Label(header_frame, image=self.logo_image_full,
                                       bg=COLORS["header_bg"], borderwidth=0)
            self.logo_label.pack(side=tk.LEFT, padx=(10, 10))
        else:
            self.logo_label = tk.Label(
                header_frame,
                text="[LOGO]",
                fg=COLORS["text_primary"],
                bg=COLORS["header_bg"],
                font=("Segoe UI", 16)
            )
            self.logo_label.pack(side=tk.LEFT, padx=(10, 10))

        self.mode_label = tk.Label(
            header_frame,
            text=f"AMI: Manual Driving - {self.model.current_event.capitalize()}",
            fg=COLORS["text_primary"],
            bg=COLORS["header_bg"],
            font=("Segoe UI", 26)
        )
        self.mode_label.pack(side=tk.LEFT, padx=(5, 0))
        return header_frame

    def toggle_logo(self):
        """Blink the logo for visual feedback"""
        if self.logo_label and self.logo_image_full and self.logo_image_blank:
            if self.logo_blink_state:
                self.logo_label.config(image=self.logo_image_blank)
            else:
                self.logo_label.config(image=self.logo_image_full)
            self.logo_blink_state = not self.logo_blink_state
        self.after(1500, self.toggle_logo)

    def create_menu_frame(self, parent, title="Menu"):
        """Create a base frame for a menu screen with header"""
        frame = tk.Frame(parent, bg=COLORS["menu_bg"])
        
        # Add the menu title
        title_frame = tk.Frame(frame, bg=COLORS["header_bg"], height=40)
        title_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        title_label = tk.Label(
            title_frame, 
            text=title,
            font=("Segoe UI", 18, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["header_bg"]
        )
        title_label.pack(side=tk.TOP, pady=5)
        
        return frame

    def create_main_menu_buttons(self, parent):
        """Create buttons for the main menu screen"""
        container = tk.Frame(parent, bg=COLORS["menu_bg"])
        container.place(relx=0.5, rely=0.5, anchor="center")
        
        buttons = []
        frames = []  # Store frames for highlighting
        
        # Menu options based on the diagram
        menu_options = [
            "Change Max Torque Setting",
            "Change Max Power",
            "Recalibrate Throttle Position: Set upper",
            "Recalibrate Throttle Position: Set lower",
            "Display Debugging Screen",
            "Display ECU Version Screen",
            "Display TS OFF"
        ]
        
        # Action bindings for menu buttons
        actions = [
            lambda: self.show_debug_message("Changing Max Torque Setting"),
            lambda: self.show_debug_message("Changing Max Power"),
            lambda: self.show_debug_message("Calibrating upper throttle"),
            lambda: self.show_debug_message("Calibrating lower throttle"),
            lambda: self.show_menu_screen(self.menu_debug_frame),
            lambda: self.show_menu_screen(self.menu_ecu_frame),
            lambda: self.show_menu_screen(self.menu_tsoff_frame)
        ]
        
        # Create buttons with highlight frames
        for i, (text, action) in enumerate(zip(menu_options, actions)):
            highlight_frame = tk.Frame(container, bg=COLORS["menu_bg"], bd=2)
            highlight_frame.pack(pady=10)
            frames.append(highlight_frame)
            
            button = tk.Button(
                highlight_frame,
                text=text,
                font=FONT_BUTTON,
                fg="#ffffff",
                bg="#333333",
                activebackground="#444444",
                width=35,
                borderwidth=0,
                command=action
            )
            button.pack()
            buttons.append(button)
            
            # Store in the class for accessibility by controller
            if i == 0:
                self.button1 = button
            elif i == 1:
                self.button2 = button
            elif i == 2:
                self.button3 = button
            elif i == 3:
                self.button4 = button
            elif i == 4:
                self.button5 = button
            elif i == 5:
                self.button6 = button
            elif i == 6:
                self.button7 = button
        
        # Add back button
        highlight_frame = tk.Frame(container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame.pack(pady=10)
        frames.append(highlight_frame)
        
        back_button = tk.Button(
            highlight_frame,
            text="Back to Driving Screen",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#555555",
            activebackground="#666666",
            width=30,
            borderwidth=0,
            command=self.return_to_event_screen
        )
        back_button.pack()
        buttons.append(back_button)
        self.button8 = back_button
        
        self.main_menu_button_list = buttons
        self.main_menu_frames = frames
        self.active_button = 0  # Initialize first button as active
        
        # Highlight the first button
        self._highlight_main_menu_button(0)
        
        return container

    def create_debug_screen(self, parent):
        """Create the debugging screen layout"""
        content_frame = tk.Frame(parent, bg=COLORS["background"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Split into left and right sections
        left_frame = tk.Frame(content_frame, bg=COLORS["background"])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        right_frame = tk.Frame(content_frame, bg=COLORS["background"])
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Debugging Data section (left)
        debug_label = tk.Label(
            left_frame,
            text="Debugging Data",
            font=FONT_HEADER,
            fg=COLORS["text_primary"],
            bg=COLORS["background"]
        )
        debug_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Create a scrollable text widget for debug data
        debug_text = tk.Text(
            left_frame,
            font=("Segoe UI", 12),
            fg=COLORS["text_primary"],
            bg=COLORS["panel_bg"],
            height=15,
            width=40
        )
        debug_text.pack(fill=tk.BOTH, expand=True)
        
        # Add some placeholder text
        debug_text.insert(tk.END, "Brake Pressure Front: 0\n")
        debug_text.insert(tk.END, "Brake Pressure Rear: 0\n")
        debug_text.insert(tk.END, "Throttle Position: 0\n")
        debug_text.insert(tk.END, "Throttle Position Lower: 0\n")
        debug_text.insert(tk.END, "Throttle Position Upper: 0\n")
        debug_text.insert(tk.END, "Steering Wheel Angle: 0\n")
        debug_text.insert(tk.END, "Competition Datalogger Active: No\n")
        debug_text.config(state=tk.DISABLED)  # Make read-only
        
        # Right frame (status panels)
        # Create telemetry panels on the right using PanelGroup
        telemetry_panels = [
            [{"id": "Accu Temp", "name": "Accu Temp", "font_value": ("Segoe UI", 36, "bold"), 
              "bg_color": COLORS["panel_bg"], "width": 200, "height": 100}],
            [{"id": "Lowest Cell", "name": "Lowest Cell", "font_value": ("Segoe UI", 36, "bold"),
              "bg_color": COLORS["panel_bg"], "width": 200, "height": 100}],
            [
                [{"id": "Inverter L Temp", "name": "Inverter L Temp", "font_value": ("Segoe UI", 24, "bold"),
                 "bg_color": COLORS["panel_bg"], "width": 100, "height": 100}],
                [{"id": "Inverter R Temp", "name": "Inverter R Temp", "font_value": ("Segoe UI", 24, "bold"),
                 "bg_color": COLORS["panel_bg"], "width": 100, "height": 100}]
            ],
            [
                [{"id": "Motor L Temp", "name": "Motor L Temp", "font_value": ("Segoe UI", 24, "bold"),
                 "bg_color": COLORS["panel_bg"], "width": 100, "height": 100}],
                [{"id": "Motor R Temp", "name": "Motor R Temp", "font_value": ("Segoe UI", 24, "bold"),
                 "bg_color": COLORS["panel_bg"], "width": 100, "height": 100}]
            ]
        ]
        
        debug_panels = PanelGroup(right_frame, self.model, telemetry_panels)
        debug_panels.pack(fill=tk.BOTH, expand=True)
        
        # Back button at the bottom
        back_frame = tk.Frame(parent, bg=COLORS["menu_bg"], height=50)
        back_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        back_button = tk.Button(
            back_frame,
            text="Back to Main Menu",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#555555",
            activebackground="#666666",
            width=20,
            command=lambda: self.show_menu_screen(self.menu_main_frame)
        )
        back_button.pack(side=tk.RIGHT, padx=20, pady=10)
        
        return content_frame

    def create_ecu_screen(self, parent):
        """Create the ECU version screen layout"""
        content_frame = tk.Frame(parent, bg=COLORS["background"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title for ECU versions
        ecu_title = tk.Label(
            content_frame,
            text="ECU Versions on the CAN Busses and their Software Versions",
            font=FONT_HEADER,
            fg=COLORS["text_primary"],
            bg=COLORS["background"]
        )
        ecu_title.pack(anchor=tk.W, pady=(10, 20))
        
        # Create a table-like display for ECU versions
        ecu_frame = tk.Frame(content_frame, bg=COLORS["panel_bg"])
        ecu_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Headers
        headers = ["ECU Name", "Software Version", "Status"]
        for i, header in enumerate(headers):
            header_label = tk.Label(
                ecu_frame,
                text=header,
                font=("Segoe UI", 14, "bold"),
                fg=COLORS["text_secondary"],
                bg=COLORS["panel_bg"]
            )
            header_label.grid(row=0, column=i, sticky="w", padx=10, pady=5)
        
        # Sample ECU data - would be populated from CAN signals
        ecu_data = [
            ("VCU", "1.2.5", "Online"),
            ("AMS", "2.0.1", "Online"),
            ("DIU", "1.3.0", "Online"),
            ("ASPU", "1.1.2", "Online"),
            ("ASCU", "1.0.3", "Online"),
            ("DRS", "1.4.1", "Online")
        ]
        
        for i, (name, version, status) in enumerate(ecu_data, start=1):
            name_label = tk.Label(
                ecu_frame,
                text=name,
                font=("Segoe UI", 12),
                fg=COLORS["text_primary"],
                bg=COLORS["panel_bg"]
            )
            name_label.grid(row=i, column=0, sticky="w", padx=10, pady=5)
            
            version_label = tk.Label(
                ecu_frame,
                text=version,
                font=("Segoe UI", 12),
                fg=COLORS["text_primary"],
                bg=COLORS["panel_bg"]
            )
            version_label.grid(row=i, column=1, sticky="w", padx=10, pady=5)
            
            status_color = COLORS["accent_normal"] if status == "Online" else COLORS["accent_critical"]
            status_label = tk.Label(
                ecu_frame,
                text=status,
                font=("Segoe UI", 12),
                fg=status_color,
                bg=COLORS["panel_bg"]
            )
            status_label.grid(row=i, column=2, sticky="w", padx=10, pady=5)
        
        # Configure grid weights
        ecu_frame.columnconfigure(0, weight=1)
        ecu_frame.columnconfigure(1, weight=1)
        ecu_frame.columnconfigure(2, weight=1)
        
        # Back button
        back_frame = tk.Frame(parent, bg=COLORS["menu_bg"], height=50)
        back_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        back_button = tk.Button(
            back_frame,
            text="Back to Main Menu",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#555555",
            activebackground="#666666",
            width=20,
            command=lambda: self.show_menu_screen(self.menu_main_frame)
        )
        back_button.pack(side=tk.RIGHT, padx=20, pady=10)
        
        return content_frame

    def show_debug_message(self, message):
        """Show a debug message/action in a popup"""
        popup = tk.Toplevel(self)
        popup.title("Action")
        popup.geometry("300x150")
        popup.configure(bg=COLORS["panel_bg"])
        
        message_label = tk.Label(
            popup,
            text=message,
            font=("Segoe UI", 14),
            fg=COLORS["text_primary"],
            bg=COLORS["panel_bg"],
            wraplength=280
        )
        message_label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        close_button = tk.Button(
            popup,
            text="Close",
            font=("Segoe UI", 12),
            command=popup.destroy
        )
        close_button.pack(pady=10)
        
        # Center the popup on the screen
        popup.update_idletasks()
        width = popup.winfo_width()
        height = popup.winfo_height()
        x = (self.winfo_width() // 2) - (width // 2)
        y = (self.winfo_height() // 2) - (height // 2)
        popup.geometry(f"+{x}+{y}")
        
        # Make the popup modal
        popup.transient(self)
        popup.grab_set()
        self.wait_window(popup)

    def show_menu_screen(self, menu_frame):
        """Show one of the menu screens"""
        # Hide all frames first
        self.split_frame.pack_forget()
        self.header_frame.pack_forget()
        self.menu_main_frame.pack_forget()
        self.menu_debug_frame.pack_forget()
        self.menu_ecu_frame.pack_forget()
        self.menu_tsoff_frame.pack_forget()
        
        # Show the requested menu frame
        menu_frame.pack(fill=tk.BOTH, expand=True)
        self.current_menu = menu_frame

    def return_to_event_screen(self):
        """Return to the main event screen from any menu"""
        # Hide all menu frames
        self.menu_main_frame.pack_forget()
        self.menu_debug_frame.pack_forget()
        self.menu_ecu_frame.pack_forget()
        self.menu_tsoff_frame.pack_forget()
        
        # Show the main interface
        self.header_frame.pack(side=tk.TOP, fill=tk.X)
        self.split_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def create_event_screen(self, event_name):
        """Create the appropriate event screen based on the event name"""
        # Clear existing
        for child in self.split_frame.winfo_children():
            child.destroy()

        # Build layouts based on the diagram
        if event_name == "endurance":
            layout = self._build_endurance_layout()
        elif event_name in ["autocross", "skidpad", "acceleration"]:
            layout = self._build_autocross_layout(event_name)
        else:
            # Fallback to a generic layout from the model
            layout = self._build_generic_layout(event_name)
            
        self.current_screen = EventScreen(event_name, self.model, self.split_frame, layout)
        self.mode_label.config(text=f"AMI: Manual Driving - {event_name.capitalize()}")

    def _build_endurance_layout(self):
        """Create the endurance screen layout based on the diagram"""
        return {
            "left": [
                # Big SOC panel (top left)
                {"id": "SOC", "name": "SOC %", 
                 "font_value": ("Segoe UI", 56, "bold"),
                 "font_name": ("Segoe UI", 36),
                 "value_pady": (13, 0),
                 "width": 400, "height": 150,
                 "bg_color": COLORS["panel_bg"]},
                
                # Lowest Cell panel (bottom left)
                {"id": "Lowest Cell", "name": "Lowest Cell",
                 "font_value": ("Segoe UI", 46, "bold"),
                 "font_name": ("Segoe UI", 22),
                 "value_pady": (20, 0),
                 "bg_color": COLORS["panel_bg"]}
            ],
            "right": [
                # Top right panels (TC, TV, Max Torque)
                [
                    [{"id": "TC", "name": "TC",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12)}],
                    [{"id": "TV", "name": "TV",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12)}],
                    [{"id": "Max Torque", "name": "Max Torque",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12)}]
                ],
                
                # DRS and Accu Temp row
                [
                    {"id": "DRS", "name": "DRS",
                     "font_value": ("Segoe UI", 28, "bold"),
                     "font_name": ("Segoe UI", 12)},
                    {"id": "Accu Temp", "name": "Accu Temp",
                     "font_value": ("Segoe UI", 36, "bold"),
                     "font_name": ("Segoe UI", 12),
                     "colspan": 2,
                     "bg_color": COLORS["panel_bg"]}
                ],
                
                # Temperature grid (bottom right)
                [
                    [{"id": "Motor L Temp", "name": "Motor L Temp",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12),
                      "bg_color": COLORS["panel_bg"]},
                     {"id": "Motor R Temp", "name": "Motor R Temp",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12),
                      "bg_color": COLORS["panel_bg"]}],
                    [{"id": "Inverter L Temp", "name": "Inverter L Temp",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12),
                      "bg_color": COLORS["panel_bg"]},
                     {"id": "Inverter R Temp", "name": "Inverter R Temp",
                      "font_value": ("Segoe UI", 28, "bold"),
                      "font_name": ("Segoe UI", 12),
                      "bg_color": COLORS["panel_bg"]}]
                ]
            ]
        }

    def _build_autocross_layout(self, event_name):
        """Create the autocross/skidpad/acceleration screen layout based on the diagram"""
        return {
            "left": [
                # DRS indicator (top)
                {"id": "DRS", "name": "DRS Indicator",
                 "font_value": ("Segoe UI", 50, "bold"),
                 "font_name": ("Segoe UI", 30),
                 "width": 200, "height": 150},
                
                # Vehicle control modes (middle)
                [
                    [{"id": "Traction Control Mode", "name": "Traction Control Mode",
                      "font_value": ("Segoe UI", 20, "bold"),
                      "font_name": ("Segoe UI", 10)}],
                    [{"id": "Torque Vectoring Mode", "name": "Torque Vectoring Mode",
                      "font_value": ("Segoe UI", 20, "bold"),
                      "font_name": ("Segoe UI", 10)}],
                    [{"id": "Max Torque", "name": "Max Torque",
                      "font_value": ("Segoe UI", 20, "bold"),
                      "font_name": ("Segoe UI", 10)}]
                ]
            ],
            "right": [
                # Lowest Cell and Accu Temp (top right)
                [
                    [{"id": "Lowest Cell", "name": "Lowest Cell",
                      "font_value": ("Segoe UI", 42, "bold"),
                      "font_name": ("Segoe UI", 22),
                      "value_pady": (20, 0),
                      "bg_color": COLORS["panel_bg"]},
                     {"id": "Accu Temp", "name": "Accu Temp",
                      "font_value": ("Segoe UI", 42, "bold"),
                      "font_name": ("Segoe UI", 22),
                      "value_pady": (20, 0),
                      "value_padx": 37,
                      "bg_color": COLORS["panel_bg"]}]
                ],
                
                # Temperature grid (bottom right)
                [
                    [{"id": "Motor L Temp", "name": "Motor L Temp",
                      "font_value": ("Segoe UI", 32, "bold"),
                      "font_name": ("Segoe UI", 16),
                      "value_pady": (10, 0),
                      "bg_color": COLORS["panel_bg"]},
                     {"id": "Motor R Temp", "name": "Motor R Temp",
                      "font_value": ("Segoe UI", 32, "bold"),
                      "font_name": ("Segoe UI", 16),
                      "value_pady": (10, 0),
                      "bg_color": COLORS["panel_bg"]}],
                    [{"id": "Inverter L Temp", "name": "Inverter L Temp",
                      "font_value": ("Segoe UI", 32, "bold"),
                      "font_name": ("Segoe UI", 16),
                      "value_pady": (10, 0),
                      "bg_color": COLORS["panel_bg"]},
                     {"id": "Inverter R Temp", "name": "Inverter R Temp",
                      "font_value": ("Segoe UI", 32, "bold"),
                      "font_name": ("Segoe UI", 16),
                      "value_pady": (10, 0),
                      "bg_color": COLORS["panel_bg"]}]
                ]
            ]
        }

    def _build_generic_layout(self, event_name):
        """Create a generic layout from the model's event_screens"""
        params = self.model.event_screens.get(event_name, [])
        midpoint = len(params) // 2
        left_params = params[:midpoint]
        right_params = params[midpoint:]
        return {
            "left": left_params,
            "right": right_params
        }

    def menu_pop(self):
        """Toggle between main screen and main menu"""
        if self.menu_main_frame.winfo_ismapped() or self.menu_debug_frame.winfo_ismapped() or \
           self.menu_ecu_frame.winfo_ismapped() or self.menu_tsoff_frame.winfo_ismapped():
            # Return to main screen if we're in any menu
            self.return_to_event_screen()
        else:
            # Go to main menu
            self.split_frame.pack_forget()
            self.header_frame.pack_forget()
            self.show_menu_screen(self.menu_main_frame)

    def _highlight_main_menu_button(self, button_index):
        """Highlight a specific button in the menu"""
        # Reset all frames to default
        for frame in self.main_menu_frames:
            frame.config(bg=COLORS["menu_bg"])
            
        # Highlight the selected button
        if 0 <= button_index < len(self.main_menu_frames):
            self.main_menu_frames[button_index].config(bg=COLORS["accent_normal"])
            self.active_button = button_index

    def handle_value_update(self, panel_id, value):
        """Update a value in the current screen"""
        if self.current_screen:
            self.current_screen.update_value(panel_id, value)