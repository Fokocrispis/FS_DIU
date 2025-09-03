import os
import tkinter as tk
import logging
import socket
import math
from PIL import Image, ImageTk

# --------------------------------------------------------------------------
# Color and style settings
# --------------------------------------------------------------------------
COLORS = {
    "background": "#0a0c0f",
    "panel_bg": "#0a0c0f",
    "panel_active": "#1b1b1b",  
    "border": "#666666",
    "text_primary": "#ffffff",
    "text_secondary": "#6eb3f3",
    "accent_critical": "#ff0000",
    "accent_warning": "#ffcc00",
    "accent_normal": "#00ff00",
    "header_bg": "#0a0c0f",
    "menu_bg": "#0a0c0f",
    "R2D_active":   "#0400ff"
}

FONT_VALUE = ("Cousine", 50, "bold")
FONT_NAME = ("Segoe UI", 10, "bold")
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
            highlightthickness=0,
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
        try:
            # Convert value to float for comparison
            num_val = float(str(val).replace("%", "").replace("°C", "").replace("V", ""))
            
            # SOC critical thresholds
            if self.panel_id == "SOC":
                if num_val < 20:
                    return COLORS["accent_critical"]
                elif num_val < 40:
                    return COLORS["accent_warning"]
                else:
                    return COLORS["text_primary"]
            
            # Temperature critical thresholds
            elif "Temp" in self.panel_id:
                if num_val > 80:
                    return COLORS["accent_critical"]
                elif num_val > 60:
                    return COLORS["accent_warning"]
                else:
                    return COLORS["text_primary"]
            
            # DRS status
            elif self.panel_id == "DRS":
                if str(val).lower() == "on" or str(val) == "1":
                    return COLORS["accent_normal"]
                else:
                    return COLORS["text_primary"]
            
            # Default color
            else:
                return COLORS["text_primary"]
                
        except:
            # If value can't be converted to float, return default color
            return COLORS["text_primary"]
    
    def on_resize(self, event=None):
        """Handle panel resize"""
        self.adjust_font_size()
    
    def adjust_font_size(self):
        """Adjust font size to fit panel"""
        try:
            # Get available space
            panel_width = self.winfo_width()
            panel_height = self.winfo_height()
            
            if panel_width <= 1 or panel_height <= 1:
                return
            
            # Reserve space for labels
            value_height = int(panel_height * 0.6)
            name_height = int(panel_height * 0.3)
            
            # Adjust font sizes based on panel size
            value_font_size = max(12, min(self.initial_font_value[1], value_height // 2))
            name_font_size = max(10, min(self.initial_font_name[1], name_height // 2))
            
            # Update fonts
            self.font_value = (self.initial_font_value[0], value_font_size, self.initial_font_value[2])
            self.font_name = (self.initial_font_name[0], name_font_size)
            
            self.value_label.config(font=self.font_value)
            self.name_label.config(font=self.font_name)
            
        except Exception as e:
            # Ignore resize errors during initialization
            pass


# --------------------------------------------------------------------------
# PanelGroup - container that can hold multiple DisplayPanels or sub-groups
# --------------------------------------------------------------------------
class PanelGroup(tk.Frame):
    """
    Manages a collection of DisplayPanels.
    If a dict has "width"/"height", we pass them to DisplayPanel so it becomes static.
    """
    def __init__(self, parent, model, items, group_bg=COLORS["panel_bg"]):
        super().__init__(parent, bg=group_bg)
        self.model = model
        self.panels = {}  # Dictionary to store panels by ID

        self.pack_propagate(False)

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

        # 4) dict with "type": "progress_bar" -> VerticalProgressBar
        elif isinstance(item, dict) and item.get("type") == "progress_bar":
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
            
            min_value = item.get("min_value", 0)
            max_value = item.get("max_value", 100)
            width = item.get("width", 60)
            height = item.get("height", 200)
            bar_color = item.get("bar_color", None)
            bg_color = item.get("bg_color", COLORS["panel_bg"])

            pb = VerticalProgressBar(
                self,
                panel_id=raw_id,
                name=display_name,
                value=val,
                unit=unit,
                model=self.model,
                min_value=min_value,
                max_value=max_value,
                width=width,
                height=height,
                bar_color=bar_color,
                bg_color=bg_color
            )
            pb.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=4, pady=4)
            self.panels[raw_id] = pb

        # 5) string -> simple DisplayPanel
        elif isinstance(item, str):
            val = self.model.get_value(item)
            unit = self.model.get_unit(item)
            dp = DisplayPanel(self, panel_id=item, name=item, value=val, unit=unit, model=self.model)
            dp.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
            self.panels[item] = dp

    def _create_grid(self, two_d_items):
        """Create a grid of panels from a 2D list"""
        grid_frame = tk.Frame(self, bg=self['bg'])
        grid_frame.pack(fill=tk.BOTH, expand=True)

        for row_idx, row in enumerate(two_d_items):
            if not isinstance(row, list):
                continue
            col_idx = 0
            for sub_item in row:
                rowspan = 1
                colspan = 1

                if isinstance(sub_item, dict):
                    raw_id = sub_item.get("id", "Unknown")
                    if raw_id == "Unknown":
                        raw_name = sub_item.get("name")
                        if raw_name and raw_name in self.model.values:
                            raw_id = raw_name

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
                    
        # Then check frames that might contain DisplayPanels or VerticalProgressBars
        for child in self.winfo_children():
            if isinstance(child, tk.Frame) and not isinstance(child, PanelGroup):
                for subchild in child.winfo_children():
                    if isinstance(subchild, (DisplayPanel, VerticalProgressBar)) and subchild.panel_id == panel_id:
                        subchild.update_value(new_value)
                        return True
        
        return False

# --------------------------------------------------------------------------
# VerticalProgressBar - shows a vertical progress bar for values like pedal position
# --------------------------------------------------------------------------
class VerticalProgressBar(tk.Frame):
    """
    A vertical progress bar that shows a value as a filled bar.
    Useful for pedal positions, brake pressure, etc.
    """
    def __init__(self, parent, panel_id, name, value, unit, model, 
                 min_value=0, max_value=100, width=60, height=200, 
                 bar_color=None, bg_color=None):
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
        self.min_value = min_value
        self.max_value = max_value
        self.bar_color = bar_color if bar_color else COLORS["accent_normal"]
        
        # Force static size
        self.config(width=width, height=height)
        self.pack_propagate(False)
        
        # Title label
        self.title_label = tk.Label(
            self,
            text=name,
            font=("Segoe UI", 12, "bold"),
            fg=COLORS["text_primary"],
            bg=self["bg"]
        )
        self.title_label.pack(pady=(5, 2))
        
        # Progress bar container
        self.bar_frame = tk.Frame(
            self,
            bg=COLORS["background"],
            highlightthickness=1,
            highlightcolor=COLORS["border"],
            width=width-20,
            height=height-80
        )
        self.bar_frame.pack(pady=5)
        self.bar_frame.pack_propagate(False)
        
        # Progress bar fill
        self.bar_fill = tk.Frame(
            self.bar_frame,
            bg=self.bar_color
        )
        
        # Value label
        self.value_label = tk.Label(
            self,
            text=f"{value}{(' ' + self.unit) if self.unit else ''}",
            font=("Segoe UI", 10, "bold"),
            fg=COLORS["text_primary"],
            bg=self["bg"]
        )
        self.value_label.pack(pady=(2, 5))
        
        # Initialize bar
        self.update_value(value)
    
    def update_value(self, new_value):
        """Update the progress bar and value display"""
        try:
            # Convert value to number
            num_value = float(str(new_value).replace("%", "").replace("°C", "").replace("V", ""))
            
            # Clamp value to range
            clamped_value = max(self.min_value, min(self.max_value, num_value))
            
            # Calculate percentage
            percentage = (clamped_value - self.min_value) / (self.max_value - self.min_value)
            
            # Update bar height
            bar_height = int(percentage * (self.bar_frame.winfo_height() - 2))
            
            # Remove old bar
            self.bar_fill.place_forget()
            
            # Place new bar from bottom
            if bar_height > 0:
                self.bar_fill.place(
                    x=1, 
                    y=self.bar_frame.winfo_height() - bar_height - 1,
                    width=self.bar_frame.winfo_width() - 2,
                    height=bar_height
                )
            
            # Update value label
            self.value_label.config(
                text=f"{new_value}{(' ' + self.unit) if self.unit else ''}",
                fg=self.get_value_color(num_value)
            )
            
        except Exception as e:
            # If conversion fails, just update the label
            self.value_label.config(text=f"{new_value}{(' ' + self.unit) if self.unit else ''}")
    
    def get_value_color(self, val):
        """Get color based on value and panel type"""
        try:
            # Pedal position colors
            if "pedal" in self.panel_id.lower() or "apps" in self.panel_id.lower():
                if val > 80:
                    return COLORS["accent_critical"]
                elif val > 60:
                    return COLORS["accent_warning"]
                else:
                    return COLORS["text_primary"]
            
            # Brake pressure colors
            elif "brake" in self.panel_id.lower() or "bp" in self.panel_id.lower():
                if val > 90:
                    return COLORS["accent_critical"]
                elif val > 70:
                    return COLORS["accent_warning"]
                else:
                    return COLORS["text_primary"]
            
            # Default
            else:
                return COLORS["text_primary"]
                
        except:
            return COLORS["text_primary"]

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

        # Hide mouse cursor
        self.config(cursor="none")

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
        self.menu_tsoff_frame = self.create_menu_frame(self.main_frame, "Testing Screen")
        
        # Create menu button frames
        self.menu_main_buttons = self.create_main_menu_buttons(self.menu_main_frame)
        self.menu_debug_content = self.create_debug_screen(self.menu_debug_frame)
        self.menu_ecu_content = self.create_ecu_screen(self.menu_ecu_frame)
        self.menu_tsoff_content = self.create_tsoff_screen(self.menu_tsoff_frame)
        
        # Hide all menu frames initially
        self.menu_main_frame.pack_forget()
        self.menu_debug_frame.pack_forget()
        self.menu_ecu_frame.pack_forget()
        self.menu_tsoff_frame.pack_forget()

        # Initialize current screen and set up initial event screen
        self.current_screen = None
        self.current_menu = None
        #self.create_event_screen(self.model.current_event)
        self.show_tsoff_screen() # Start with TS OFF screen
        
        # State tracking to prevent flickering
        self.last_r2d_state = None
        
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
        self.blinking = False
        self.is_logo_visible = True

        # Start value update loop
        self.update_values_from_model()

        # Bind model callbacks
        self.model.bind_value_changed(self.handle_value_update)
        self.model.bind_event_changed(self.on_event_changed)

        # Load sdc ready picture
        self.load_sdc_ready_logo()

        # Define ids for debug screen
        self.debug_ids = [
        ("Accel Pedal pos", "apps_modified"),
        ("Accel Pedal upper", "apps_upper"),
        ("Accel Pedal lower", "apps_lower"),
        ("Steering Wheel angle", "steering_angle"),
        ("Brake Pressure Front", "bp_front"),
        ("Brake Pressure Back", "bp_rear"),
    ]

    def update_values_from_model(self):
        """
        Periodically sync displayed values with the model.
        """
        if self.current_screen:
            for key, value in self.model.values.items():
                self.current_screen.update_value(key, value)
        
        # Schedule next update
        self.after(100, self.update_values_from_model)

    def create_header_frame(self, parent):
        """Create the header frame with logo and mode label"""
        header_frame = tk.Frame(parent, bg=COLORS["header_bg"], height=50)
        header_frame.pack_propagate(False)
        
        # Logo on the left
        logo_frame = tk.Frame(header_frame, bg=COLORS["header_bg"])
        logo_frame.pack(side=tk.LEFT, padx=10)

        try:
            # Try to load logo
            logo_path = os.path.join(os.path.dirname(__file__), "resources", "HAWKS_LOGO.png")
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                logo_img = logo_img.resize((160, 40), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_img)
                self.logo_label = tk.Label(logo_frame, image=self.logo_photo, bg=COLORS["header_bg"])
                self.logo_label.pack()
        except:
            # Fallback text if logo not found
            self.logo_label = tk.Label(
                logo_frame, 
                text="HAWKS RACING", 
                font=("Segoe UI", 16, "bold"),
                fg=COLORS["text_secondary"],
                bg=COLORS["header_bg"]
            )
            self.logo_label.pack()
        
        # Mode label in center
        self.mode_label = tk.Label(
            header_frame,
            text=f"{self.model.current_event.capitalize()}",
            font=("Segoe UI", 22, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["header_bg"]
        )
        self.mode_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # R2D indicator on the right
        self.r2d_frame = tk.Frame(header_frame, bg=COLORS["header_bg"])
        self.r2d_frame.pack(side=tk.RIGHT, padx=10)

        self.r2d_indicator = tk.Label(
            self.r2d_frame,
            text="leck egg",
            font=("Segoe UI", 14, "bold"),
            fg=COLORS["accent_critical"],
            bg=COLORS["header_bg"]
        )
        self.r2d_indicator.pack()


        # Label for laptime
        self.laptime_label = tk.Label(
            header_frame,
            text="Laptime: unknown",
            font=("Segoe UI", 20, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["header_bg"],
            width=18,  # Feste Breite in Zeichen
            anchor="w"  # Links ausrichten
        )

        self.laptime_label.pack(side=tk.RIGHT, padx=10)

        return header_frame

    def create_menu_frame(self, parent, title="Menu"):
        """Create a generic menu frame with logo links in der Titlebar"""
        menu_frame = tk.Frame(parent, bg=COLORS["menu_bg"])
        
        # Title bar
        self.title_bar = tk.Frame(menu_frame, bg=COLORS["header_bg"], height=50)
        self.title_bar.pack(fill=tk.X)
        self.title_bar.pack_propagate(False)

        # Logo links
        self.logo_frame = tk.Frame(self.title_bar, bg=COLORS["header_bg"])
        self.logo_frame.grid(row=0, column=0)
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "resources", "HAWKS_LOGO.png")
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                logo_img = logo_img.resize((160, 40), Image.Resampling.LANCZOS)
                logo_photo = ImageTk.PhotoImage(logo_img)
                logo_label = tk.Label(self.logo_frame, image=logo_photo, bg=COLORS["header_bg"])
                logo_label.image = logo_photo  # Referenz speichern!
                logo_label.pack()
            else:
                logo_label = tk.Label(
                    self.logo_frame,
                    text="HAWKS RACING",
                    font=("Segoe UI", 16, "bold"),
                    fg=COLORS["text_secondary"],
                    bg=COLORS["header_bg"]
                )
                logo_label.pack()
        except Exception:
            logo_label = tk.Label(
                self.logo_frame,
                text="HAWKS RACING",
                font=("Segoe UI", 16, "bold"),
                fg=COLORS["text_secondary"],
                bg=COLORS["header_bg"]
            )
            logo_label.pack()

        # Titel mittig
        self.title_label = tk.Label(
            self.title_bar,
            text=title,
            font=("Segoe UI", 20, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["header_bg"]
        )
        self.title_label.grid(row=0, column=1, sticky="nsew")

        # Label for connection feedback
        self.connection_label = tk.Label(
            self.title_bar, 
            text=self.get_ip_address(),
            fg=COLORS["text_primary"],
            bg=COLORS["header_bg"]
        )
        self.connection_label.grid(row=0, column=2, sticky="nsew")

        # Start update of connection label
        self.update_ip_label()

        # Grid-Konfiguration für gleichmäßige Verteilung
        self.title_bar.grid_columnconfigure(0, weight=1)
        self.title_bar.grid_columnconfigure(1, weight=1)
        self.title_bar.grid_columnconfigure(2, weight=1)

        return menu_frame

    def create_main_menu_buttons(self, parent):
        """Create main menu buttons"""
        button_frame = tk.Frame(parent, bg=COLORS["menu_bg"])
        button_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        buttons = [
            ("Debugging Screen", self.show_debug_screen),
            ("ECU Versions and Activity", self.show_ecu_screen),
            ("TS OFF Screen", self.show_tsoff_screen),
            ("Return to Main", self.return_to_event_screen)
        ]
        
        self.main_menu_frames = []
        self.main_menu_button_list = []
        
        for idx, (text, command) in enumerate(buttons):
            btn_frame = tk.Frame(button_frame, bg=COLORS["menu_bg"], height=60)
            btn_frame.pack(fill=tk.X, pady=5)
            btn_frame.pack_propagate(False)
            
            btn = tk.Button(
                btn_frame,
                text=text,
                font=FONT_BUTTON,
                fg=COLORS["text_primary"],
                bg=COLORS["panel_bg"],
                activebackground=COLORS["accent_normal"],
                command=command,
                bd=0,
                highlightthickness=2
            )
            btn.pack(fill=tk.BOTH, expand=True)
            
            self.main_menu_frames.append(btn_frame)
            self.main_menu_button_list.append(btn)
        
        # Highlight first button by default
        if self.main_menu_frames:
            self.main_menu_frames[0].config(bg=COLORS["accent_normal"])
            
        return button_frame

    def create_debug_screen(self, parent):
        """Create debugging screen layout with CAN messages and pedal position bars"""
        content_frame = tk.Frame(parent, bg=COLORS["menu_bg"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left side - CAN message log
        left_frame = tk.Frame(content_frame, bg=COLORS["panel_bg"])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.data_ids = [
            "apps_modified", "bp_front", "bp_rear"
        ]
        
        log_label = tk.Label(
            left_frame,
            text="CAN Messages",
            font=("Segoe UI", 14, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["panel_bg"]
        )
        log_label.pack(pady=5)
        
        # Create a text widget for CAN messages
        self.can_log = tk.Text(
            left_frame,
            bg=COLORS["background"],
            fg=COLORS["text_primary"],
            font=("Consolas", 15),
            height=15,
            width=20
        )

        for sid in self.data_ids:
            value = self.model.get_value(sid)
            self.can_log.insert(tk.END, f"{sid}: {value}\n")

        self.can_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Middle - Vertical progress bars for pedals
        middle_frame = tk.Frame(content_frame, bg=COLORS["panel_bg"])
        middle_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 0))
        
        bars_label = tk.Label(
            middle_frame,
            text="Pedal Positions",
            font=("Segoe UI", 14, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["panel_bg"]
        )
        bars_label.pack(pady=5)
        
        # Container for progress bars
        bars_container = tk.Frame(middle_frame, bg=COLORS["panel_bg"])
        bars_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create progress bars for pedal positions
        pedal_bars = [
            {
                "id": "apps_modified", 
                "name": "Accel Pedal", 
                "type": "progress_bar",
                "min_value": 0,
                "max_value": 100,
                "width": 60,
                "height": 200,
                "bar_color": COLORS["accent_normal"]
            },
            {
                "id": "bp_front", 
                "name": "Brake Front", 
                "type": "progress_bar",
                "min_value": 0,
                "max_value": 100,
                "width": 60,
                "height": 200,
                "bar_color": COLORS["accent_critical"]
            },
            {
                "id": "bp_rear", 
                "name": "Brake Rear", 
                "type": "progress_bar",
                "min_value": 0,
                "max_value": 100,
                "width": 60,
                "height": 200,
                "bar_color": COLORS["accent_warning"]
            }
        ]
        
        self.debug_bars = PanelGroup(bars_container, self.model, pedal_bars)
        self.debug_bars.pack(fill=tk.BOTH, expand=True)
        
        # Right side - Live telemetry values
        right_frame = tk.Frame(content_frame, bg=COLORS["panel_bg"])
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        telemetry_label = tk.Label(
            right_frame,
            text="Live Telemetry",
            font=("Segoe UI", 14, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["panel_bg"]
        )
        telemetry_label.pack(pady=5)
        
        # Create panels for key telemetry values
        telemetry_panels = [
            {"id": "Speed", "name": "Speed"},
            {"id": "SOC", "name": "Battery SOC"},
            {"id": "Motor Temp", "name": "Motor Temp"},
            {"id": "DRS", "name": "DRS Status"}
        ]
        
        self.debug_panels = PanelGroup(right_frame, self.model, telemetry_panels)
        self.debug_panels.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        return content_frame

    def create_ecu_screen(self, parent):
        """Create the ECU versions and activity screen"""
        content_frame = tk.Frame(parent, bg=COLORS["menu_bg"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create a grid of ECU status panels
        ecu_data = [
            [
                {"id": "AMS_Status", "name": "AMS Status"},
                {"id": "AMS_Version", "name": "AMS Version"}
            ],
            [
                {"id": "VCU_Status", "name": "VCU Status"},
                {"id": "VCU_Version", "name": "VCU Version"}
            ],
            [
                {"id": "PDU_Status", "name": "PDU Status"},
                {"id": "PDU_Version", "name": "PDU Version"}
            ],
            [
                {"id": "DIU_Status", "name": "DIU Status"},
                {"id": "DIU_Version", "name": "DIU Version"}
            ]
        ]
        
        ecu_panels = PanelGroup(content_frame, self.model, ecu_data)
        ecu_panels.pack(fill=tk.BOTH, expand=True)
        
        return content_frame

    def create_tsoff_screen(self, parent):
        """Create debugging screen layout with CAN messages"""
        content_frame = tk.Frame(parent, bg=COLORS["menu_bg"])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left side - CAN message log

        # SDC Data
        sdc_ids = [
        "SDC_PDU", "SDC_VCU", "SDC_Inertia", "SDC_ESB_Front", "SDC_BSPD",
        "SDC_BOTS", "SDC_TS_Interlock", "SDC_AMS_IMD", "SDC_ESB_Right",
        "SDC_HVD", "SDC_ESB_Left", "SDC_TSMS"
        ]

        left_frame = tk.Frame(content_frame, bg=COLORS["panel_bg"])
        left_frame.pack(side=tk.LEFT)
        
        # Create a text widget for SDC status
        self.can_log = tk.Text(
            left_frame,
            bg=COLORS["background"],
            fg=COLORS["text_primary"],
            font=("Consolas", 15),
            height=15,
            width=22
        )

        # Tags for color coding
        self.can_log.tag_config("closed", foreground=COLORS["text_secondary"])
        self.can_log.tag_config("open", foreground="red")

        for sid in sdc_ids:
            value = self.model.get_value(sid)
            label = sid.replace("SDC_", "")  # shorter name
            self.can_log.insert(tk.END, f"{label}: {value}\n")

        self.can_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Bild direkt einfügen, damit du die Größe siehst
        if hasattr(self, "SDC_READY") and self.SDC_READY:
            self.can_log.delete("1.0", tk.END)  # Clear previous content
            self.can_log.image_create(tk.END, image=self.SDC_READY)
        
        # Right side - Live telemetry values
        right_frame = tk.Frame(content_frame, bg=COLORS["panel_bg"])
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Panels in 2x4 Grid
                
        telemetry_panels_grid = [
            [  # Row 1
                {"id": "Wh", "font_value_override": ("Cousine", 45, "bold")},
                {"id": "Lowest Cell", "font_value": ("Cousine", 45, "bold")}
            ],
            [  # Row 3
                {"id": "Highest Cell Temp", "name": "Highest Cell Temp"},
                {"id": "Max Torque", "name": "Torque"}
            ],
            [  # Row 5
                {"id": "Motor L Temp", "name": "Motor Temp Left"},
                {"id": "Motor R Temp", "name": "Motor Temp Right"}
            ]
        ]

        self.tsoff_panels = PanelGroup(right_frame, self.model, [telemetry_panels_grid])
        self.tsoff_panels.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        return content_frame

    def show_debug_screen(self):
        """Show the debug menu screen"""
        self.show_menu_screen(self.menu_debug_frame)

    def show_ecu_screen(self):
        """Show the ECU menu screen"""
        self.show_menu_screen(self.menu_ecu_frame)

    def show_tsoff_screen(self):
        """Show the TS OFF menu screen"""
        self.show_menu_screen(self.menu_tsoff_frame)

    def show_debug_message(self, message):
        """Show a debug message popup"""
        popup = tk.Toplevel(self)
        popup.title("Debug Message")
        popup.geometry("300x150")
        popup.configure(bg=COLORS["menu_bg"])
        
        msg_label = tk.Label(
            popup,
            text=message,
            font=("Segoe UI", 12),
            fg=COLORS["text_primary"],
            bg=COLORS["menu_bg"],
            wraplength=280
        )
        msg_label.pack(expand=True, pady=20)
        
        close_btn = tk.Button(
            popup,
            text="Close",
            font=("Segoe UI", 12, "bold"),
            fg=COLORS["text_primary"],
            bg=COLORS["panel_bg"],
            command=popup.destroy
        )
        close_btn.pack(pady=10)
        
        # Center the popup
        popup.update_idletasks()
        x = (popup.winfo_screenwidth() // 2) - (popup.winfo_width() // 2)
        y = (popup.winfo_screenheight() // 2) - (popup.winfo_height() // 2)
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
        self.mode_label.config(text=f"{event_name.capitalize()}")

    def on_event_changed(self, event_name):
        """Handle event change from model"""
        self.create_event_screen(event_name)

    def _build_autocross_layout(self, event_name="autocross"):
        """Create the autocross/skidpad/acceleration screen layout based on the diagram"""
        return {
            "left": [
                # # SOC indicator (top)
                # {"id": "SOC", "name": "SOC",
                #  "font_value": ("Segoe UI", 50, "bold"),
                #  "font_name": ("Segoe UI", 30),
                #  "width": 200, "height": 150,
                #  "bg_color": COLORS["panel_bg"]},
                
                # Vehicle control modes (middle)
                [
                    {"id": "Traction Control Mode", "name": "Traction Control Mode",
                     "font_value": ("Segoe UI", 30, "bold"),
                     "font_name": ("Segoe UI", 10),
                     "bg_color": COLORS["panel_bg"]}
                ],
                [
                    {"id": "Torque Vectoring Mode", "name": "Torque Vectoring Mode",
                     "font_value": ("Segoe UI", 30, "bold"),
                     "font_name": ("Segoe UI", 10),
                     "bg_color": COLORS["panel_bg"]}
                ],
                [
                    {"id": "Max Torque", "name": "Max Torque",
                     "font_value": ("Segoe UI", 30, "bold"),
                     "font_name": ("Segoe UI", 10),
                     "bg_color": COLORS["panel_bg"]}
                ]
            ],
            "right": [
                # Lowest Cell and Accu Temp (top right)
                [
                    [{"id": "Lowest Cell", "name": "Lowest Cell",
                      "font_value": ("Segoe UI", 30, "bold"),
                      "font_name": ("Segoe UI", 14),
                      "value_pady": (20, 0),
                      "bg_color": COLORS["panel_bg"]},
                     {"id": "Highest Cell Temp", "name": "Highest Cell Temp",
                      "font_value": ("Segoe UI", 30, "bold"),
                      "font_name": ("Segoe UI", 14),
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
                {"id": "Lowest Cell", "name": "Lowest CellV",
                 "font_value": ("Segoe UI", 48, "bold"),
                 "font_name": ("Segoe UI", 26),
                 "value_pady": (10, 0),
                 "bg_color": COLORS["panel_bg"]}
            ],
            "right": [
                # Temperature grid (2x2)
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
        # Skip TS On updates - these are handled by the Controller
        if panel_id == "TS On":
            return
            
        if self.current_screen:
            self.current_screen.update_value(panel_id, value)
        
        if hasattr(self, 'tsoff_panels') and self.menu_tsoff_frame.winfo_ismapped():
            self.tsoff_panels.update_panel_value(panel_id, value)

        """Handle R2D Status changes"""
        if panel_id == "R2D Status":
            current_r2d_state = self.model.get_value("R2D Status")
            
            # Only update if the state actually changed
            if self.last_r2d_state != current_r2d_state:
                # Cancel any pending timer since we have a real state change
                # if self.r2d_update_timer:
                #     self.after_cancel(self.r2d_update_timer)
                #     self.r2d_update_timer = None
                    
                # Update immediately on state change
                self.last_r2d_state = current_r2d_state
                if current_r2d_state == 1:
                    self.r2d_indicator.config(text="R2D Active", fg=COLORS["text_primary"], bg=COLORS["R2D_active"])
                    self.header_frame.config(bg=COLORS["R2D_active"])
                    self.logo_label.config(bg=COLORS["R2D_active"])
                    self.mode_label.config(bg=COLORS["R2D_active"])
                    self.laptime_label.config(bg=COLORS["R2D_active"])

                    self.title_label.config(bg=COLORS["R2D_active"])
                    self.connection_label.config(bg=COLORS["R2D_active"])
                    self.logo_frame.config(bg=COLORS["R2D_active"])
                    self.title_bar.config(bg=COLORS["R2D_active"])
                else:
                    self.r2d_indicator.config(text="R2D Inactive", fg=COLORS["text_primary"], bg=COLORS["header_bg"])
                    self.header_frame.config(bg=COLORS["header_bg"])
                    self.logo_label.config(bg=COLORS["header_bg"])
                    self.mode_label.config(bg=COLORS["header_bg"])
                    self.laptime_label.config(bg=COLORS["header_bg"])
                    # For Testing screen
                    self.title_label.config(bg=COLORS["header_bg"])
                    self.connection_label.config(bg=COLORS["header_bg"])
                    self.logo_frame.config(bg=COLORS["header_bg"])
                    self.title_bar.config(bg=COLORS["header_bg"])
        
        """Handle Laptime changes"""
        if panel_id == "Laptime":
            self.laptime_label.config(text=f"Laptime: {round(value, 2)}")

        """Handle SDC Status changes"""
        # Handle SDC Status changes
        if panel_id.startswith("SDC_"):
            self.can_log.delete("1.0", tk.END)
            all_closed = True
            for pid in [k for k in self.model.values if k.startswith("SDC_")]:
                v = self.model.get_value(pid)
                status = "Open" if v == 1 else "Closed"
                tag = "open" if v == 1 else "closed"
                self.can_log.insert(tk.END, f"{pid.replace('SDC_', '')}: {status}\n", tag)
                if v == 1:
                    all_closed = False

            # Wenn alle geschlossen sind, Bild anzeigen
            if all_closed and self.SDC_READY:
                self.can_log.delete("1.0", tk.END)
                self.can_log.image_create(tk.END, image=self.SDC_READY)
        
        """Handle changes for debug screen"""
        if self.menu_debug_frame.winfo_ismapped():
            # Update CAN log
            self.can_log.delete("1.0", tk.END)
            for label, key in self.debug_ids:
                v = self.model.get_value(key)
                self.can_log.insert(tk.END, f"{label}: {v}\n")
            
            # Update debug bars
            if hasattr(self, 'debug_bars'):
                self.debug_bars.update_panel_value(panel_id, value)
            
            # Update debug panels
            if hasattr(self, 'debug_panels'):
                self.debug_panels.update_panel_value(panel_id, value)

    def load_sdc_ready_logo(self):
        try:
            img_path = os.path.join(os.path.dirname(__file__), "resources", "SDC_READY.png")
            if os.path.exists(img_path):
                self.SDC_READY = ImageTk.PhotoImage(Image.open(img_path).resize((400, 400)))
            else:
                self.SDC_READY = None
        except Exception:
            self.SDC_READY = None

    def blink_logo(self):
        """Blink the logo for visual feedback"""
        if not self.blinking:
            self.blinking = True
            self._do_blink()
    
    def _do_blink(self):
        """Perform the actual blinking"""
        if self.blinking:
            if self.is_logo_visible:
                self.logo_label.config(bg=COLORS["accent_warning"])
            else:
                self.logo_label.config(bg=COLORS["header_bg"])
            
            self.is_logo_visible = not self.is_logo_visible
            
            # Continue blinking
            self.after(200, self._do_blink)

    def get_ip_address(self):
        try:
            # Verbindungsversuch zu einer externen Adresse (Google DNS)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "No connection"
    
    def update_ip_label(self):
        if hasattr(self, "ip_label"):
            self.ip_label.config(text=self.get_ip_address())
        self.after(5000, self.update_ip_label)
