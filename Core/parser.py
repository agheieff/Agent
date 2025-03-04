import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ToolParser:
    def parse_message(self, message: str) -> Dict[str, Any]:
        try:
            data = json.loads(message.strip())
            if not isinstance(data, dict):
                raise ValueError("Top-level JSON is not an object.")
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            return {"tool_calls": []}
        
        if "tool_calls" not in data:
            data["tool_calls"] = []
        return data
