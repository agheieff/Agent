"""
Composer for formatting tool results into agent-friendly responses.
"""

import logging
from typing import List, Dict, Any, Tuple, Union

logger = logging.getLogger(__name__)

class ToolResponseComposer:
    """
    Composes responses from tool executions into a format suitable
    for sending back to the agent as a user message.
    """

    @staticmethod
    def format_tool_result(tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> str:
        """
        Format a single tool result

        Args:
            tool_name: Name of the tool that was executed
            params: Parameters that were passed to the tool
            result: Result dictionary from the tool execution

        Returns:
            Formatted string representing the tool result
        """
        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error", "")

        # Create a summary of the parameters for display
        params_str = " ".join([f"{k}={v}" for k, v in params.items()])

        formatted_result = f"Tool: /{tool_name} {params_str}\n"
        formatted_result += f"Status: {'Success' if success else 'Failed'}\n"

        if error:
            formatted_result += f"Error: {error}\n"

        if output:
            formatted_result += f"Output:\n{output}\n"

        return formatted_result

    @staticmethod
    def compose_response(tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        """
        Compose a complete response from multiple tool results

        Args:
            tool_results: List of tuples containing (tool_name, params, result)

        Returns:
            Formatted message to send back to the agent
        """
        if not tool_results:
            return "No tools were executed."

        response = "I've executed the following tools:\n\n"

        for tool_name, params, result in tool_results:
            formatted_result = ToolResponseComposer.format_tool_result(
                tool_name, params, result
            )
            response += f"{formatted_result}\n"

        response += "Please continue with your task based on these results."

        return response