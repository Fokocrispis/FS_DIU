from can_model import CANModel, AllMsg
from Model import Model
from View import Display
from Controller import Controller
import tkinter as tk

def main():
    # Initialize CAN model
    can = CANModel()

    # Create Model with CAN bus
    model = Model(can.bus)

    # Create the main Tkinter window through the Display class
    view = Display(model)

    # Create the Controller
    controller = Controller(model, view, can.bus)

    secondary_window = tk.Toplevel(view)
    secondary_window.title("CAN Messages")
    AllMsg(secondary_window, controller, dbc_path="H19_CAN_dbc.dbc")
    
    # Run the Tkinter main loop
    view.mainloop()

if __name__ == '__main__':
    main()
