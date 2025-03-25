import os
import json
from dataclasses import dataclass
from typing import Dict, List, Optional
import inspect

from Tools.Core.registry import ToolRegistry
from Tools.base import Tool, Argument
from Tools.error_codes import ErrorCodes

@dataclass
class ToolInfo:
    name: str
    description: str
    args: List[Dict[str, str]]
    examples: List[str]

class PromptGenerator:
    def __init__(self):
        self.sections = []
    
    def add_section(self, title: str, content: str):
        self.sections.append((title, content))
        return self
    
    def generate(self) -> str:
        return "\n\n".join(
            f"# {title.upper()}\n{content}"
            for title, content in self.sections
        )

def get_tool_info(tool_instance: Tool) -> ToolInfo:
    """Extracts metadata from a Tool instance."""
    arg_list = []
    if hasattr(tool_instance, "args"):
        for arg in tool_instance.args:
            arg_list.append({
                "name": arg.name,
                "type": arg.arg_type.name,
                "description": arg.description
            })
    examples = getattr(tool_instance, "examples", [])
    return ToolInfo(
        name=tool_instance.name,
        description=tool_instance.description,
        args=arg_list,
        examples=examples
    )

def discover_tools() -> List[Tool]:
    """
    Discover all available tools by leveraging the ToolRegistry.
    Returns a list of Tool instances.
    """
    registry = ToolRegistry()
    # Trigger discovery so that the registry is populated
    registry.discover_tools()
    # Sort the tools alphabetically by name for consistency
    return sorted(list(registry.get_all().values()), key=lambda t: t.name)

def generate_tools_overview() -> str:
    """
    Generate an overview of available tools including the file structure
    of the Tools directory, tool names, and their short descriptions.
    """
    # Determine the path to the Tools directory (assuming this file is in Prompts/)
    tools_dir = os.path.join(os.path.dirname(__file__), "..", "Tools")
    
    tree_lines = []
    for root, dirs, files in os.walk(tools_dir):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        files = [f for f in files if not f.startswith('.') and not f.startswith('__')]
        level = root.replace(tools_dir, "").count(os.sep)
        indent = "    " * level
        tree_lines.append(f"{indent}{os.path.basename(root)}/")
        sub_indent = "    " * (level + 1)
        for f in files:
            tree_lines.append(f"{sub_indent}{f}")
    file_structure = "\n".join(tree_lines)
    
    # Get a simple overview of tools from the registry
    tools = discover_tools()
    tool_overview_lines = ["Available Tools:"]
    for tool in tools:
        tool_overview_lines.append(f"- {tool.name}: {tool.description}")
    
    overview = (
        "File Structure of Tools Directory:\n"
        f"{file_structure}\n\n"
        + "\n".join(tool_overview_lines)
    )
    return overview

def generate_system_prompt(provider: str) -> str:
    """
    Generates complete system prompt with dynamic tool documentation.
    """
    builder = PromptGenerator()
    
    # Core Agent Role
    builder.add_section("Role", 
        "You are an autonomous AI assistant with tool usage capabilities. "
        "Your purpose is to assist users by executing tasks using available tools."
    )
    
    # Tool Usage Instructions
    builder.add_section("Tool Usage",
        "Use tools by specifying @tool followed by the tool name and arguments.\n"
        "Example: @tool read_file path='file.txt' lines=10\n"
        "End the tool call with @end.\n\n"
        "You can embed multiple lines in the tool call body.\n"
        "For instance:\n"
        "@tool edit_file\nfilename: 'notes.txt'\nreplacements: '{\"Hello\":\"World\"}'\n@end"
    )
    
    # File Path Handling
    builder.add_section("File Paths",
        "When working with files:\n"
        "- Use absolute paths (/path/to/file) or relative paths (./file.txt)\n"
        "- ~ expands to user home directory\n"
        "- Paths are case-sensitive"
    )
    
    # Provider-specific formatting note (if applicable)
    if provider == "anthropic":
        builder.add_section("Formatting",
            "For Anthropic, please note that special XML-like tags might be used, "
            "but you should still prefer the @tool ... @end style in your responses."
        )
    
    # Detailed Tools Documentation Section
    tools_section = ["## Available Tools"]
    for tool_instance in discover_tools():
        info = get_tool_info(tool_instance)
        tools_section.append(f"### {info.name}\n{info.description}")
        if info.args:
            tools_section.append("**Arguments:**")
            for arg in info.args:
                tools_section.append(f"- {arg['name']}: {arg['description']}")
        if info.examples:
            tools_section.append("**Examples:**")
            for ex in info.examples:
                tools_section.append(f"  {ex}")
    
    builder.add_section("Tools", "\n".join(tools_section))
    
    # Add the tools overview (file structure and simple list of tool names)
    tools_overview = generate_tools_overview()
    builder.add_section("Tool Overview", tools_overview)
    
    return builder.generate()

# For testing purposes you could uncomment the following lines to print the system prompt:
# if __name__ == "__main__":
#     print(generate_system_prompt("anthropic"))
