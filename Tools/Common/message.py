from typing import Dict, Any

TOOL_NAME = "message"
TOOL_DESCRIPTION = "Display a message to the user from the agent."

# Example values for parameters - used for generating examples
EXAMPLES = {
    "text": "I'm thinking about how to solve this problem..."
}

FORMATTER = "agent_message"

async def tool_message(
    text: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Send a message from the agent to the user.
    
    This allows the agent to communicate with the user outside the standard
    LLM response flow, which is useful when only returning structured tool outputs.
    
    Args:
        text: The message text to display to the user
        
    Returns:
        Dictionary with status information
    """
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