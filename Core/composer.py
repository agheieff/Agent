"""
Composer for formatting tool results into agent-friendly responses.
"""

import logging
from typing import List, Dict, Any, Tuple, Union

logger = logging.getLogger(__name__)

class ToolResponseComposer:

    @staticmethod
    def format_tool_result(tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> str:
        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error", "")


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
