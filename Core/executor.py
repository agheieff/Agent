import re
from typing import Dict, Any
from Tools.base import ToolResult
from Tools.error_codes import ErrorCodes

def parse_tool_call(text: str) -> Dict[str, Any]:
    tool_pattern = r'@tool\s+(?P<name>\w+)(?P<body>.*?)@end'
    match = re.search(tool_pattern, text, re.DOTALL)
    if not match:
        raise ValueError("Invalid tool call format")
    
    body = match.group('body').strip()
    args = {}
    lines = body.split('\n')

    current_key = None
    current_value_lines = []
    in_multiline = False

    for line in lines:
        line = line.rstrip()
        if not in_multiline:
            # Attempt to parse "key: value" or "key: <<<"
            if ': ' in line:
                key, val = line.split(': ', 1)
                key = key.strip()
                val = val.strip()
                if val == '<<<':
                    # Start multiline
                    current_key = key
                    in_multiline = True
                    current_value_lines = []
                else:
                    args[key] = val
        else:
            # We are inside a multi-line block
            if line == '>>>':
                # End multiline
                args[current_key] = "\n".join(current_value_lines)
                in_multiline = False
                current_key = None
                current_value_lines = []
            else:
                current_value_lines.append(line)

    return {
        'tool': match.group('name'),
        'args': args
    }

def format_tool_result(name: str, success: bool, output: str) -> str:
    """Format tool result for LLM consumption"""
    status = "success" if success else "error"
    return f"@result {name}\nstatus: {status}\noutput: {output}\n@end"

class Executor:
    def __init__(self):
        self.tools = {}  # name -> Tool instance

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def execute(self, tool_call_text: str) -> str:
        try:
            parsed = parse_tool_call(tool_call_text)
            tool_name = parsed['tool']
            args = parsed['args']
            
            if tool_name not in self.tools:
                return format_tool_result(tool_name, False, f"Tool '{tool_name}' not found")
            
            tool = self.tools[tool_name]
            result = tool.execute(**args)
            
            if isinstance(result, ToolResult):
                success = result.ok
                output = result.message or str(result.data)
            else:
                success = True
                output = str(result)
                
            return format_tool_result(tool_name, success, output if output else "")
            
        except Exception as e:
            # We might not know the tool name if parse_tool_call failed
            return format_tool_result("unknown_tool", False, str(e))
