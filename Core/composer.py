import logging
import json
import datetime
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class ToolResponseComposer:
    def __init__(self):
        self.conversation_start_time = datetime.datetime.now()
        self.last_update_time = self.conversation_start_time
        self.turn_counter = 0
        self.total_tokens = 0

    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Any:
        formatted = {
            "tool": tool_name,
            "params": params,
            "success": result.get("success", False),
            "error": result.get("error", ""),
            "output": result.get("output", ""),
            "exit_code": 0 if result.get("success", False) else 1,
            "timestamp": datetime.datetime.now().isoformat()
        }
        return formatted

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> Any:
        self.turn_counter += 1
        formatted_results = [
            self.format_tool_result(tool, params, result)
            for tool, params, result in tool_results
        ]
        response = {
            "results": formatted_results,
            "conversation_stats": self._get_conversation_stats()
        }
        return json.dumps(response, indent=2)

    def update_token_count(self, additional_tokens: int):
        self.total_tokens += additional_tokens

    def _get_conversation_stats(self) -> Dict[str, Any]:
        now = datetime.datetime.now()
        return {
            "turn_number": self.turn_counter,
            "total_tokens": self.total_tokens,
            "conversation_duration": str(now - self.conversation_start_time),
            "time_since_last_update": str(now - self.last_update_time),
            "current_timestamp": now.isoformat(),
            "formatted_time": now.strftime('%Y-%m-%d %H:%M:%S')
        }

class TextFormatComposer(ToolResponseComposer):
    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> str:
        status = "Success" if result.get("success", False) else "Failed"
        output = result.get("output", "") if result.get("success", False) else result.get("error", "")
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        return f"Tool: {tool_name}\nParameters: {param_str}\nStatus: {status}\nOutput:\n{output}"

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        parts = ["I've executed the following tools:"]
        for tool, params, result in tool_results:
            parts.append(self.format_tool_result(tool, params, result))
        if not tool_results:
            return "No tools were executed."
        parts.append("Please continue based on these results.")
        return "\n\n".join(parts)

class JSONFormatComposer(ToolResponseComposer):
    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tool": tool_name,
            "params": params,
            "success": result.get("success", False),
            "output": result.get("output", ""),
            "error": result.get("error", ""),
            "exit_code": 0 if result.get("success", False) else 1,
            "timestamp": datetime.datetime.now().isoformat()
        }

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
        formatted_results = [self.format_tool_result(tool, params, result) for tool, params, result in tool_results]
        response = {
            "results": formatted_results,
            "message": "Tool execution complete." if tool_results else "No tools were executed."
        }
        return json.dumps(response, indent=2)
