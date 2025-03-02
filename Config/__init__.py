"""
Arcadia Agent Configuration Package.

This package manages configuration settings for the Arcadia Agent, including:
- Path configurations (memory, projects, etc.)
- Agent behavior settings
- LLM model configurations
- Security settings
- Logging settings
"""

from .config_manager import ConfigManager, get_config

__all__ = ["ConfigManager", "get_config"]