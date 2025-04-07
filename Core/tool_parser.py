from typing import Tuple, Optional, Dict, Any
from Core.executor import parse_tool_call
import re

class ToolCallParser:
    def __init__(self):
        self.buffer = ""
        self.parsing_tool = False

    def feed(self, text: str) -> Tuple[str, Optional[Dict]]:
        output_text = ""
        tool_data = None

        if not self.parsing_tool:
            combined = self.buffer + text
            tool_start_index = combined.find("@tool")

            if tool_start_index != -1:
                output_text = combined[:tool_start_index]
                self.buffer = combined[tool_start_index:]
                self.parsing_tool = True
            else:
                output_text = text
                self.buffer += text
        else:
             self.buffer += text
             tool_end_index = self.buffer.find("@end")
             if tool_end_index != -1:
                 tool_section = self.buffer[:tool_end_index + 4]
                 self.buffer = self.buffer[tool_end_index + 4:]
                 self.parsing_tool = False

                 try:
                     tool_data = parse_tool_call(tool_section)
                 except ValueError as e:
                     print(f"Warning: Invalid tool format detected and skipped: {e}")
        return output_text, tool_data
