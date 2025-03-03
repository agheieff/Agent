"""
Tool Parser for extracting and parsing tool invocations from messages.

This module is responsible for:
1. Extracting tool invocations from complete messages
2. Parsing each tool invocation into a tool name and parameters
3. Formatting tool execution results
"""

import logging
import re
from typing import Dict, Tuple, Optional, List, Any, Generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tool_parser")

class ToolParser:
    """
    Parser for extracting and processing tool invocations from messages.
    """

    # Regex pattern to match tool invocations in a message
    # Matches either:
    # 1. Lines starting with / followed by a word (e.g., /bash ls -la)
    # 2. Blocks of text between ``` or ```tool markers
    TOOL_PATTERN = r'(^/\w+(?:\s+.*)?$|```(?:tool)?\s*\n([\s\S]*?)\n```)'

    @staticmethod
    def extract_tools(message: str) -> List[str]:
        """
        Extract all tool invocations from a message.

        Args:
            message: The complete message to parse

        Returns:
            List of extracted tool invocation texts
        """
        if not message:
            return []

        # Find all matches of the tool pattern
        matches = re.finditer(ToolParser.TOOL_PATTERN, message, re.MULTILINE)
        tool_texts = []

        for match in matches:
            if match.group(1).startswith('/'):
                # Single line command (e.g., /bash ls -la)
                tool_texts.append(match.group(1))
            else:
                # Code block
                tool_texts.append(match.group(2))

        return tool_texts

    @staticmethod
    def parse_tool(tool_text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Parse a tool invocation into a tool name and parameters.

        Args:
            tool_text: The text of a single tool invocation

        Returns:
            Tuple of (tool_name, parameters_dict)

        Raises:
            ValueError: If the tool text is empty or malformed
        """
        if not tool_text:
            raise ValueError("Empty tool text")

        lines = tool_text.strip().split('\n')
        first_line = lines[0].strip()

        # Handle /command style
        if first_line.startswith('/'):
            first_line = first_line[1:]  # Remove the leading /
            parts = first_line.split(' ', 1)
            tool_name = parts[0].strip()

            params = {}
            if len(parts) > 1 and parts[1].strip():
                # For simple command invocation, put the rest in the 'value' parameter
                params['value'] = parts[1].strip()

        # Handle multi-line format
        else:
            tool_name = first_line
            params = {}

        # Parse additional parameters from subsequent lines
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            if ':' in line:
                key, value = line.split(':', 1)
                params[key.strip()] = value.strip()
            elif '=' in line:
                key, value = line.split('=', 1)
                params[key.strip()] = value.strip()
            else:
                # Consider the line as an additional argument
                if 'args' not in params:
                    params['args'] = []
                params['args'].append(line)

        return tool_name, params

    @staticmethod
    def format_result(tool_name: str, success: bool, output: Optional[str] = None, 
                      error: Optional[str] = None) -> Dict[str, Any]:
        """
        Format the result of a tool execution.

        Args:
            tool_name: The name of the tool
            success: Whether the tool execution was successful
            output: The output of the tool execution
            error: The error message if the tool execution failed

        Returns:
            Formatted result dictionary
        """
        result = {
            "tool": tool_name,
            "success": success
        }

        if success and output is not None:
            result["output"] = output
        elif not success and error is not None:
            result["error"] = error

        return result

    @staticmethod
    def process_message(message: str) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        """
        Process a complete message and yield all tool invocations.

        Args:
            message: The complete message to process

        Yields:
            Tuples of (tool_name, parameters_dict) for each valid tool invocation
        """
        tool_texts = ToolParser.extract_tools(message)

        for tool_text in tool_texts:
            try:
                tool_name, params = ToolParser.parse_tool(tool_text)
                yield tool_name, params
            except ValueError as e:
                logger.warning(f"Failed to parse tool invocation: {e}")
                continue