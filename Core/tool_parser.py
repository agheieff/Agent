from typing import Tuple, Optional, Dict, Any
import re

class ToolCallParser:
    def __init__(self):
        self.buffer = ""
        self.partial_tool = None

    def feed(self, text: str) -> Tuple[str, Optional[Dict]]:
        self.buffer += text
        output_text = ""
        tool_call = None

        tool_start = self.buffer.find("@tool")
        if tool_start >= 0:
            tool_end = self.buffer.find("@end", tool_start)
            if tool_end >= 0:
                tool_section = self.buffer[tool_start:tool_end+4]
                output_text = self.buffer[:tool_start]
                self.buffer = self.buffer[tool_end+4:]

                try:
                    tool_call = parse_tool_call(tool_section)
                except ValueError:
                    output_text += tool_section

        return output_text, tool_call

    def _parse_tool_args(self, body: str) -> Dict[str, str]:
        args = {}
        current_key = None
        current_value = []

        for line in body.split('\n'):
            line = line.strip()
            if ': ' in line:
                if current_key:
                    args[current_key] = '\n'.join(current_value).strip()
                key, val = line.split(': ', 1)
                current_key = key.strip()
                current_value = [val.strip()]
            elif current_key:
                current_value.append(line)

        if current_key:
            args[current_key] = '\n'.join(current_value).strip()

        return args
