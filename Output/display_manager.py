"""
Display manager for handling console output.
"""

import sys
import os
import shutil
from typing import Dict, Any, List, Optional, Tuple

from Output import OutputFormatter
from Output.config import OutputConfig

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
        self._config = OutputConfig(config_path)
        self._formatter = OutputFormatter(self._config)
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
        # Get verbose level to determine output detail
        verbose_level = self._config.get("verbose_level", 0)
        verbose_output = self._config.get("verbose_output", False)
        
        # Format the command result line
        formatted = self._formatter.format_command_result(command, result)
        
        # Use colors if enabled
        if self._config.get("colors_enabled", True):
            if result.get('success', result.get('code', 1) == 0):
                formatted = f"\033[32m{formatted}\033[0m"  # Green for success
            else:
                formatted = f"\033[31m{formatted}\033[0m"  # Red for failure
        
        print(formatted)
        
        # Verbose level determines output display
        show_output = (verbose_output or verbose_level >= 1 or 
                      (verbose_level == 0 and result.get('stdout', '') and 
                       len(result.get('stdout', '').splitlines()) <= 3))
        
        # If has output and verbose settings allow display
        if result.get('stdout'):
            if show_output:
                indent = ' ' * self._config.get("indent_size", 2)
                
                # Determine max lines based on verbose level
                if verbose_level >= 3:  # Debug level - show everything
                    max_lines = 1000
                elif verbose_level >= 2:  # Detailed level
                    max_lines = 30
                elif verbose_level >= 1:  # Normal level
                    max_lines = 15
                else:  # Minimal level
                    max_lines = self._config.get("max_output_lines", 10)
                
                # Limit output lines based on verbose level
                lines = result.get('stdout', '').splitlines()
                if len(lines) > max_lines and verbose_level < 3:
                    # More sophisticated truncation for different verbose levels
                    if verbose_level >= 2:
                        # Show more content with clearer markers in detailed mode
                        head_lines = max(5, max_lines // 2)
                        tail_lines = max(5, max_lines - head_lines - 1)
                        output = '\n'.join(
                            lines[:head_lines] + 
                            [f"... {len(lines) - head_lines - tail_lines} more lines ..."] + 
                            lines[-tail_lines:]
                        )
                    else:
                        # Basic truncation for lower verbose levels
                        output = '\n'.join(
                            lines[:max(1, max_lines-5)] + 
                            ['...'] + 
                            lines[-min(3, max_lines-1):]
                        )
                else:
                    output = result.get('stdout')
                
                # Output each line with indentation
                for line in output.splitlines():
                    print(f"{indent}{line}")
            elif verbose_level >= 1:
                # In normal verbose mode, at least indicate that output was truncated
                line_count = len(result.get('stdout', '').splitlines())
                print(f"  ... {line_count} lines of output (use higher verbose level to see) ...")
        
        # Always show stderr if present, regardless of verbose level
        if result.get('stderr') and result.get('stderr', '').strip():
            indent = ' ' * self._config.get("indent_size", 2)
            print(f"{indent}\033[31m[Error Output]\033[0m")
            for line in result.get('stderr', '').splitlines()[:10]:  # Limit error lines
                print(f"{indent}{line}")
    
    def display_api_error(self, error_msg: str):
        """
        Display an API error in a compact format.
        
        Args:
            error_msg: The error message from the API
        """
        formatted = self._formatter.format_api_error(error_msg)
        
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
        formatted = self._formatter.format_command_list(commands)
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