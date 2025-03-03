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
    """
    Format help information for a tool in a consistent way.
    
    Args:
        name: Tool name
        description: Tool description
        usage: Usage instructions
        examples: List of (example, description) tuples
        notes: Additional notes to include
        
    Returns:
        Help information as a dictionary with standard keys
    """
    # Build help text
    help_text = f"{description}\n\n{usage}\n"
    
    # Add notes if provided
    if notes:
        help_text += f"\nNotes:\n{notes}\n"
    
    # Add examples if provided
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
    """
    Extract help information from a tool module's metadata.
    
    Args:
        module: The tool module
        
    Returns:
        Help information as a dictionary with standard keys
    """
    name = getattr(module, "TOOL_NAME", "unknown")
    description = getattr(module, "TOOL_DESCRIPTION", "No description available")
    usage = getattr(module, "TOOL_HELP", "No usage information available")
    examples = getattr(module, "TOOL_EXAMPLES", [])
    notes = getattr(module, "TOOL_NOTES", None)
    
    return format_tool_help(name, description, usage, examples, notes)

def add_help_parameter_to_tool(func):
    """
    Decorator that adds standard help parameter handling to a tool function.
    
    Example:
    ```python
    @add_help_parameter_to_tool
    async def tool_sample(message: str = None, **kwargs) -> Dict[str, Any]:
        # Tool implementation
        # No need to handle help parameter - it's handled by the decorator
        ...
    ```
    
    Args:
        func: Tool function to decorate
        
    Returns:
        Decorated function
    """
    import functools
    import inspect
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Check for help parameter
        if kwargs.get("help"):
            # Get module from function
            module = inspect.getmodule(func)
            
            # Return help information
            return get_help_from_module(module)
        
        # Otherwise, call the original function
        return await func(*args, **kwargs)
    
    return wrapper
