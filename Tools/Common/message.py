from typing import Dict, Any

TOOL_NAME = "message"
TOOL_DESCRIPTION = "Display a message to the user from the agent."


EXAMPLES = {
    "text": "I'm thinking about how to solve this problem..."
}

FORMATTER = "agent_message"

async def tool_message(
    text: str,
    **kwargs
) -> Dict[str, Any]:

    if not text:
        return {
            "output": "",
            "error": "Missing required parameter: text",
            "success": False,
            "exit_code": 1
        }

    return {
        "output": text,
        "error": "",
        "success": True,
        "exit_code": 0,
        "message": text
    }
