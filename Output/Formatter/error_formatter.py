"""
Formatter for API and system errors.
"""

from typing import Optional, List, Dict, Any

from Output.Config.config_manager import ConfigManager

class ErrorFormatter:
    """Format error messages for display."""

    def __init__(self, config: Optional[ConfigManager] = None):
        """
        Initialize the error formatter.

        Args:
            config: Optional configuration manager
        """
        self.config = config or ConfigManager()

    def format_api_error(self, error_msg: str) -> str:
        """
        Format API errors to be more compact.

        Args:
            error_msg: The original error message

        Returns:
            Formatted error message
        """
        # Return full error if compact_errors is disabled
        if not self.config.get("compact_errors", True):
            return f"API Error: {error_msg}"

        # Extract the most important part of the error
        lines = error_msg.split('\n')
        if not lines:
            return "API Error: Unknown error"

        # First try to find any line with "error" in it
        error_lines = [line for line in lines if 'error' in line.lower()]
        if error_lines:
            return f"API Error: {error_lines[0].strip()}"

        # Otherwise just return the first line
        max_len = self.config.get("max_error_length", 100)
        first_line = lines[0].strip()
        if len(first_line) > max_len:
            first_line = first_line[:max_len] + "..."

        return f"API Error: {first_line}"

    def format_system_error(self, error_msg: str, context: Optional[str] = None) -> str:
        """
        Format system errors for display.

        Args:
            error_msg: The error message
            context: Optional context information

        Returns:
            Formatted error message
        """
        if not self.config.get("compact_errors", True):
            if context:
                return f"System Error [{context}]: {error_msg}"
            return f"System Error: {error_msg}"

        # Make compact error message
        lines = error_msg.split('\n')
        if not lines:
            return f"System Error: Unknown error"

        max_len = self.config.get("max_error_length", 100)
        first_line = lines[0].strip()
        if len(first_line) > max_len:
            first_line = first_line[:max_len] + "..."

        if context:
            return f"System Error [{context}]: {first_line}"
        return f"System Error: {first_line}"