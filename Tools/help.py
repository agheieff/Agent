"""
Tool for getting help on available tools.
"""

import os
import inspect
import importlib
from pathlib import Path
from typing import Dict, Any, List, Optional

# Tool metadata
TOOL_NAME = "help"
TOOL_DESCRIPTION = "Get help on available tools or a specific tool"
TOOL_HELP = """
Get help on available tools or a specific tool.

Usage:
  /help
  /help <tool_name>
  /help tool=<tool_name>

Arguments:
  tool           Name of the tool to get help for (optional)
                 If not provided, shows a list of all available tools

Examples:
  /help
  /help view
  /help tool=bash
"""

TOOL_EXAMPLES = [
    ("/help", "List all available tools"),
    ("/help view", "Get help on the 'view' tool"),
    ("/help tool=edit", "Get help on the 'edit' tool")
]

def _get_tools_list() -> Dict[str, Dict[str, str]]:
    """Get a list of all available tools with their metadata."""
    tools = {}
    tools_dir = Path(__file__).parent

    for directory in [d for d in tools_dir.iterdir() if d.is_dir() and not d.name.startswith('__')]:
        for py_file in directory.glob("**/*.py"):
            if py_file.name == "__init__.py":
                continue

            # Extract tool name and metadata
            module_name = f"Tools.{directory.name}.{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Look for tool function
                for name, obj in inspect.getmembers(module):
                    if name.startswith('tool_'):
                        tool_name = name[5:]  # Remove 'tool_' prefix

                        # Get metadata if available
                        description = getattr(module, 'TOOL_DESCRIPTION', '')
                        if not description and obj.__doc__:
                            description = obj.__doc__.strip().split('\n')[0]

                        tools[tool_name] = {
                            "name": tool_name,
                            "description": description,
                            "path": f"{directory.name}/{py_file.name}",
                        }

            except (ImportError, AttributeError):
                pass

    return tools

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

def tool_help(tool: str = None, help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    """
    Get help on available tools or a specific tool.

    Args:
        tool: Name of the tool to get help for (optional)
        help: Whether to return help information for the help tool itself
        value: Alternative way to specify tool as positional parameter
        **kwargs: Additional parameters

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    # Return help information about the help tool if requested
    if help:
        return _get_help()

    # Handle positional parameter
    if tool is None and value is not None:
        tool = value

    # Check for missing tool in named or positional parameters
    if tool is None:
        # Look for positional parameters in kwargs
        for k in kwargs:
            if k.isdigit():
                tool = kwargs[k]
                break

    # If no specific tool is requested, list all available tools
    if tool is None:
        tools = _get_tools_list()

        if not tools:
            return {
                "output": "No tools available.",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        # Format the list of tools
        output = "Available tools:\n\n"

        # Group tools by category
        categories = {}
        for name, info in tools.items():
            category = info["path"].split('/')[0]
            if category not in categories:
                categories[category] = []
            categories[category].append((name, info["description"]))

        # Sort categories and tools
        for category, tool_list in sorted(categories.items()):
            output += f"## {category.capitalize()} Tools\n\n"
            for name, description in sorted(tool_list):
                output += f"- /{name}: {description}\n"
            output += "\n"

        output += "Use /help <tool_name> to get more information about a specific tool."

        return {
            "output": output,
            "error": "",
            "success": True,
            "exit_code": 0
        }
    else:
        # Get help for the specified tool
        try:
            # First, ensure this is a valid tool
            tools = _get_tools_list()
            if tool not in tools:
                return {
                    "output": "",
                    "error": f"Unknown tool: {tool}",
                    "success": False,
                    "exit_code": 1
                }

            # Execute the tool with the help parameter
            # We need to dynamically import and call the tool
            path_parts = tools[tool]["path"].split('/')
            module_name = f"Tools.{path_parts[0]}.{path_parts[1].replace('.py', '')}"
            module = importlib.import_module(module_name)

            tool_func = getattr(module, f"tool_{tool}")
            result = tool_func(help=True)

            # If the result is a coroutine, we need to run it
            if inspect.iscoroutine(result):
                import asyncio
                result = asyncio.run(result)

            return result

        except Exception as e:
            return {
                "output": "",
                "error": f"Error getting help for tool '{tool}': {str(e)}",
                "success": False,
                "exit_code": 1
            }