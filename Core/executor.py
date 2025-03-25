import re
from typing import Dict, Any

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
