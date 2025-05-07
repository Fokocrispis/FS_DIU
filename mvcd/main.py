import logging
import tkinter as tk
import argparse
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("DIU.log"),
        logging.StreamHandler()
    ]
)

def main():
    """
    Main entry point for the DIU application.
    Parses command line arguments, initializes components, and starts the GUI.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Hawks Display")
    parser.add_argument("--virtual", action="store_true", help="Use virtual CAN (vcan0) instead of real CAN")
    parser.add_argument("--demo", action="store_true", help="Run in demo mode with simulated values")
    parser.add_argument("--dbc", type=str, default="H19_CAN_dbc.dbc", help="Path to DBC file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Set logging level based on debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Import components only after parsing arguments to ensure they
    # have access to command line options if needed
    from can_model import CANModel
    from Model import Model
    from View import Display
    from Controller import Controller
    
    # Optional: Import AllMsg for secondary window if debugging
    try:
        from can_model import AllMsg
    except ImportError:
        AllMsg = None
        logging.warning("AllMsg class not found in can_model.py")
    
    # Check for resources directory and logo
    resources_dir = "resources"
    if not os.path.exists(resources_dir):
        os.makedirs(resources_dir, exist_ok=True)
        logging.warning(f"Created missing '{resources_dir}' directory")
    
    logo_path = os.path.join(resources_dir, "HAWKS_LOGO.png")
    if not os.path.exists(logo_path):
        logging.warning(f"Logo file '{logo_path}' not found. UI will use a placeholder.")
    
    # Check for DBC file
    if not os.path.exists(args.dbc):
        logging.error(f"DBC file '{args.dbc}' not found. CAN decoding will not work correctly.")
    
    # Initialize CAN model with virtual flag
    can_model = CANModel(dbc_path=args.dbc)
    
    # Create the application Model
    model = Model(can_model.bus, dbc_path=args.dbc)
    
    # Create the main Tkinter window through the Display class
    view = Display(model)
    
    # Create the Controller
    controller = Controller(model, view, can_model.bus)
    
    # Start in demo mode if requested
    if args.demo:
        controller.toggle_demo_mode()
    
    # Create secondary window for CAN monitoring if debug mode is enabled
    secondary_window = None
    if args.debug and AllMsg is not None:
        secondary_window = tk.Toplevel(view)
        secondary_window.title("CAN Messages")
        secondary_window.geometry("900x600")
        AllMsg(secondary_window, controller, dbc_path=args.dbc)
    
    # Log startup status
    logging.info("DIU Display started")
    logging.info(f"Using DBC file: {args.dbc}")
    logging.info(f"Demo mode: {'Enabled' if args.demo else 'Disabled'}")
    logging.info(f"Debug mode: {'Enabled' if args.debug else 'Disabled'}")
    
    # Run the Tkinter main loop
    try:
        view.mainloop()
    except KeyboardInterrupt:
        logging.info("Application terminated by user")
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
    finally:
        logging.info("Application shutdown")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)