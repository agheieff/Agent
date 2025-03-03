import logging
import re
from typing import Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tool_parser")

class ToolParser:
    @staticmethod
    def parse_tool(tool_text: str) -> Tuple[str, Dict[str, str]]:
        lines = tool_text.strip().split('\n')

        if not lines:
            raise ValueError("Empty tool text")

        tool_name = lines[0].strip()
        if tool_name.startswith('/'):
            tool_name = tool_name[1:]

        params = {}
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                params[key.strip()] = value.strip()
            else:
                logger.warning(f"Ignoring malformed parameter line: {line}")

        return tool_name, params

    @staticmethod
    def format_result(tool_name: str, success: bool, output: Optional[str] = None, 
                      error: Optional[str] = None) -> Dict:
        result = {
            "tool": tool_name,
            "success": success
        }

        if success and output is not None:
            result["output"] = output
        elif not success and error is not None:
            result["error"] = error

        return result
