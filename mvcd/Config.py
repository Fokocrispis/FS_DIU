import os
import json
import logging
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class Config:
    """
    Configuration management class for the Formula Student Car Display.
    
    Handles:
    - Loading/saving configuration from files
    - Default configuration values
    - Environment-specific configuration
    - Multiple configuration profiles
    
    This allows for easier development, testing, and deployment
    with different settings.
    """
    
    DEFAULT_CONFIG = {
        # Application settings
        "app": {
            "name": "Formula Student Car Display",
            "version": "1.0.0",
            "fullscreen": False,
            "width": 800,
            "height": 480,
            "demo_mode": False,
            "debug": False
        },
        
        # CAN bus settings
        "can": {
            "interface": "socketcan",
            "channel": "can0",
            "bitrate": 1000000,
            "dbc_file": "H19_CAN_dbc.dbc",
            "use_virtual": False
        },
        
        # UI settings
        "ui": {
            "theme": "dark",
            "font_family": "Segoe UI",
            "refresh_rate_ms": 100,
            "animation_enabled": True,
            "colors": {
                "background": "#0a0c0f",
                "panel_bg": "#1b1b1b",
                "panel_active": "#4b8f29",
                "border": "#666666",
                "text_primary": "#ffffff",
                "text_secondary": "#ff9900",
                "accent_critical": "#ff0000",
                "accent_warning": "#ffcc00",
                "accent_normal": "#00ff00",
                "header_bg": "#202020",
                "menu_bg": "#151515"
            }
        },
        
        # Default model values
        "model": {
            "autosave_interval_ms": 30000,
            "current_event": "autocross",
            "thresholds": {
                "accu_temp_warning": 40,
                "accu_temp_critical": 60,
                "motor_temp_warning": 75,
                "motor_temp_critical": 90,
                "inverter_temp_warning": 65,
                "inverter_temp_critical": 80,
                "lowest_cell_warning": 3.5,
                "lowest_cell_critical": 3.2,
                "soc_warning": 30,
                "soc_critical": 20
            }
        },
        
        # Logging settings
        "logging": {
            "level": "INFO",
            "file": "formula_student_gui.log",
            "max_size_mb": 10,
            "backup_count": 3
        }
    }
    
    def __init__(self, config_dir: str = "config", profile: str = "default"):
        """
        Initialize configuration system.
        
        Args:
            config_dir: Directory for configuration files
            profile: Configuration profile name to load
        """
        self.config_dir = config_dir
        self.profile = profile
        self.config = dict(self.DEFAULT_CONFIG)  # Create a copy of default config
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Load configuration
        self.load()
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            section: Configuration section
            key: Configuration key
            default: Default value if not found
            
        Returns:
            Configuration value or default if not found
        """
        if section in self.config and key in self.config[section]:
            return self.config[section][key]
        return default
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get an entire configuration section.
        
        Args:
            section: Configuration section
            
        Returns:
            Dictionary containing the section or empty dict if not found
        """
        return self.config.get(section, {})
    
    def set(self, section: str, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            section: Configuration section
            key: Configuration key
            value: Value to set
        """
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
    
    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        """
        Update an entire configuration section.
        
        Args:
            section: Configuration section
            values: Dictionary of values to update
        """
        if section not in self.config:
            self.config[section] = {}
        self.config[section].update(values)
    
    def get_config_path(self) -> str:
        """
        Get the path to the configuration file.
        
        Returns:
            Path to configuration file
        """
        return os.path.join(self.config_dir, f"{self.profile}.json")
    
    def load(self) -> bool:
        """
        Load configuration from file.
        
        Returns:
            True if successful, False otherwise
        """
        config_path = self.get_config_path()
        
        # If config file doesn't exist, create it with default values
        if not os.path.exists(config_path):
            logger.info(f"Configuration file not found: {config_path}. Creating with defaults.")
            return self.save()
        
        try:
            with open(config_path, 'r') as f:
                loaded_config = json.load(f)
                
                # Merge with defaults (keeping loaded values where they exist)
                self._merge_configs(self.config, loaded_config)
                
                logger.info(f"Configuration loaded from {config_path}")
                return True
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing configuration file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False
    
    def save(self) -> bool:
        """
        Save configuration to file.
        
        Returns:
            True if successful, False otherwise
        """
        config_path = self.get_config_path()
        
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
                
            logger.info(f"Configuration saved to {config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def _merge_configs(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        Recursively merge source config into target config.
        
        Args:
            target: Target configuration dictionary
            source: Source configuration dictionary
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_configs(target[key], value)
            else:
                target[key] = value
    
    def create_profile(self, profile_name: str) -> bool:
        """
        Create a new configuration profile.
        
        Args:
            profile_name: Name of the profile to create
            
        Returns:
            True if successful, False otherwise
        """
        # Save current config first
        current_profile = self.profile
        result = self.save()
        
        # Switch to new profile and save default config
        self.profile = profile_name
        self.config = dict(self.DEFAULT_CONFIG)  # Reset to defaults
        new_result = self.save()
        
        # Switch back to original profile
        self.profile = current_profile
        self.load()  # Reload original config
        
        return result and new_result
    
    def switch_profile(self, profile_name: str) -> bool:
        """
        Switch to a different configuration profile.
        
        Args:
            profile_name: Name of the profile to switch to
            
        Returns:
            True if successful, False otherwise
        """
        # Save current config first
        result = self.save()
        
        # Switch profile and load its config
        self.profile = profile_name
        return result and self.load()
    
    def get_available_profiles(self) -> list:
        """
        Get a list of available configuration profiles.
        
        Returns:
            List of profile names
        """
        profiles = []
        for filename in os.listdir(self.config_dir):
            if filename.endswith('.json'):
                profiles.append(filename[:-5])  # Remove '.json' extension
        return profiles
    
    def export_config(self, export_path: str) -> bool:
        """
        Export configuration to a file.
        
        Args:
            export_path: Path to export file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(export_path, 'w') as f:
                json.dump(self.config, f, indent=2)
                
            logger.info(f"Configuration exported to {export_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting configuration: {e}")
            return False
    
    def import_config(self, import_path: str) -> bool:
        """
        Import configuration from a file.
        
        Args:
            import_path: Path to import file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(import_path, 'r') as f:
                imported_config = json.load(f)
                
                # Replace current config with imported config
                self.config = imported_config
                
                # Save to current profile
                result = self.save()
                
                logger.info(f"Configuration imported from {import_path}")
                return result
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing imported configuration file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error importing configuration: {e}")
            return False