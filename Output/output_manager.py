"""
Output Manager for handling tool outputs and user interactions.
"""

import sys
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class OutputManager:
    """
    Manages the output from tools and user interactions.

    Responsibilities:
    1. Receive output from tool executions
    2. Format outputs according to tool-specific formatters
    3. Display formatted output to the user
    4. Handle user input when needed
    """

    def __init__(self):
        self.tool_formatters = {}
        self._register_default_formatters()

    def _register_default_formatters(self):
        """Register default formatters for common output types."""
        # Default formatter just returns the output as is
        self.register_formatter("default", self._default_formatter)

        # These will be defined by tool handlers later
        # Just placeholders for now
        self.register_formatter("error", self._error_formatter)
        self.register_formatter("command", self._command_formatter)

    def register_formatter(self, tool_name: str, formatter_func):
        """
        Register a custom formatter for a specific tool.

        Args:
            tool_name: The name of the tool
            formatter_func: Function that formats the tool output
        """
        self.tool_formatters[tool_name] = formatter_func

    async def handle_tool_output(self, tool_name: str, output: Dict[str, Any]) -> str:
        self.display_output(formatted_output)

        return formatted_output

    async def handle_tool_outputs(self, tool_outputs: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
        for tool_name, output in tool_outputs:
            formatted_output = await self.handle_tool_output(tool_name, output)
            formatted_outputs.append(formatted_output)

        return formatted_outputs

    def display_output(self, output: str):
        print(output)

        sys.stdout.flush()

    async def get_user_input(self, prompt: str = "> ") -> str:
        print(prompt, end="", flush=True)

        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, sys.stdin.readline)

        return user_input.rstrip("\n")

    async def get_user_confirmation(self, prompt: str = "Confirm? [y/N]: ") -> bool:
        response = await self.get_user_input(prompt)
        return response.lower() in ["y", "yes"]

    # Default formatters
    async def _default_formatter(self, output: Dict[str, Any]) -> str:
        if isinstance(output, dict):
            if "error" in output and output["error"]:
                return f"Error: {output['error']}"
            elif "output" in output:
                return str(output["output"])
            else:
                return str(output)
        else:
            return str(output)

    async def _error_formatter(self, output: Dict[str, Any]) -> str:
        error_msg = output.get("error", "Unknown error")
        return f"Error: {error_msg}"

    async def _command_formatter(self, output: Dict[str, Any]) -> str:
        cmd_output = output.get("output", "")
        exit_code = output.get("exit_code", 0)

        if exit_code != 0:
            error = output.get("error", "")
            return f"Command failed (exit code {exit_code}):\n{error}\n{cmd_output}"
        else:
            return cmd_output

output_manager = OutputManager()
