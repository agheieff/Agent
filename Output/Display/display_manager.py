"""
Manager for console display output.
"""

import sys
import os
import shutil
from typing import Dict, Any, List, Optional, Tuple

from Output.Config.config_manager import ConfigManager
from Output.Formatter.command_formatter import CommandFormatter
from Output.Formatter.error_formatter import ErrorFormatter

class DisplayManager:
    """
    Manages the display of output to the console.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the display manager.

        Args:
            config_path: Optional path to config file
        """
        self._config = ConfigManager(config_path)
        self._command_formatter = CommandFormatter(self._config)
        self._error_formatter = ErrorFormatter(self._config)
        self._terminal_size = self._get_terminal_size()

    def _get_terminal_size(self) -> Tuple[int, int]:
        """
        Get the terminal size.

        Returns:
            Tuple of (width, height)
        """
        try:
            columns, lines = shutil.get_terminal_size()
            return columns, lines
        except Exception:
            # Default fallback size
            return 80, 24

    def update_terminal_size(self):
        """Update the stored terminal size."""
        self._terminal_size = self._get_terminal_size()

    def display_command_result(self, command: str, result: Dict[str, Any]):
        """
        Display a command result with inline status.

        Args:
            command: The command that was executed
            result: The command result dictionary
        """
        # Format the command result line
        formatted = self._command_formatter.format_result(command, result)

        # Use colors if enabled
        if self._config.get("colors_enabled", True):
            if result.get('success', result.get('code', 1) == 0):
                formatted = f"\033[32m{formatted}\033[0m"  # Green for success
            else:
                formatted = f"\033[31m{formatted}\033[0m"  # Red for failure

        print(formatted)

        # If successful and has output, display it indented
        if result.get('success', False) and result.get('stdout'):
            # Only display output if verbose mode is enabled or output is short
            if self._config.get("verbose_output", False) or len(result.get('stdout', '').splitlines()) <= 3:
                indent = ' ' * self._config.get("indent_size", 2)
                max_lines = self._config.get("max_output_lines", 10)

                # Limit output lines if very verbose
                lines = result.get('stdout', '').splitlines()
                if len(lines) > max_lines and not self._config.get("verbose_output", False):
                    output = '\n'.join(lines[:max(1, max_lines-5)] + ['...'] + lines[-min(3, max_lines-1):])
                else:
                    output = result.get('stdout')

                for line in output.splitlines():
                    print(f"{indent}{line}")

    def display_api_error(self, error_msg: str):
        """
        Display an API error in a compact format.

        Args:
            error_msg: The error message from the API
        """
        formatted = self._error_formatter.format_api_error(error_msg)

        # Use colors if enabled
        if self._config.get("colors_enabled", True):
            formatted = f"\033[31m{formatted}\033[0m"  # Red text for errors

        print(formatted)

    def display_system_error(self, error_msg: str, context: Optional[str] = None):
        """
        Display a system error.

        Args:
            error_msg: The error message
            context: Optional context about the error
        """
        formatted = self._error_formatter.format_system_error(error_msg, context)

        # Use colors if enabled
        if self._config.get("colors_enabled", True):
            formatted = f"\033[31m{formatted}\033[0m"  # Red text for errors

        print(formatted)

    def display_command_list(self, commands: List[Dict[str, Any]]):
        """
        Display a list of commands and their results.

        Args:
            commands: List of command dictionaries
        """
        formatted = self._command_formatter.format_command_list(commands)
        print(formatted)

    def display_banner(self, message: str):
        """
        Display a banner message.

        Args:
            message: The message to display in the banner
        """
        width = self._terminal_size[0]
        padding = max(0, (width - len(message) - 4) // 2)

        print("=" * width)
        print(f"{' ' * padding}| {message} |{' ' * padding}")
        print("=" * width)

    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def display_progress(self, message: str, percent: float):
        """
        Display a progress bar.

        Args:
            message: The message to display with the progress bar
            percent: The percentage of completion (0-100)
        """
        width = self._terminal_size[0] - len(message) - 10
        filled_length = int(width * percent / 100)
        bar = '█' * filled_length + '-' * (width - filled_length)

        sys.stdout.write(f'\r{message} |{bar}| {percent:.1f}%')
        sys.stdout.flush()

        if percent >= 100:
            sys.stdout.write('\n')

    @property
    def config(self) -> ConfigManager:
        """Get the configuration manager."""
        return self._config