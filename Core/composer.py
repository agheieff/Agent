"""
Composer for formatting tool results into agent-friendly responses.
"""

import logging
import json
from typing import List, Dict, Any, Tuple, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class FormatComposer(ABC):


    @abstractmethod
    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Any:

        pass

    @abstractmethod
    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:

        pass

class TextFormatComposer(FormatComposer):


    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> str:

        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error", "")

        params_formatted = []
        for k, v in params.items():
            if isinstance(v, str) and "\n" in v:
                params_formatted.append(f"{k}=<multiline content>")
            elif isinstance(v, (dict, list)):
                params_formatted.append(f"{k}=<complex value>")
            else:
                params_formatted.append(f"{k}={v}")

        params_str = ", ".join(params_formatted)

        formatted_result = f"Tool: {tool_name}\n"
        formatted_result += f"Parameters: {params_str}\n"
        formatted_result += f"Status: {'Success' if success else 'Failed'}\n"

        if error:
            formatted_result += f"Error: {error}\n"

        if output:
            formatted_result += f"Output:\n{output}\n"

        return formatted_result

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:

        if not tool_results:
            return "No tools were executed."

        response = "I've executed the following tools:\n\n"

        for tool_name, params, result in tool_results:
            formatted_result = self.format_tool_result(tool_name, params, result)
            response += f"{formatted_result}\n"

        response += "Please continue based on these results."

        return response

class JSONFormatComposer(FormatComposer):


    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:

        return {
            "tool": tool_name,
            "params": params,
            "success": result.get("success", False),
            "error": result.get("error", ""),
            "output": result.get("output", ""),
            "exit_code": result.get("exit_code", 1 if not result.get("success", False) else 0)
        }

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:

        if not tool_results:
            return json.dumps({"message": "No tools were executed."})

        json_results = []
        for tool_name, params, result in tool_results:
            json_results.append(self.format_tool_result(tool_name, params, result))

        response = {
            "results": json_results,
            "message": "Tool execution complete."
        }

        return json.dumps(response, indent=2)

class ToolResponseComposer:


    def __init__(self):

        self.composers = {
            "text": TextFormatComposer(),
            "json": JSONFormatComposer()
        }
        self.default_format = "text"

    def register_composer(self, format_name: str, composer: FormatComposer):

        self.composers[format_name] = composer

    def set_default_format(self, format_name: str):

        if format_name in self.composers:
            self.default_format = format_name
        else:
            logger.warning(f"Format {format_name} not registered, keeping default {self.default_format}")

    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any],
                          format_name: str = None) -> Any:

        format_name = format_name or self.default_format
        composer = self.composers.get(format_name, self.composers[self.default_format])
        return composer.format_tool_result(tool_name, params, result)

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
                         format_name: str = None) -> str:

        format_name = format_name or self.default_format
        composer = self.composers.get(format_name, self.composers[self.default_format])
        return composer.compose_response(tool_results)


    @staticmethod
    def format_result_as_json(tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:

        return JSONFormatComposer().format_tool_result(tool_name, params, result)

    @staticmethod
    def compose_json_response(tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:

        return JSONFormatComposer().compose_response(tool_results)
