"""
Configuration manager for output settings.
"""

import os
from pathlib import Path
import json
from typing import Dict, Any, Optional, Union

class ConfigManager:
    """Manager for output configuration settings."""

    DEFAULT_CONFIG = {
        "command_success_symbol": "✓",
        "command_fail_symbol": "✗",
        "max_error_length": 100,
        "max_output_lines": 10,
        "show_timestamps": True,
        "colors_enabled": True,
        "compact_errors": True,
        "indent_size": 2,
        "verbose_output": False,
        "show_conversation_roles": True
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config manager.

        Args:
            config_path: Optional path to config file
        """
        self.config_path = config_path or str(Path.home() / ".agent_output_config.json")
        self.settings = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file or create default.

        Returns:
            Config dictionary
        """
        config_file = Path(self.config_path)
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    loaded_config = json.load(f)

                # Merge with defaults to ensure all keys exist
                config = self.DEFAULT_CONFIG.copy()
                config.update(loaded_config)
                return config
            except Exception as e:
                print(f"Error loading output config, using defaults: {e}")
                return self.DEFAULT_CONFIG.copy()
        else:
            # Create default config file
            config = self.DEFAULT_CONFIG.copy()
            try:
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not save default config: {e}")

            return config

    def save_config(self):
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving output config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: Value to set
        """
        self.settings[key] = value
        self.save_config()

    def update(self, settings: Dict[str, Any]):
        """
        Update multiple settings at once.

        Args:
            settings: Dictionary of settings to update
        """
        self.settings.update(settings)
        self.save_config()

    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        self.settings = self.DEFAULT_CONFIG.copy()
        self.save_config()

    @property
    def all_settings(self) -> Dict[str, Any]:
        """Get all settings as a dictionary."""
        return self.settings.copy()