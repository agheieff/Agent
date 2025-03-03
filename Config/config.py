"""
Configuration module for the Arcadia Agent.

This module provides a simple interface for accessing and managing agent configuration settings,
with support for configuration via files, environment variables, and code.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)

class Config:
    """
    Configuration handler for the Arcadia Agent.
    
    This class handles loading configurations from various sources with the following priority:
    1. Environment variables (prefixed with ARCADIA_)
    2. Custom config.yaml
    3. Default configuration values
    
    For now, it only handles test_mode, but will be expanded later.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration handler.
        
        Args:
            config_path: Optional path to a custom config.yaml file
        """
        self._config: Dict[str, Any] = {}
        self._config_path = config_path or self._find_config_file()
        self._load_config()
    
    def _find_config_file(self) -> Path:
        """Find the configuration file in standard locations."""
        # Check environment variable first
        if os.environ.get("ARCADIA_CONFIG_PATH"):
            env_path = Path(os.environ.get("ARCADIA_CONFIG_PATH"))
            if env_path.exists():
                return env_path
        
        # Standard locations to check
        search_paths = [
            Path.cwd() / "Config" / "config.yaml",
            Path.cwd() / "config.yaml", 
            Path.home() / ".arcadia" / "config.yaml",
            Path(__file__).parent / "config.yaml"
        ]
        
        for path in search_paths:
            if path.exists():
                return path
        
        # Default path if no config found
        return Path(__file__).parent / "config.yaml"
    
    def _load_config(self):
        """Load configuration from defaults, file, and environment variables."""
        # Start with default config
        self._config = self._load_default_config()
        
        # Override with file config if exists
        if self._config_path.exists():
            try:
                with open(self._config_path, 'r') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self._update_dict_recursive(self._config, file_config)
            except Exception as e:
                logger.error(f"Error loading config from {self._config_path}: {e}")
        
        # Override with environment variables
        self._apply_environment_variables()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load the default configuration from defaults.yaml."""
        default_config_path = Path(__file__).parent / "defaults.yaml"
        
        if default_config_path.exists():
            try:
                with open(default_config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading default config: {e}")
        
        # Minimal fallback if defaults.yaml is missing
        return {"agent": {"test_mode": False}}
    
    def _update_dict_recursive(self, target: Dict, source: Dict):
        """Update target dictionary recursively with values from source."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._update_dict_recursive(target[key], value)
            else:
                target[key] = value
    
    def _apply_environment_variables(self):
        """Override configuration values with environment variables."""
        env_prefix = "ARCADIA_"
        
        for env_var, value in os.environ.items():
            if env_var.startswith(env_prefix):
                # Convert ARCADIA_AGENT_TEST_MODE to agent.test_mode
                config_path = env_var[len(env_prefix):].lower().replace("_", ".")
                self.set(config_path, value)
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a configuration value by path.
        
        Args:
            path: Dot-separated path to the configuration value (e.g., "agent.test_mode")
            default: Default value to return if the path doesn't exist
        
        Returns:
            The configuration value at the specified path, or the default value
        """
        parts = path.split('.')
        current = self._config
        
        try:
            for part in parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return default
    
    def set(self, path: str, value: Any):
        """
        Set a configuration value by path.
        
        Args:
            path: Dot-separated path to the configuration value (e.g., "agent.test_mode")
            value: The value to set
        """
        parts = path.split('.')
        current = self._config
        
        # Navigate to the parent object
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Convert string values to appropriate types
        if isinstance(value, str):
            if value.lower() in ('true', 'yes', 'y', '1'):
                value = True
            elif value.lower() in ('false', 'no', 'n', '0'):
                value = False
            elif value.isdigit():
                value = int(value)
        
        # Set the value
        current[parts[-1]] = value
    
    def save(self, path: Optional[Path] = None):
        """
        Save the current configuration to file.
        
        Args:
            path: Path to save the configuration to. If None, uses the current config_path.
        """
        save_path = path or self._config_path
        
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False)
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def is_test_mode(self) -> bool:
        """Check if the agent is running in test mode."""
        return self.get("agent.test_mode", False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Return the entire configuration as a dictionary."""
        return self._config.copy()


# Singleton instance
config = Config()

def get_test_mode() -> bool:
    """Get whether test mode is enabled."""
    return config.is_test_mode()