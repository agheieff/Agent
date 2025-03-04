"""
Parser for extracting JSON tool calls from agent messages.
"""

import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ToolParser:
    @staticmethod
    def extract_tool_calls(message: str) -> List[Tuple[str, Dict[str, Any], bool]]:
\
\
\
\
\
\
\
\

        tool_calls = []


        tool_pattern = r'#tool\s*(\{[^#]*?\})'
        raw_matches = re.finditer(tool_pattern, message, re.MULTILINE | re.DOTALL)

        for match in raw_matches:
            try:
                json_str = match.group(1).strip()

                tool_data = json.loads(json_str)


                tool_name = tool_data.get("name", "")
                params = tool_data.get("params", {})
                is_help = tool_data.get("help", False)

                if tool_name:
                    tool_calls.append((tool_name, params, is_help))
                else:
                    logger.warning("Tool call missing 'name' field")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call JSON: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing tool call: {e}")
                continue


        thinking_pattern = r'#thinking\s*(\{[^#]*?\})'
        thinking_matches = re.finditer(thinking_pattern, message, re.MULTILINE | re.DOTALL)

        for match in thinking_matches:
            try:
                json_str = match.group(1).strip()

                json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse thinking JSON: {e}")

        return tool_calls

    @staticmethod
    def extract_thinking(message: str) -> List[Dict[str, Any]]:
\
\
\
\
\
\
\
\

        thinking_sections = []

        thinking_pattern = r'#thinking\s*(\{[^#]*?\})'
        matches = re.finditer(thinking_pattern, message, re.MULTILINE | re.DOTALL)

        for match in matches:
            try:
                json_str = match.group(1).strip()
                thinking_data = json.loads(json_str)
                thinking_sections.append(thinking_data)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse thinking JSON: {e}")
            except Exception as e:
                logger.error(f"Unexpected error parsing thinking section: {e}")

        return thinking_sections

    @staticmethod
    def is_exit_request(text: str) -> bool:
\
\

        exit_patterns = [r'#tool\s*{"name":\s*"exit"}', r'#tool\s*{"name":\s*"quit"}']
        for pattern in exit_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
