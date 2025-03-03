"""
Output management module for displaying and formatting command results.
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from Output.config import OutputConfig

class OutputFormatter:
    """
    Formats output from commands and API calls for better readability.
    """
    
    def __init__(self, config: Optional[OutputConfig] = None):
        """
        Initialize the formatter with configuration.
        
        Args:
            config: Optional configuration, will use default if None
        """
        self.config = config or OutputConfig()
    
    def format_command_result(self, command: str, result: Dict[str, Any]) -> str:
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
        
        # Get symbols from config, use ASCII-only versions
        success_symbol = self.config.get("command_success_symbol", "[OK]")
        fail_symbol = self.config.get("command_fail_symbol", "[FAIL]")
        
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
        return f"API Error: {lines[0].strip()}"
    
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
            output_lines.append(self.format_command_result(cmd, result))
        
        return '\n'.join(output_lines)