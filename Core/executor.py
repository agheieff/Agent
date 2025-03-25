import re
from typing import Dict, Any
from Tools.base import ToolResult
from Tools.error_codes import ErrorCodes

def parse_tool_call(text: str) -> Dict[str, Any]:
    """Parse tool call with multi-line support"""
    tool_pattern = r'@tool\s+(?P<name>\w+)\s+(?P<args>.*?)@end'
    match = re.search(tool_pattern, text, re.DOTALL)
    if not match:
        raise ValueError("Invalid tool call format")
    
    args = {}
    for line in match.group('args').strip().split('\n'):
        if ': ' in line:
            key, value = line.split(': ', 1)
            args[key.strip()] = value.strip()
    
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
                
            return format_tool_result(tool_name, success, output)
            
        except Exception as e:
            return format_tool_result(tool_name, False, str(e))
