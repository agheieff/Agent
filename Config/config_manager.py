"""
Configuration management for the Arcadia Agent.
Handles loading, validation, and access to configuration settings.
"""

import os
import re
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Manages configuration for the Arcadia Agent.
    
    This class handles loading configuration from various sources with the following priority:
    1. Environment variables (prefixed with ARCADIA_)
    2. User config.yaml
    3. Default configuration values
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Path to the configuration file. If None, will search in standard locations.
        """
        self.config: Dict[str, Any] = {}
        self.config_path = config_path or self._find_config_file()
        self.load_config()
        
    def _find_config_file(self) -> Path:
        """
        Find the configuration file in standard locations.
        
        Returns:
            Path to the configuration file.
        """
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
                
        # Return default path - will create default config there if it doesn't exist
        return Path(__file__).parent / "config.yaml"
        
    def load_config(self):
        """Load configuration from file and override with environment variables."""
        # Start with default config
        self.config = self._load_default_config()
        
        # Load from file if it exists
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self._update_dict_recursive(self.config, file_config)
            except Exception as e:
                logger.error(f"Error loading config from {self.config_path}: {e}")
        else:
            # Create default config file
            self._save_default_config()
            
        # Process variable interpolation
        self._process_variable_interpolation()
            
        # Override with environment variables
        self._apply_environment_variables()
        
    def _load_default_config(self) -> Dict[str, Any]:
        """Load the default configuration."""
        default_config_path = Path(__file__).parent / "defaults" / "default_config.yaml"
        
        if default_config_path.exists():
            try:
                with open(default_config_path, 'r') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Error loading default config: {e}")
        
        # Minimal default config if file doesn't exist
        return {
            "paths": {
                "memory_dir": str(Path.cwd() / "memory"),
                "projects_dir": str(Path.cwd() / "projects"),
                "temp_dir": str(Path.cwd() / "memory" / "temp"),
                "backup_dir": str(Path.cwd() / "memory" / "backups")
            },
            "memory": {
                "max_document_size": 1048576,
                "max_indexed_entries": 10000,
                "max_backups": 5,
                "backup_interval": 3600,
                "context_keys": [
                    "system_config", "tool_usage", "error_history", "active_projects", 
                    "agent_notes", "status_updates", "command_skills", "knowledge_base", 
                    "important", "task", "mind_map", "code", "project"
                ]
            },
            "llm": {
                "default_model": "deepseek",
                "models": ["anthropic", "deepseek"],
                "anthropic": {"temperature": 0.7, "max_tokens": 4000},
                "deepseek": {"temperature": 0.7, "max_tokens": 4000}
            },
            "agent": {
                "headless": False,
                "test_mode": False,
                "max_inactivity": 3600,
                "allow_internet": True,
                "max_tasks": 100,
                "monitor_resources": True,
                "resource_check_interval": 300
            },
            "security": {
                "restricted_dirs": ["/etc", "/var", "/boot", "/root"],
                "blocked_commands": ["rm -rf /", "mkfs", "dd", "wget", "curl", "sudo"],
                "max_file_size": 104857600
            },
            "logging": {
                "level": "INFO",
                "log_to_file": True,
                "log_file": "memory/logs/agent.log",
                "log_commands": True,
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        }
    
    def _save_default_config(self):
        """Save the default configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Created default configuration at {self.config_path}")
        except Exception as e:
            logger.error(f"Error creating default config: {e}")
            
    def _update_dict_recursive(self, target: Dict, source: Dict):
        """
        Update target dictionary recursively with values from source.
        
        Args:
            target: Target dictionary to update
            source: Source dictionary with new values
        """
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
                # Convert ARCADIA_PATHS_MEMORY_DIR to paths.memory_dir
                config_path = env_var[len(env_prefix):].lower().replace("_", ".")
                self.set_value(config_path, value)
                
    def _process_variable_interpolation(self):
        """Process variable interpolation in configuration values."""
        # Convert the config to string
        config_str = yaml.dump(self.config)
        
        # Find all ${...} patterns
        var_pattern = r'\${([^}]+)}'
        matches = re.findall(var_pattern, config_str)
        
        # Process each variable
        for variable in matches:
            # Get the current value
            try:
                value = self.get_value(variable)
                # Replace all occurrences of ${variable} with its value
                config_str = config_str.replace(f"${{{variable}}}", str(value))
            except:
                # Keep the original variable if it can't be resolved
                pass
                
        # Load back the processed config
        self.config = yaml.safe_load(config_str)
    
    def get_value(self, path: str, default: Any = None) -> Any:
        """
        Get a configuration value by path.
        
        Args:
            path: Dot-separated path to the configuration value (e.g., "paths.memory_dir")
            default: Default value to return if the path doesn't exist
            
        Returns:
            The configuration value at the specified path or the default value
        """
        parts = path.split('.')
        current = self.config
        
        try:
            for part in parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return default
            
    def set_value(self, path: str, value: Any):
        """
        Set a configuration value by path.
        
        Args:
            path: Dot-separated path to the configuration value (e.g., "paths.memory_dir")
            value: The value to set
        """
        parts = path.split('.')
        current = self.config
        
        # Navigate to the parent object
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            
        # Set the value
        current[parts[-1]] = value
        
    def save_config(self, path: Optional[Path] = None):
        """
        Save the current configuration to file.
        
        Args:
            path: Path to save the configuration to. If None, uses the current config_path.
        """
        save_path = path or self.config_path
        
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            
    def get_memory_path(self) -> Path:
        """Get the memory directory path."""
        memory_path = self.get_value("paths.memory_dir")
        return Path(memory_path)
        
    def get_projects_path(self) -> Path:
        """Get the projects directory path."""
        projects_path = self.get_value("paths.projects_dir")
        return Path(projects_path)
        
    def get_context_keys(self) -> List[str]:
        """Get the context keys for memory."""
        return self.get_value("memory.context_keys", [])
        
    def get_llm_config(self, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the configuration for a specific LLM model.
        
        Args:
            model: The model name. If None, uses the default model.
            
        Returns:
            Dictionary with model configuration
        """
        if model is None:
            model = self.get_value("llm.default_model", "deepseek")
            
        return self.get_value(f"llm.{model}", {})
        
    def is_test_mode(self) -> bool:
        """Check if the agent is running in test mode."""
        return self.get_value("agent.test_mode", False)
        
    def is_headless(self) -> bool:
        """Check if the agent is running in headless mode."""
        return self.get_value("agent.headless", False)
        
    def to_dict(self) -> Dict[str, Any]:
        """Return the entire configuration as a dictionary."""
        return self.config.copy()
        
    def get_config_summary(self) -> str:
        """
        Get a human-readable summary of the configuration.
        
        Returns:
            A string summarizing the key configuration settings
        """
        summary = "Arcadia Agent Configuration Summary:\n"
        summary += f"- Memory directory: {self.get_value('paths.memory_dir')}\n"
        summary += f"- Projects directory: {self.get_value('paths.projects_dir')}\n"
        summary += f"- Default LLM model: {self.get_value('llm.default_model')}\n"
        summary += f"- Test mode: {self.get_value('agent.test_mode')}\n"
        summary += f"- Headless mode: {self.get_value('agent.headless')}\n"
        summary += f"- Internet access: {self.get_value('agent.allow_internet')}\n"
        summary += f"- Log level: {self.get_value('logging.level')}\n"
        
        return summary

# Singleton instance
_config_manager: Optional[ConfigManager] = None

def get_config() -> ConfigManager:
    """
    Get the singleton ConfigManager instance.
    
    Returns:
        The ConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager