from typing import Dict, Any

TOOL_NAME = "finish"
TOOL_DESCRIPTION = "End the conversation with the agent."

# Example values for parameters - used for generating examples
EXAMPLES = {}

FORMATTER = "conversation_end"

async def tool_finish(
    **kwargs
) -> Dict[str, Any]:
    """
    End the conversation with the agent.
    
    This tool signals that the agent has completed its task and wants to
    terminate the conversation. It allows for a clean exit point.
    
    Args:
        None
        
    Returns:
        Dictionary with status information
    """
    return {
        "output": "Conversation ended by agent.",
        "error": "",
        "success": True,
        "exit_code": 0,
        "conversation_ended": True
    }