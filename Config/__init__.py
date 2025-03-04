"""
Configuration package for handling agent settings.

This package provides configuration management for the Arcadia Agent,
primarily focusing on loading, accessing, and modifying configuration settings.
"""

from .config import Config, config

__all__ = ["Config", "config"]
