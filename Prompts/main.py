
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
    # Convert each Argument into a dictionary
    arg_list = []
    if hasattr(tool_instance, "args"):
        for arg in tool_instance.args:
            arg_list.append({
                "name": arg.name,
                "type": arg.arg_type.name,
                "description": arg.description
            })
    # If the tool has any usage examples, capture them (or skip if not present).
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
    # Trigger actual discovery so registry is populated
    registry.discover_tools()
    # Return the list of tool instances
    return list(registry.get_all().values())

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
    
    # Add provider-specific formatting note (optional)
    if provider == "anthropic":
        builder.add_section("Formatting",
            "For Anthropic, please note that special XML-like tags might be used, "
            "but you should still prefer the @tool ... @end style in your responses."
        )
    
    # Document all discovered tools
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
    
    return builder.generate()
