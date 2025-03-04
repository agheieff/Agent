"""
Composer for formatting tool results into agent-friendly responses.
"""

import logging
import json
import datetime
from typing import List, Dict, Any, Tuple, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class FormatComposer(ABC):
    """
    Abstract base class for response formatters.
    """

    @abstractmethod
    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Any:
        """Format a single tool result"""
        pass

    @abstractmethod
    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        """Compose a full response from multiple tool results"""
        pass

class TextFormatComposer(FormatComposer):
    """
    Text-based formatter for tool results.
    """

    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Format a single tool result as text"""
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
        formatted_result += f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        if error:
            formatted_result += f"Error: {error}\n"

        if output:
            formatted_result += f"Output:\n{output}\n"

        return formatted_result

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        """Compose a full response from multiple tool results as text"""
        if not tool_results:
            return "No tools were executed."

        response = "I've executed the following tools:\n\n"

        for tool_name, params, result in tool_results:
            formatted_result = self.format_tool_result(tool_name, params, result)
            response += f"{formatted_result}\n"

        # Add conversation statistics
        response += self._add_conversation_stats()
        
        response += "Please continue based on these results."

        return response
        
    def _add_conversation_stats(self) -> str:
        """Add conversation statistics"""
        # This could be expanded to include more stats
        current_time = datetime.datetime.now()
        stats = "--- Conversation Statistics ---\n"
        stats += f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        return stats

class JSONFormatComposer(FormatComposer):
    """
    JSON-based formatter for tool results.
    """

    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Format a single tool result as a dictionary"""
        return {
            "tool": tool_name,
            "params": params,
            "success": result.get("success", False),
            "error": result.get("error", ""),
            "output": result.get("output", ""),
            "exit_code": result.get("exit_code", 1 if not result.get("success", False) else 0),
            "timestamp": datetime.datetime.now().isoformat()
        }

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        """Compose a full response from multiple tool results as JSON"""
        if not tool_results:
            return json.dumps({"message": "No tools were executed."})

        json_results = []
        for tool_name, params, result in tool_results:
            json_results.append(self.format_tool_result(tool_name, params, result))

        response = {
            "results": json_results,
            "message": "Tool execution complete.",
            "conversation_stats": self._get_conversation_stats()
        }

        return json.dumps(response, indent=2)
        
    def _get_conversation_stats(self) -> Dict[str, Any]:
        """Get conversation statistics as a dictionary"""
        current_time = datetime.datetime.now()
        return {
            "timestamp": current_time.isoformat(),
            "human_readable_time": current_time.strftime('%Y-%m-%d %H:%M:%S'),
        }

class ToolResponseComposer:
    """
    Main composer class that manages different format composers.
    """

    def __init__(self):
        """Initialize with default formatters"""
        self.composers = {
            "text": TextFormatComposer(),
            "json": JSONFormatComposer()
        }
        self.default_format = "text"
        
        # Conversation tracking
        self.conversation_start_time = datetime.datetime.now()
        self.last_compact_time = self.conversation_start_time
        self.turn_counter = 0
        self.total_tokens = 0

    def register_composer(self, format_name: str, composer: FormatComposer):
        """Register a new format composer"""
        self.composers[format_name] = composer

    def set_default_format(self, format_name: str):
        """Set the default response format"""
        if format_name in self.composers:
            self.default_format = format_name
        else:
            logger.warning(f"Format {format_name} not registered, keeping default {self.default_format}")

    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any],
                          format_name: str = None) -> Any:
        """Format a single tool result using the specified formatter"""
        format_name = format_name or self.default_format
        composer = self.composers.get(format_name, self.composers[self.default_format])
        
        # Check if this is a compact tool and update last_compact_time
        if tool_name == "compact" and result.get("success", False):
            self.last_compact_time = datetime.datetime.now()
            
        return composer.format_tool_result(tool_name, params, result)

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
                         format_name: str = None) -> str:
        """Compose a full response from multiple tool results"""
        self.turn_counter += 1
        
        format_name = format_name or self.default_format
        composer = self.composers.get(format_name, self.composers[self.default_format])
        
        # Add conversation tracking info to the result
        result = composer.compose_response(tool_results)
        
        # If the result is JSON, we need to parse, add stats, and re-serialize
        if format_name == "json":
            try:
                result_dict = json.loads(result)
                result_dict["conversation_stats"] = self._get_conversation_stats()
                result = json.dumps(result_dict, indent=2)
            except json.JSONDecodeError:
                logger.warning("Failed to add stats to JSON result, returning as is")
        
        return result

    def update_token_count(self, additional_tokens: int):
        """Update the total token count"""
        self.total_tokens += additional_tokens

    def _get_conversation_stats(self) -> Dict[str, Any]:
        """Get comprehensive conversation statistics"""
        current_time = datetime.datetime.now()
        
        stats = {
            "turn_number": self.turn_counter,
            "total_tokens": self.total_tokens,
            "conversation_duration": str(current_time - self.conversation_start_time),
            "time_since_last_compact": str(current_time - self.last_compact_time),
            "current_timestamp": current_time.isoformat(),
            "formatted_time": current_time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return stats

    @staticmethod
    def format_result_as_json(tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Static method to format a result as JSON"""
        return JSONFormatComposer().format_tool_result(tool_name, params, result)

    @staticmethod
    def compose_json_response(tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        """Static method to compose a response as JSON"""
        return JSONFormatComposer().compose_response(tool_results)
