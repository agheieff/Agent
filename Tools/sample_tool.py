"""
Sample tool to demonstrate the updated metadata pattern.
"""

import os
import logging
from typing import Dict, Any, Optional

# Tool metadata
TOOL_NAME = "sample"
TOOL_DESCRIPTION = "A sample tool to demonstrate the metadata pattern"
TOOL_HELP = """
A sample tool that demonstrates the metadata pattern.

Usage:
  /sample message="Hello World"
  /sample <message>

Arguments:
  message       The message to echo (required)
  repeat        Number of times to repeat the message (default: 1)

Examples:
  /sample Hello World
  /sample message="Hello World" repeat=3
"""

TOOL_EXAMPLES = [
    ("/sample Hello World", "Display 'Hello World'"),
    ("/sample message=\"Hello World\" repeat=3", "Display 'Hello World' three times")
]

logger = logging.getLogger(__name__)

def _get_help() -> Dict[str, Any]:
    """Return help information for this tool."""
    example_text = "\nExamples:\n" + "\n".join(
        [f"  {example[0]}\n    {example[1]}" for example in TOOL_EXAMPLES]
    )

    return {
        "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{example_text}",
        "error": "",
        "success": True,
        "exit_code": 0
    }

async def tool_sample(message: str = None, repeat: int = 1, help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    """
    A sample tool that demonstrates the metadata pattern.

    Args:
        message: The message to echo
        repeat: Number of times to repeat the message
        help: Whether to return help information
        value: Alternative way to specify message as positional parameter
        **kwargs: Additional parameters

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    # Return help information if requested
    if help:
        return _get_help()

    # Handle positional parameter
    if message is None and value is not None:
        message = value

    # Check for missing required parameters
    if message is None:
        # Look for positional parameters in kwargs
        for k in kwargs:
            if k.isdigit():
                message = kwargs[k]
                break

    if message is None:
        return {
            "output": "",
            "error": "Missing required parameter: message",
            "success": False,
            "exit_code": 1
        }

    try:
        # Validate repeat parameter
        try:
            repeat = int(repeat)
            if repeat <= 0:
                return {
                    "output": "",
                    "error": "Parameter 'repeat' must be a positive integer",
                    "success": False,
                    "exit_code": 1
                }
        except (ValueError, TypeError):
            return {
                "output": "",
                "error": "Parameter 'repeat' must be a valid integer",
                "success": False,
                "exit_code": 1
            }

        # Generate the output
        output = "\n".join([message] * repeat)

        return {
            "output": output,
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        logger.error(f"Error in sample tool: {str(e)}")
        return {
            "output": "",
            "error": f"Error executing command: {str(e)}",
            "success": False,
            "exit_code": 1
        }
