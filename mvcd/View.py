import os
import tkinter as tk
from PIL import Image, ImageTk

# --------------------------------------------------------------------------
# Color and style settings
# --------------------------------------------------------------------------
COLORS = {
    "background": "#0a0c0f",
    "panel_bg": "#1b1b1b",
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

    Each panel can be assigned a static width and height so it never
    resizes when text changes.
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
        height=100   # default height if not specified
    ):
        super().__init__(
            parent,
            bg=COLORS["panel_bg"],
            highlightthickness=1,
            highlightcolor=COLORS["border"]
        )
        self.panel_id = panel_id
        self.name = name
        self.unit = unit
        self.model = model

        # Force a static width & height
        self.config(width=width, height=height)
        self.pack_propagate(False)  # or grid_propagate(False) if using .grid()

        # Decide which fonts to use
        self.font_value = font_value_override or FONT_VALUE
        self.font_name = font_name_override or FONT_NAME

        # Value Label
        self.value_label = tk.Label(
            self,
            text=f"{value}{(' ' + self.unit) if self.unit else ''}",
            font=self.font_value,
            fg=self.get_value_color(value),
            bg=COLORS["panel_bg"],
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
            bg=COLORS["panel_bg"],
            borderwidth=0
        )
        self.name_label.pack(
            expand=True,
            fill=tk.BOTH,
            padx=name_padx,
            pady=name_pady
        )

    def update_value(self, new_value):
        """
        Update the displayed value and color based on new_value.
        """
        self.value_label.config(
            text=f"{new_value}{(' ' + self.unit) if self.unit else ''}",
            fg=self.get_value_color(new_value)
        )

    def get_value_color(self, val):
        """
        Determine the foreground color based on self.panel_id and thresholds.
        """
        # Expand this with your logic/thresholds
        if self.panel_id == "Air Temp":
            if val > 60:
                return COLORS['accent_critical']
            elif val > 40:
                return COLORS['accent_warning']
            else:
                return COLORS['accent_normal']
        return COLORS['accent_normal']


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
                height=height
            )
            dp.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

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
                        height=height
                    )
                    dp.grid(row=row_idx, column=col_idx,
                            rowspan=rowspan, columnspan=colspan,
                            padx=4, pady=4, sticky='nsew')

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
        for child in self.winfo_children():
            if isinstance(child, DisplayPanel):
                if child.panel_id == panel_id:
                    child.update_value(new_value)
            elif isinstance(child, PanelGroup):
                child.update_panel_value(panel_id, new_value)


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
        if self.left_group:
            self.left_group.update_panel_value(panel_id, value)
        if self.right_group:
            self.right_group.update_panel_value(panel_id, value)


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

        self.header_frame = self.create_header_frame(self.main_frame)
        self.header_frame.config(height=50)
        self.header_frame.pack_propagate(False)
        self.header_frame.pack(side=tk.TOP, fill=tk.X)

        self.split_frame = tk.Frame(self.main_frame, bg=COLORS["background"])
        self.split_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.menu_frame = self.create_menu_frame(self.main_frame)
        self.menu_event_frame = self.create_event_menu_frame(self.main_frame)

        self.current_screen = None
        self.create_event_screen(self.model.current_event)
        self.create_buttons()

        # Blink logo
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
        if self.logo_label and self.logo_image_full and self.logo_image_blank:
            if self.logo_blink_state:
                self.logo_label.config(image=self.logo_image_blank)
            else:
                self.logo_label.config(image=self.logo_image_full)
            self.logo_blink_state = not self.logo_blink_state
        self.after(1500, self.toggle_logo)

    def create_menu_frame(self, parent):
        return tk.Frame(parent, bg=COLORS["menu_bg"])

    def create_event_menu_frame(self, parent):
        return tk.Frame(parent, bg=COLORS["menu_bg"])

    def create_buttons(self):
        self.menu_container = tk.Frame(self.menu_frame, bg=COLORS["menu_bg"])
        self.menu_container.place(relx=0.5, rely=0.5, anchor="center")

        highlight_frame1 = tk.Frame(self.menu_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame1.pack(pady=10)
        self.button1 = tk.Button(
            highlight_frame1,
            text="Add random value",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button1.pack()

        highlight_frame2 = tk.Frame(self.menu_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame2.pack(pady=10)
        self.button2 = tk.Button(
            highlight_frame2,
            text="Event Selection",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button2.pack()

        highlight_frame3 = tk.Frame(self.menu_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame3.pack(pady=10)
        self.button3 = tk.Button(
            highlight_frame3,
            text="TBI",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button3.pack()

        self.main_menu_button_list = [self.button1, self.button2, self.button3]
        self.main_menu_frames = [highlight_frame1, highlight_frame2, highlight_frame3]

        self.menu_event_container = tk.Frame(self.menu_event_frame, bg=COLORS["menu_bg"])
        self.menu_event_container.place(relx=0.5, rely=0.5, anchor="center")

        highlight_frame4 = tk.Frame(self.menu_event_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame4.pack(pady=10)
        self.button4 = tk.Button(
            highlight_frame4,
            text="Autocross",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button4.pack()

        highlight_frame5 = tk.Frame(self.menu_event_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame5.pack(pady=10)
        self.button5 = tk.Button(
            highlight_frame5,
            text="Endurance",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button5.pack()

        highlight_frame6 = tk.Frame(self.menu_event_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame6.pack(pady=10)
        self.button6 = tk.Button(
            highlight_frame6,
            text="Acceleration",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button6.pack()

        highlight_frame7 = tk.Frame(self.menu_event_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame7.pack(pady=10)
        self.button7 = tk.Button(
            highlight_frame7,
            text="Skidpad",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button7.pack()

        highlight_frame8 = tk.Frame(self.menu_event_container, bg=COLORS["menu_bg"], bd=2)
        highlight_frame8.pack(pady=10)
        self.button8 = tk.Button(
            highlight_frame8,
            text="Practice",
            font=FONT_BUTTON,
            fg="#ffffff",
            bg="#333333",
            activebackground="#444444",
            width=18,
            borderwidth=0
        )
        self.button8.pack()

        self.event_menu_button_list = [self.button4, self.button5, self.button6, self.button7, self.button8]
        self.event_menu_frames = [highlight_frame4, highlight_frame5, highlight_frame6, highlight_frame7, highlight_frame8]

        self.menu_frame.pack_forget()
        self.menu_event_frame.pack_forget()

    def menu_pop(self):
        if self.menu_frame.winfo_ismapped() or self.menu_event_frame.winfo_ismapped():
            self.menu_frame.pack_forget()
            self.menu_event_frame.pack_forget()
            self.header_frame.pack(side=tk.TOP, fill=tk.X)
            self.split_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        else:
            self.split_frame.pack_forget()
            self.header_frame.pack_forget()
            self.menu_frame.pack(fill=tk.BOTH, expand=True)

    def menu_event_selector(self):
        self.menu_frame.pack_forget()
        self.menu_event_frame.pack(fill=tk.BOTH, expand=True)

    def create_event_screen(self, event_name):
        # Clear existing
        for child in self.split_frame.winfo_children():
            child.destroy()

        layout = self._build_event_layout(event_name)
        self.current_screen = EventScreen(event_name, self.model, self.split_frame, layout)
        self.mode_label.config(text=f"AMI: Manual Driving - {event_name.capitalize()}")

    def _build_event_layout(self, event_name):
        params = self.model.event_screens.get(event_name, [])
        midpoint = len(params) // 2
        left_params = params[:midpoint]
        right_params = params[midpoint:]
        return {
            "left": left_params,
            "right": right_params
        }

    def handle_value_update(self, panel_id, value):
        if self.current_screen:
            self.current_screen.update_value(panel_id, value)
