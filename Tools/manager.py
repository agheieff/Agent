"""
Tool manager for integrating parser, executor, and composer.
"""

import logging
import asyncio
from typing import List, Dict, Any, Tuple

from Tools.parser import ToolParser
from Tools.executor import execute_tool

# Import output manager - we use a try/except to handle circular imports
try:
    from Output import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolManager:
    """
    Manages the entire tool execution pipeline:
    1. Parses agent messages to extract tool calls
    2. Executes tools
    3. Composes responses for the agent
    """

    def __init__(self):
        self.parser = ToolParser()

    async def process_message(self, message: str) -> str:
        """
        Process an agent message and execute any tool calls.

        Args:
            message: The message from the agent

        Returns:
            A response message to send back to the agent
        """
        # Extract tool calls from the message
        tool_calls = self.parser.extract_tool_calls(message)

        if not tool_calls:
            return ""

        # Execute each tool call
        results = []

        for tool_name, params, is_help in tool_calls:
            logger.info(f"Executing tool: {tool_name} with params: {params}, help={is_help}")

            # Handle help requests
            if is_help:
                # Add help=True parameter to get tool help info
                result = await execute_tool(tool_name, {"help": True})
            else:
                # Execute the tool with the provided parameters
                result = await execute_tool(tool_name, params)

            # The tool execution already sends output to the output manager
            # via the ToolHandler.run method
            results.append((tool_name, params, result))

        # No need to compose a response since the OutputManager has already displayed the output
        return ""

    async def execute_single_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single tool directly.

        Args:
            tool_name: The name of the tool to execute
            params: Parameters to pass to the tool

        Returns:
            The tool result
        """
        # The execute_tool function will implicitly send output to the output manager
        # through the ToolHandler.run method
        return await execute_tool(tool_name, params)

    async def execute_tools_concurrently(self, tool_requests: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
        """
        Execute multiple tools concurrently.

        Args:
            tool_requests: List of (tool_name, params) tuples

        Returns:
            List of (tool_name, params, result) tuples
        """
        async def _execute_tool(tool_name, params):
            # The execute_tool function will implicitly send output to the output manager
            # through the ToolHandler.run method
            result = await execute_tool(tool_name, params)
            return tool_name, params, result

        tasks = [_execute_tool(name, params) for name, params in tool_requests]
        results = await asyncio.gather(*tasks)

        # If tool outputs should be collected and returned as a batch, the output manager
        # can be updated to have a batch mode that collects outputs first
        return results