import os
import json
from dataclasses import dataclass
from typing import Dict, List, Optional
import inspect

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

def get_tool_info(tool_class) -> ToolInfo:
    """Extracts tool metadata from a Tool class"""
    return ToolInfo(
        name=tool_class.name,
        description=tool_class.description,
        args=[{"name": arg.name, "type": str(arg.arg_type), "description": arg.description}
              for arg in tool_class.arguments],
        examples=getattr(tool_class, "examples", [])
    )

def generate_system_prompt(provider: str) -> str:
    """Generates complete system prompt with dynamic tool documentation"""
    builder = PromptGenerator()
    
    # Core Agent Role
    builder.add_section("Role", 
        "You are an autonomous AI assistant with tool usage capabilities. "
        "Your purpose is to assist users by executing tasks using available tools.")
    
    # Tool Usage Instructions
    builder.add_section("Tool Usage",
        "Use tools by specifying @tool followed by the tool name and arguments.\n"
        "Example: @tool read_file path='file.txt' lines=10")
    
    # File Path Handling
    builder.add_section("File Paths",
        "When working with files:\n"
        "- Use absolute paths (/path/to/file) or relative paths (./file.txt)\n"
        "- ~ expands to user home directory\n"
        "- Paths are case-sensitive")
    
    # Add provider-specific formatting
    if provider == "anthropic":
        builder.add_section("Formatting",
            "Use XML tags for tool calls: <tool_name>param=value</tool_name>")
    
    # Tool Documentation (dynamically generated)
    tools_section = ["## Available Tools"]
    for tool in discover_tools():
        info = get_tool_info(tool)
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

def discover_tools():
    """Discover all available tools by inspecting the Tools directory"""
    # Implementation would scan Tools/ directory and import tool classes
    # Return list of tool classes
    return []
