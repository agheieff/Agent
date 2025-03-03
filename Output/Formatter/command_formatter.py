"""
Formatter for command execution results.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from Output.Config.config_manager import ConfigManager

class CommandFormatter:
    """Format command execution results with status indicators."""

    def __init__(self, config: Optional[ConfigManager] = None):
        """
        Initialize the command formatter.

        Args:
            config: Optional configuration manager
        """
        self.config = config or ConfigManager()

    def format_result(self, command: str, result: Dict[str, Any]) -> str:
        """
        Format command execution results to show status on the same line.

        Args:
            command: The executed command
            result: The command result dictionary with stdout, stderr, code

        Returns:
            Formatted output string
        """
        success = result.get('success', result.get('code', 1) == 0)
        code = result.get('code', 1)

        # Get symbols from config
        success_symbol = self.config.get("command_success_symbol", "✓")
        fail_symbol = self.config.get("command_fail_symbol", "✗")

        status = success_symbol if success else f"{fail_symbol} [code: {code}]"

        # Get just the first line of the command if it's multiline
        command_display = command.split('\n')[0]
        if len(command_display) > 60:
            command_display = command_display[:57] + "..."

        # Add timestamp if configured
        timestamp = ""
        if self.config.get("show_timestamps", True):
            timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] "

        output = f"{timestamp}{command_display} → {status}"

        if not success and result.get('stderr'):
            # Show a compact error message if configured
            if self.config.get("compact_errors", True):
                error_msg = result.get('stderr').split('\n')[0]
                max_len = self.config.get("max_error_length", 100)
                if error_msg:
                    if len(error_msg) > max_len:
                        error_msg = error_msg[:max_len] + "..."
                    output += f" Error: {error_msg}"

        return output

    def format_command_list(self, commands: List[Dict[str, Any]]) -> str:
        """
        Format a list of commands and their results.

        Args:
            commands: List of command dictionaries with command text and results

        Returns:
            Formatted output string
        """
        output_lines = []
        for cmd_entry in commands:
            cmd = cmd_entry.get('command', '')
            result = cmd_entry.get('result', {})
            output_lines.append(self.format_result(cmd, result))

        return '\n'.join(output_lines)