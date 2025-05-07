import tkinter as tk
from tkinter import PhotoImage
from tkinter import ttk

def create_main_window():
    root = tk.Tk()
    root.title("Hawks Display")
    root.configure(bg="#121212")
    root.geometry("1024x768")
    root.minsize(800, 600)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    header_frame = tk.Frame(root, bg="#1e1e1e", bd=4, relief=tk.RIDGE)
    header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
    header_frame.columnconfigure(0, weight=0)
    header_frame.columnconfigure(1, weight=1)

    original_logo_photo = PhotoImage(file="resources/HAWKS_LOGO.png")
    logo_label = tk.Label(header_frame, bg="#1e1e1e")
    logo_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    def resize_image(event):
        max_size = min(event.width // 8, event.height - 5)
        if max_size > 0:
            resized_logo = original_logo_photo.subsample(max(1, original_logo_photo.width() // max_size), max(1, original_logo_photo.height() // max_size))
            logo_label.config(image=resized_logo)
            logo_label.image = resized_logo

    header_frame.bind("<Configure>", resize_image)

    mode_label = tk.Label(header_frame, text="AMI: Manual Driving - Autocross", font=("Helvetica", 30, "bold"), bg="#1e1e1e", fg="#00ff00")
    mode_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    grid_frame = tk.Frame(root, bg="#121212")
    grid_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 20))

    for i in range(3):
        grid_frame.columnconfigure(i, weight=1, uniform="column")
        grid_frame.rowconfigure(i, weight=1, uniform="row")

    panel_info = [
        ("AMS", "OFF"),
        ("IMD", "0"),
        ("Watt Hours", "169"),
        ("ASPU", "0"),
        ("Aux Voltage", "0"),
        ("SOC", "0%"),
        ("Air Temp", "20C"),
        ("Lowest Cell Voltage", "3.7V"),
        ("Inverter Temp", "22C")
    ]

    panels = []
    for row in range(3):
        for col in range(3):
            index = row * 3 + col
            panel = tk.Frame(grid_frame, bg="#2b2b2b", bd=3, relief=tk.RIDGE)
            panel.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            panel.columnconfigure(0, weight=1)
            panel.rowconfigure(0, weight=1)
            panel.rowconfigure(1, weight=1)
            value_label = tk.Label(panel, text=panel_info[index][1], font=("Helvetica", 22, "bold"), bg="#2b2b2b", fg="#ffcc00")
            value_label.pack(pady=(10, 0))
            description_label = tk.Label(panel, text=panel_info[index][0], font=("Helvetica", 16), bg="#2b2b2b", fg="white")
            description_label.pack(pady=(5, 10))

            panels.append((panel, value_label, description_label))

    def adjust_sizes(event):
        new_width = event.width
        new_height = event.height

        new_font_size_mode = max(20, int(new_width / 30))
        mode_label.config(font=("Helvetica", new_font_size_mode, "bold"))

        for panel, value_label, description_label in panels:
            panel_width = panel.winfo_width()
            new_font_size_value = max(18, int(panel_width / 8))
            new_font_size_desc = max(14, int(panel_width / 12))
            value_label.config(font=("Helvetica", new_font_size_value, "bold"))
            description_label.config(font=("Helvetica", new_font_size_desc))

    root.bind("<Configure>", adjust_sizes)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TLabel", background="#2b2b2b", foreground="white", font=("Helvetica", 12))
    style.configure("TFrame", background="#2b2b2b")

    root.mainloop()

if __name__ == "__main__":
    create_main_window()


