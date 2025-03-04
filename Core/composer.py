import logging
import json
import datetime
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class ResponseComposer:
    def __init__(self):
        # Conversation tracking
        self.conversation_start_time = datetime.datetime.now()
        self.last_update_time = self.conversation_start_time
        self.turn_counter = 0
        self.total_tokens = 0  # Update this externally as needed

    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tool": tool_name,
            "params": params,
            "success": result.get("success", False),
            "error": result.get("error", ""),
            "output": result.get("output", ""),
            "exit_code": 0 if result.get("success", False) else 1,
            "timestamp": datetime.datetime.now().isoformat()
        }

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
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
