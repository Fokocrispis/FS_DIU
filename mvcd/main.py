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
    Parses command line arguments, initializes components with dual CAN bus support, and starts the GUI.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Hawks Display - Formula Student Car Interface")
    parser.add_argument("--virtual", action="store_true", help="Use virtual CAN (vcan0/vcan1) instead of real CAN")
    parser.add_argument("--demo", action="store_true", help="Run in demo mode with simulated values")
    parser.add_argument("--dbc", type=str, default="H20_CAN_dbc.dbc", help="Path to DBC file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--control-channel", type=str, default="can0", help="Control CAN bus channel (default: can0)")
    parser.add_argument("--logging-channel", type=str, default="can1", help="Logging CAN bus channel (default: can1)")
    parser.add_argument("--no-can-monitor", action="store_true", help="Disable secondary CAN monitoring window")
    args = parser.parse_args()
    
    # Set logging level based on debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.info("Debug logging enabled")
    
    # Override channels if virtual mode is requested
    if args.virtual:
        args.control_channel = "vcan0"
        args.logging_channel = "vcan1"
        logging.info("Using virtual CAN channels: vcan0 (control), vcan1 (logging)")
    
    # Import components after parsing arguments
    try:
        from can_model import CANModel, AllMsg
        from Model import Model
        from View import Display
        from Controller import Controller
    except ImportError as e:
        logging.critical(f"Failed to import required modules: {e}")
        logging.critical("Make sure all required files are present and dependencies are installed")
        return 1
    
    # Check for resources directory and logo
    resources_dir = "resources"
    if not os.path.exists(resources_dir):
        try:
            os.makedirs(resources_dir, exist_ok=True)
            logging.warning(f"Created missing '{resources_dir}' directory")
        except Exception as e:
            logging.error(f"Failed to create resources directory: {e}")
    
    logo_path = os.path.join(resources_dir, "HAWKS_LOGO.png")
    if not os.path.exists(logo_path):
        logging.warning(f"Logo file '{logo_path}' not found. UI will use a placeholder.")
    
    # Check for DBC file
    if not os.path.exists(args.dbc):
        logging.error(f"DBC file '{args.dbc}' not found. CAN decoding will not work correctly.")
        logging.error("Please ensure the DBC file is in the correct location or specify the correct path with --dbc")
    
    # Log startup configuration
    logging.info("=" * 60)
    logging.info("DIU Display Starting")
    logging.info("=" * 60)
    logging.info(f"Control CAN Channel: {args.control_channel}")
    logging.info(f"Logging CAN Channel: {args.logging_channel}")
    logging.info(f"DBC File: {args.dbc}")
    logging.info(f"Demo Mode: {'Enabled' if args.demo else 'Disabled'}")
    logging.info(f"Debug Mode: {'Enabled' if args.debug else 'Disabled'}")
    logging.info(f"Virtual CAN: {'Enabled' if args.virtual else 'Disabled'}")
    logging.info("Starting with default values (no persistence)")
    
    # Initialize dual CAN bus model
    try:
        can_model = CANModel(
            dbc_path=args.dbc,
            control_channel=args.control_channel,
            logging_channel=args.logging_channel
        )
        logging.info("CAN model initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize CAN model: {e}")
        logging.error("Continuing with limited functionality...")
        can_model = None
    
    # Create the application Model (always starts with default values)
    try:
        # Pass the control bus as the primary bus for compatibility
        primary_bus = can_model.control_bus if can_model else None
        model = Model(primary_bus, dbc_path=args.dbc)
        logging.info("Data model initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize data model: {e}")
        return 1
    
    # Create the main Tkinter window through the Display class
    try:
        view = Display(model)
        logging.info("GUI view initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize GUI: {e}")
        return 1
    
    # Create the Controller with dual bus support
    try:
        control_bus = can_model.control_bus if can_model else None
        logging_bus = can_model.logging_bus if can_model else None
        controller = Controller(model, view, control_bus, logging_bus)
        logging.info("Controller initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize controller: {e}")
        return 1
    
    # Start in demo mode if requested
    if args.demo:
        try:
            controller.toggle_demo_mode()
            logging.info("Demo mode activated")
        except Exception as e:
            logging.error(f"Failed to start demo mode: {e}")
    
    # Create secondary window for CAN monitoring if debug mode is enabled and not disabled
    secondary_window = None
    if args.debug and not args.no_can_monitor:
        try:
            secondary_window = tk.Toplevel(view)
            secondary_window.title("CAN Bus Monitor - Dual Bus")
            secondary_window.geometry("1000x700")
            secondary_window.configure(bg="#f0f0f0")
            
            # Initialize the CAN monitoring window
            can_monitor = AllMsg(
                secondary_window, 
                controller, 
                dbc_path=args.dbc,
                control_channel=args.control_channel,
                logging_channel=args.logging_channel
            )
            logging.info("CAN monitoring window initialized")
        except Exception as e:
            logging.error(f"Failed to initialize CAN monitoring window: {e}")
            logging.error("Continuing without CAN monitoring window...")
            if secondary_window:
                secondary_window.destroy()
                secondary_window = None
    
    # Configure window properties
    try:
        # Set window icon if available
        icon_path = os.path.join(resources_dir, "icon.ico")
        if os.path.exists(icon_path):
            view.iconbitmap(icon_path)
        
        # Set window title with version info
        view.title("Hawks Display - Formula Student Car Interface v1.0")
        
        # Configure window closing behavior
        def on_closing():
            logging.info("Application shutdown requested")
            try:
                # Clean up resources
                if hasattr(model, 'cleanup'):
                    model.cleanup()
                if can_model and hasattr(can_model, 'shutdown'):
                    can_model.shutdown()
                if secondary_window:
                    secondary_window.destroy()
                view.destroy()
                logging.info("Application shutdown completed")
            except Exception as e:
                logging.error(f"Error during shutdown: {e}")
            finally:
                # Force exit if necessary
                os._exit(0)
        
        view.protocol("WM_DELETE_WINDOW", on_closing)
        
    except Exception as e:
        logging.error(f"Error configuring window properties: {e}")
    
    # Log successful startup
    logging.info("=" * 60)
    logging.info("DIU Display Successfully Started")
    logging.info("=" * 60)
    logging.info("Available keyboard shortcuts:")
    logging.info("  SPACE    - Toggle demo mode")
    logging.info("  N        - Next event")
    logging.info("  P        - Previous event")
    logging.info("  H/ESC    - Toggle menu")
    logging.info("  T        - Cycle traction control mode")
    logging.info("  V        - Cycle torque vectoring mode")
    logging.info("  D        - Toggle DRS state")
    logging.info("  S        - Show settings screen")
    logging.info("  F        - Toggle fullscreen")
    logging.info("  Q        - Quit application")
    
    # Show bus status
    if can_model:
        control_status = "Connected" if can_model.control_bus else "Failed"
        logging_status = "Connected" if can_model.logging_bus else "Failed"
        logging.info(f"Control Bus Status: {control_status}")
        logging.info(f"Logging Bus Status: {logging_status}")
        
        if not can_model.control_bus and not can_model.logging_bus:
            logging.warning("No CAN buses available - running in view-only mode")
        elif not can_model.control_bus:
            logging.warning("Control bus not available - limited functionality")
        elif not can_model.logging_bus:
            logging.warning("Logging bus not available - limited sensor data")
    
    logging.info("=" * 60)
    
    # Run the Tkinter main loop
    try:
        view.mainloop()
    except KeyboardInterrupt:
        logging.info("Application terminated by user (Ctrl+C)")
    except Exception as e:
        logging.error(f"Unhandled exception in main loop: {e}", exc_info=True)
        return 1
    finally:
        # Final cleanup
        try:
            logging.info("Performing final cleanup...")
            if hasattr(model, 'cleanup'):
                model.cleanup()
            if can_model and hasattr(can_model, 'shutdown'):
                can_model.shutdown()
            logging.info("Final cleanup completed")
        except Exception as e:
            logging.error(f"Error during final cleanup: {e}")
        
        logging.info("DIU Display application terminated")
    
    return 0

def setup_virtual_can():
    """
    Helper function to set up virtual CAN interfaces for development/testing.
    This function can be called separately to set up vcan0 and vcan1.
    """
    import subprocess
    import sys
    
    try:
        # Check if running on Linux (required for vcan)
        if sys.platform != "linux":
            print("Virtual CAN interfaces are only supported on Linux")
            return False
        
        # Commands to set up virtual CAN interfaces
        commands = [
            ["sudo", "modprobe", "vcan"],
            ["sudo", "ip", "link", "add", "dev", "vcan0", "type", "vcan"],
            ["sudo", "ip", "link", "set", "up", "vcan0"],
            ["sudo", "ip", "link", "add", "dev", "vcan1", "type", "vcan"],
            ["sudo", "ip", "link", "set", "up", "vcan1"]
        ]
        
        for cmd in commands:
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                print(f"Successfully executed: {' '.join(cmd)}")
            except subprocess.CalledProcessError as e:
                if "File exists" in str(e.stderr):
                    print(f"Interface already exists: {cmd[4] if len(cmd) > 4 else 'unknown'}")
                else:
                    print(f"Failed to execute: {' '.join(cmd)}")
                    print(f"Error: {e.stderr.decode()}")
        
        print("Virtual CAN setup completed")
        print("You can now use --virtual flag or specify --control-channel vcan0 --logging-channel vcan1")
        return True
        
    except Exception as e:
        print(f"Error setting up virtual CAN: {e}")
        return False

if __name__ == '__main__':
    try:
        exit_code = main()
        exit(exit_code)
    except Exception as e:
        logging.critical(f"Critical error in main: {e}", exc_info=True)
        exit(1)