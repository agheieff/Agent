"""
Utilities for generating help information for tools.
"""

from typing import Dict, Any, List, Tuple, Optional

def format_tool_help(
    name: str,
    description: str,
    usage: str,
    examples: List[Tuple[str, str]] = None,
    notes: str = None
) -> Dict[str, Any]:

    help_text = f"{description}\n\n{usage}\n"


    if notes:
        help_text += f"\nNotes:\n{notes}\n"


    if examples:
        example_text = "\nExamples:\n" + "\n".join(
            [f"  {example[0]}\n    {example[1]}" for example in examples]
        )
        help_text += example_text

    return {
        "output": help_text,
        "error": "",
        "success": True,
        "exit_code": 0,
        "is_help": True
    }

def get_help_from_module(module) -> Dict[str, Any]:
    name = getattr(module, "TOOL_NAME", "unknown")
    description = getattr(module, "TOOL_DESCRIPTION", "No description available")
    usage = getattr(module, "TOOL_HELP", "No usage information available")
    examples = getattr(module, "TOOL_EXAMPLES", [])
    notes = getattr(module, "TOOL_NOTES", None)

    return format_tool_help(name, description, usage, examples, notes)

def add_help_parameter_to_tool(func):
    import functools
    import inspect

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):

        if kwargs.get("help"):

            module = inspect.getmodule(func)


            return get_help_from_module(module)


        return await func(*args, **kwargs)

    return wrapper
