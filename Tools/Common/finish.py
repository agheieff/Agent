from typing import Dict, Any

TOOL_NAME = "finish"
TOOL_DESCRIPTION = "End the conversation with the agent."
EXAMPLES = {}
FORMATTER = "conversation_end"

async def tool_finish(**kwargs) -> Dict[str, Any]:
    return {
        "output": "Conversation ended by agent.",
        "error": "",
        "exit_code": 0,
        "conversation_ended": True
    }

def display_format(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    return "[FINISH] Conversation ended."
