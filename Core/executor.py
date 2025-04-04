import re
from typing import Dict, Any
from Tools.base import ToolResult
from Tools.Core.registry import ToolRegistry
from Tools.error_codes import ErrorCodes

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
        registry = ToolRegistry()
        self.tools: Dict[str, Any] = registry.get_all()

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def execute(self, tool_call: str) -> str:
        try:
            try:
                parsed = parse_tool_call(tool_call)
            except ValueError as e:
                if "@tool" in tool_call and "@end" not in tool_call:
                    try:
                        parsed = parse_tool_call(tool_call + "\n@end")
                    except ValueError:
                        return format_result("error", ErrorCodes.INVALID_ARGUMENTS, f"Invalid tool call - {str(e)}")
                else:
                    return format_result("error", ErrorCodes.INVALID_ARGUMENTS, f"Invalid tool call - {str(e)}")

            tool = self.tools.get(parsed['tool'])
            if not tool:
                return format_result(parsed['tool'], ErrorCodes.TOOL_NOT_FOUND, f"Tool '{parsed['tool']}' not found in executor registry")
            result: ToolResult = tool.execute(**parsed['args'])
            return format_result(parsed['tool'], result.code, result.message)

        except Exception as e:
            return format_result("error", ErrorCodes.UNKNOWN_ERROR, f"Error executing tool: {str(e)}")
