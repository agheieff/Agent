import re
from typing import Dict, Any, Optional, TYPE_CHECKING
import traceback

from Tools.base import ToolResult, Tool
from Tools.Core.registry import ToolRegistry
# Import ConversationEnded to specifically handle it
from Tools.error_codes import ErrorCodes, ConversationEnded

if TYPE_CHECKING:
    from Core.agent_config import AgentConfiguration

# --- parse_tool_call and format_result remain the same ---
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
        if not line: continue
        if ': ' in line:
            if current_key and current_value:
                args[current_key] = '\n'.join(current_value).strip()
            key, val = line.split(': ', 1)
            current_key = key.strip()
            val = val.strip()
            if val == '<<<':
                 current_value = [] # Start multiline
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
    safe_output = str(output).replace('@end', '@_end')
    return f"@result {name}\nexit_code: {exit_code}\noutput: {safe_output}\n@end"


class Executor:
    def __init__(self):
        registry = ToolRegistry()
        self.tools: Dict[str, Tool] = registry.get_all()

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def execute(self, tool_call: str, agent_config: Optional['AgentConfiguration'] = None) -> str:
        tool_name = "error"
        parsed = None # Define parsed outside try for use in except
        try:
            # --- Parsing ---
            try:
                parsed = parse_tool_call(tool_call)
                tool_name = parsed.get('tool', 'unknown_tool')
            except ValueError as e:
                if "@tool" in tool_call and "@end" not in tool_call:
                     try:
                          parsed = parse_tool_call(tool_call + "\n@end")
                          tool_name = parsed.get('tool', 'unknown_tool')
                     except ValueError:
                          return format_result("parse_error", ErrorCodes.INVALID_ARGUMENTS, f"Invalid tool call format - {str(e)}")
                else:
                     return format_result("parse_error", ErrorCodes.INVALID_ARGUMENTS, f"Invalid tool call format - {str(e)}")

            # --- Tool Lookup ---
            tool = self.tools.get(parsed['tool'])
            if not tool:
                return format_result(parsed['tool'], ErrorCodes.TOOL_NOT_FOUND, f"Tool '{parsed['tool']}' not found in registry.")

            # --- Permissions Placeholder ---
            # ...

            # --- Execute the Tool ---
            print(f"DEBUG Executor: Attempting to execute tool '{tool_name}'...") # DEBUG
            result: ToolResult = tool.execute(**parsed['args']) # This call might raise ConversationEnded
            print(f"DEBUG Executor: Tool '{tool_name}' execution finished normally.") # DEBUG (Only if no exception)
            # --- This point is only reached if tool.execute() returns normally ---
            return format_result(parsed['tool'], result.code, result.message)

        # --- Specific Exception Handling FIRST ---
        except ConversationEnded as ce:
            print(f"DEBUG Executor: Caught specific ConversationEnded for tool '{tool_name}'. RE-RAISING.") # DEBUG
            raise ce # Re-raise this specific exception

        # --- Generic Exception Handling LAST ---
        except Exception as e:
            # This block should NOT catch ConversationEnded if the above block works
            print(f"DEBUG Executor: Caught GENERIC Exception for tool '{tool_name}': {type(e).__name__}") # DEBUG
            print(f"ERROR during tool execution ({tool_name}): {type(e).__name__} - {e}")
            traceback.print_exc()
            # Format the generic exception as an error result
            return format_result(tool_name, ErrorCodes.UNKNOWN_ERROR, f"Unexpected error executing tool: {str(e)}")

    # --- Placeholder permission check ---
    # def _check_directory_permissions(...): return True
