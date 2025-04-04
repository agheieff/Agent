import re
from typing import Dict, Any
from Tools.base import ToolResult

def parse_tool_call(text: str) -> Dict[str, Any]:
    tool_pattern = r'@tool\s+(?P<name>\w+)(?P<body>.*?)@end'
    match = re.search(tool_pattern, text, re.DOTALL)
    if not match:
        raise ValueError("Invalid tool call format")

    args = {}
    current_key = None
    current_value = []

    for line in match.group('body').strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        if ': ' in line:
            if current_key and current_value:
                args[current_key] = '\n'.join(current_value).strip()
                current_value = []
            key, val = line.split(': ', 1)
            current_key = key.strip()
            val = val.strip()
            if val == '<<<':
                continue
            args[current_key] = val
            current_key = None
        elif line == '>>>':
            if current_key:
                args[current_key] = '\n'.join(current_value).strip()
                current_key = None
                current_value = []
        elif current_key:
            current_value.append(line)

    if current_key and current_value:
        args[current_key] = '\n'.join(current_value).strip()

    return {'tool': match.group('name'), 'args': args}

def format_result(name: str, exit_code: int, output: str) -> str:
    return f"@result {name}\nexit_code: {exit_code}\noutput: {output}\n@end"

class Executor:
    def __init__(self):
        self.tools = {}

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def execute(self, tool_call: str) -> str:
        try:
            parsed = parse_tool_call(tool_call)
            tool = self.tools.get(parsed['tool'])

            if not tool:
                return format_result(parsed['tool'], 1, "Tool not found")

            result = tool.execute(**parsed['args'])

            if isinstance(result, tuple) and len(result) == 2:
                exit_code, message = result
                return format_result(parsed['tool'], exit_code, str(message))
            elif isinstance(result, ToolResult):
                return format_result(
                    parsed['tool'], 
                    0 if result.success else 1,
                    result.message if result.message else str(result.data)
                )
            else:
                return format_result(parsed['tool'], 0, str(result))

        except Exception as e:
            return format_result("unknown", 1, str(e))
