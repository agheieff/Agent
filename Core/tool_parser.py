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

        while True:
            tool_match = re.search(r'@tool\s+(?P<name>\w+)(?P<body>.*?)@end', 
                                 self.buffer, re.DOTALL)

            if not tool_match:
                break

            tool_name = tool_match.group('name')
            tool_body = tool_match.group('body').strip()

            args = self._parse_tool_args(tool_body)

            tool_call = {
                'tool': tool_name,
                'args': args
            }

            self.buffer = self.buffer[tool_match.end():]

        output_text = self.buffer
        self.buffer = ""

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
