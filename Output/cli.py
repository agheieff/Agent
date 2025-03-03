#!/usr/bin/env python3
"""
CLI tool for configuring output display settings.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any, Optional

from Output.config import OutputConfig

def list_settings(config: OutputConfig):
    """
    Display the current configuration settings.

    Args:
        config: The output configuration
    """
    print("\nCurrent Output Configuration:")
    print("-" * 30)
    for key, value in config.settings.items():
        print(f"{key}: {value}")
    print("-" * 30)

def update_setting(config: OutputConfig, key: str, value: str):
    """
    Update a configuration setting.

    Args:
        config: The output configuration
        key: The setting key to update
        value: The value to set (will be parsed as JSON)
    """
    if key not in config.settings:
        print(f"Error: Unknown setting '{key}'")
        print("Available settings:")
        for k in config.settings:
            print(f"  - {k}")
        return

    # Try to parse the value as JSON
    try:
        parsed_value = json.loads(value)
        config.set(key, parsed_value)
        print(f"Updated {key} = {parsed_value}")
    except json.JSONDecodeError:
        # If not valid JSON, treat as string
        config.set(key, value)
        print(f"Updated {key} = {value}")

def reset_to_defaults(config: OutputConfig):
    """
    Reset all settings to defaults.

    Args:
        config: The output configuration
    """
    config.reset_to_defaults()
    print("Settings reset to defaults")
    list_settings(config)

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Configure output display settings")
    parser.add_argument("--config", help="Path to config file (default: ~/.agent_output_config.json)")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List settings command
    list_parser = subparsers.add_parser("list", help="List current settings")

    # Update setting command
    update_parser = subparsers.add_parser("set", help="Update a setting")
    update_parser.add_argument("key", help="Setting key to update")
    update_parser.add_argument("value", help="Value to set (will be parsed as JSON if possible)")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset to default settings")

    args = parser.parse_args()

    # Load config
    config = OutputConfig(args.config)

    if args.command == "list" or not args.command:
        list_settings(config)
    elif args.command == "set":
        update_setting(config, args.key, args.value)
    elif args.command == "reset":
        reset_to_defaults(config)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()