import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

try:
    from MCP.registry import operation_registry
    from MCP.Operations.base import Operation
except ImportError:
    class OperationRegistry:
        def get_all(self): return {}
    class Operation:
        name: str = "unavailable"
        description: str = "MCP components not found"
        arguments: List = []
    operation_registry = OperationRegistry()

logger = logging.getLogger(__name__)

@dataclass
class OperationInfo:
    """Information about an MCP Operation for prompt generation."""
    name: str
    description: str
    args: List[Dict[str, Any]]

def get_operation_info(op_instance: Operation) -> OperationInfo:
    """Extract metadata from an Operation instance."""
    arg_list = []
    for arg_def in getattr(op_instance, "arguments", []):
        arg_data = {
            "name": arg_def.name,
            "type": arg_def.type,
            "required": arg_def.required,
            "description": arg_def.description,
        }
        if getattr(arg_def, "default", None) is not None:
            arg_data["default"] = arg_def.default
        arg_list.append(arg_data)
    
    return OperationInfo(
        name=op_instance.name,
        description=op_instance.description,
        args=arg_list,
    )

def generate_operations_documentation() -> str:
    """Generate Markdown documentation for MCP operations."""
    ops_dict = operation_registry.get_all()
    operations = sorted(list(ops_dict.values()), key=lambda op: op.name)
    
    if not operations:
        return "No MCP operations discovered."
    
    docs = ["## Available MCP Operations"]
    
    for op in operations:
        info = get_operation_info(op)
        docs.append(f"### `{info.name}`\n{info.description}")
        
        if info.args:
            docs.append("**Arguments:**")
            for arg in info.args:
                req_status = "Required" if arg.get('required', True) else f"Optional (default: `{arg.get('default', 'None')}`)"
                docs.append(f"- `{arg['name']}` ({arg['type']}): {arg['description']} [{req_status}]")
        docs.append("")
    
    return "\n".join(docs)

def generate_system_prompt(provider: Optional[str] = None) -> str:
    """Generate a complete system prompt."""
    sections = []
    
    # Role section
    sections.append("# ROLE\nYou are an autonomous AI assistant.")
    
    # Goal section
    sections.append("# GOAL\nYour primary goal is to assist the user by understanding their requests and executing tasks accurately using the available MCP Operations.")
    
    # Usage instructions
    sections.append(
        "# MCP OPERATION USAGE\n"
        "When you need to use an operation, respond with a JSON block:\n"
        "```json\n"
        "{\n"
        '  "mcp_operation": {\n'
        '    "operation_name": "name_of_operation",\n'
        '    "arguments": {\n'
        '      "arg1_name": "value1",\n'
        '      "arg2_name": value2\n'
        '    }\n'
        '  }\n'
        '}\n'
        "```"
    )
    
    # Add provider-specific notes if needed
    if provider == "anthropic":
        sections.append(
            "# PROVIDER NOTES (ANTHROPIC)\n"
            "Structure your thoughts clearly in your response to the user."
        )
    
    # Add operations documentation
    sections.append(generate_operations_documentation())
    
    # Response format
    sections.append(
        "# RESPONSE FORMAT\n"
        "If a user request requires an operation, respond with the JSON operation call. "
        "Otherwise, respond in a clear, helpful manner."
    )
    
    return "\n\n".join(sections)

if __name__ == "__main__":
    prompt_text = generate_system_prompt("anthropic")
    print("--- Generated System Prompt ---")
    print(prompt_text)
    print("\n--- End Prompt ---")