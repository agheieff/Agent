import json
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ToolParser:
    """
    Parses model responses assuming they return JSON of the form:
    {
      "thinking": "...",
      "analysis": "...",
      "tool_calls": [
        { "name": "some_tool", "params": {...} },
        ...
      ],
      "answer": "..."
    }
    """

    @staticmethod
    def parse_message(message: str) -> Dict[str, Any]:
        """
        Attempt to parse the entire message as JSON. Return a dictionary with
        "thinking", "analysis", "tool_calls", and "answer".
        If parsing fails, log an error and return a minimal dict.
        """
        try:
            data = json.loads(message.strip())
            # Basic structure check:
            if not isinstance(data, dict):
                raise ValueError("Top-level JSON must be an object.")

            # Ensure the fields we care about exist or are set:
            parsed = {
                "thinking": data.get("thinking", ""),
                "analysis": data.get("analysis", ""),
                "tool_calls": data.get("tool_calls", []),
                "answer": data.get("answer", "")
            }

            # Validate "tool_calls" shape:
            if not isinstance(parsed["tool_calls"], list):
                logger.warning("tool_calls is not a list; forcing it to be an empty list.")
                parsed["tool_calls"] = []

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from model response: {e}")
        except Exception as ex:
            logger.error(f"Unexpected error parsing JSON response: {ex}")

        # Fallback if parsing fails:
        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message  # fallback to raw message
        }
