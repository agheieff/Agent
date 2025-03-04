import logging
from typing import Dict, Any, Optional

TOOL_NAME = "pause"
TOOL_DESCRIPTION = "Pause the conversation and wait for user input."

# Example values for parameters - used for generating examples
EXAMPLES = {
    "message": "Please provide your API key:"
}

FORMATTER = "user_interaction"

logger = logging.getLogger(__name__)

async def tool_pause(
    message: str,
    output_manager=None,
    **kwargs
) -> Dict[str, Any]:
    """
    Pause the conversation and wait for user input.
    
    Args:
        message: Message to display to the user
        output_manager: Output manager instance for direct user interaction
        
    Returns:
        Dictionary with the user's response
    """
    if not message:
        return {
            "output": "",
            "error": "Missing required parameter: message",
            "success": False,
            "exit_code": 1
        }
    
    if output_manager is None:
        return {
            "output": "",
            "error": "No output manager provided to pause tool",
            "success": False,
            "exit_code": 1
        }
    
    try:
        # Display the message to the user
        user_input = await output_manager.get_user_input(f"{message} ")
        
        return {
            "output": f"Received user input: {user_input}",
            "error": "",
            "success": True,
            "exit_code": 0,
            "user_input": user_input,
            "prompt_message": message
        }
    except Exception as e:
        logger.exception("Error in pause tool")
        return {
            "output": "",
            "error": f"Error getting user input: {str(e)}",
            "success": False,
            "exit_code": 1
        }