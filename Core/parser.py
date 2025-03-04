import json
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ToolParser:
\
\
\
\
\
\
\
\
\
\
\


    @staticmethod
    def parse_message(message: str) -> Dict[str, Any]:
\
\
\
\

        try:
            data = json.loads(message.strip())

            if not isinstance(data, dict):
                raise ValueError("Top-level JSON must be an object.")


            parsed = {
                "thinking": data.get("thinking", ""),
                "analysis": data.get("analysis", ""),
                "tool_calls": data.get("tool_calls", []),
                "answer": data.get("answer", "")
            }


            if not isinstance(parsed["tool_calls"], list):
                logger.warning("tool_calls is not a list; forcing it to be an empty list.")
                parsed["tool_calls"] = []

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from model response: {e}")
        except Exception as ex:
            logger.error(f"Unexpected error parsing JSON response: {ex}")


        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message
        }
