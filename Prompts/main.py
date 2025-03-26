import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

# Use relative imports assuming this is run within the project structure
try:
    from MCP.registry import operation_registry
    from MCP.Operations.base import Operation, ArgumentDefinition
    # Removed reference to non-existent Tools package
except ImportError as e:
     logging.error(f"Failed to import MCP components for prompt generation: {e}")
     # Define dummy classes if MCP isn't available, prompts will be basic
     class OperationRegistry:
         def get_all(self): return {}
     class Operation:
         name: str = "unavailable"
         description: str = "MCP components not found"
         arguments: List = []
     class ArgumentDefinition: pass
     operation_registry = OperationRegistry()


logger = logging.getLogger(__name__)

@dataclass
class OperationInfo:
    """Extracted information about an MCP Operation for prompt generation."""
    name: str
    description: str
    args: List[Dict[str, Any]] # Use Any for default value flexibility

class PromptGenerator:
    """Helper class to build structured prompts section by section."""
    def __init__(self):
        self.sections: List[tuple[str, str]] = []

    def add_section(self, title: str, content: str):
        """Adds a named section to the prompt."""
        if content: # Only add sections with content
             self.sections.append((title.strip(), content.strip()))
        return self

    def generate(self) -> str:
        """Combines sections into a single formatted prompt string."""
        return "\n\n".join(
            f"# {title.upper()}\n{content}"
            for title, content in self.sections
            if title and content # Ensure both title and content exist
        ).strip()

def get_operation_info(op_instance: Operation) -> OperationInfo:
    """Extracts metadata from an Operation instance for documentation."""
    arg_list = []
    if hasattr(op_instance, "arguments"):
        for arg_def in op_instance.arguments:
            arg_data = {
                "name": arg_def.name,
                "type": arg_def.type,
                "required": arg_def.required,
                "description": arg_def.description,
            }
            # Only include default if it's explicitly set (not None)
            if arg_def.default is not None:
                arg_data["default"] = arg_def.default
            arg_list.append(arg_data)

    return OperationInfo(
        name=op_instance.name,
        description=op_instance.description,
        args=arg_list,
    )

def discover_operations() -> List[Operation]:
    """Discovers available MCP Operations using the registry."""
    # Ensure registry is populated (discovery happens on first access if needed)
    ops_dict = operation_registry.get_all()
    # Sort alphabetically by name for consistent prompt output
    return sorted(list(ops_dict.values()), key=lambda op: op.name)

def generate_mcp_operations_documentation() -> str:
    """Generates Markdown documentation for available MCP operations."""
    docs_section = ["## Available MCP Operations"]
    operations = discover_operations()

    if not operations:
         return "No MCP operations discovered or MCP components unavailable."

    for op_instance in operations:
        info = get_operation_info(op_instance)
        docs_section.append(f"### `{info.name}`\n{info.description}") # Use backticks for name
        if info.args:
            docs_section.append("**Arguments:**")
            for arg in info.args:
                req_status = "Required" if arg['required'] else f"Optional (default: `{arg.get('default', 'None')}`)"
                docs_section.append(f"- `{arg['name']}` ({arg['type']}): {arg['description']} [{req_status}]")
        docs_section.append("") # Add spacing between operations

    return "\n".join(docs_section)


def generate_system_prompt(provider: Optional[str] = None) -> str:
    """
    Generates a complete system prompt including core role, instructions,
    and dynamically generated documentation for available MCP Operations.

    Args:
        provider: Optional name of the LLM provider (e.g., "anthropic")
                  to include provider-specific notes.
    """
    builder = PromptGenerator()

    # --- Core Agent Role & Goal ---
    builder.add_section("Role",
        "You are an autonomous AI assistant."
    )
    builder.add_section("Goal",
        "Your primary goal is to assist the user by understanding their requests and executing tasks accurately and efficiently. "
        "When appropriate, use the available MCP Operations (listed below) to interact with the environment or perform actions."
    )

    # --- MCP Operation Usage Instructions ---
    # Define the specific syntax expected for tool/operation calls.
    # This might vary based on how you parse the LLM's output.
    # Example using a simple JSON-like block:
    builder.add_section("MCP Operation Usage",
        "When you need to use an operation, respond ONLY with a JSON block formatted like this:\n"
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
        "```\n"
        "Replace `name_of_operation` with the actual operation name and provide the necessary arguments within the `arguments` object. "
        "Ensure the JSON is valid. Do not include any other text, explanation, or conversational filler before or after the JSON block when calling an operation."
    )
    # --- Alternative Usage Instruction Example (using @tool syntax) ---
    # builder.add_section("MCP Operation Usage",
    #     "Use operations by specifying @tool followed by the operation name and arguments (key='value'). End with @end.\n"
    #     "Example: @tool read_file path='/path/to/file.txt' lines=10 @end\n"
    #     "Multiline arguments can be embedded.\n"
    #     "@tool write_file path='notes.txt' overwrite=True\n"
    #     "content: This is the content\n"
    #     "to write across multiple lines.\n"
    #     "@end"
    # )

    # --- File Path Handling (If file ops exist) ---
    # Check if file operations are actually available before adding this section
    if any(op.name in ["read_file", "write_file", "delete_file", "list_directory"] for op in discover_operations()):
        builder.add_section("File Paths",
            "When using file operations:\n"
            "- Use absolute paths (e.g., `/data/file.txt`) when possible.\n"
            "- Relative paths (e.g., `./subdir/file.txt`) are relative to the server's working directory.\n"
            "- Path resolution (like `..`) is handled by the server.\n"
            "- Be mindful of case-sensitivity depending on the server's OS.\n"
            "- You may only access paths permitted by your agent configuration."
        )

    # --- Provider-Specific Notes ---
    if provider == "anthropic":
        # Anthropic specific formatting or behavior notes
        builder.add_section("Provider Notes (Anthropic)",
            "When formulating your final response to the user (after receiving operation results or if no operation is needed), structure your thoughts clearly. You do not need to use XML tags unless explicitly instructed for a specific task."
        )
    # Add elif for other providers if needed

    # --- Dynamic MCP Operations Documentation ---
    operations_docs = generate_mcp_operations_documentation()
    builder.add_section("Available MCP Operations", operations_docs)

    # --- Final Instruction ---
    builder.add_section("Response Format",
         "If a user request requires an operation, respond with the JSON operation call as specified above. "
         "If the request does not require an operation, or after you receive the result of an operation, respond to the user in a clear, concise, and helpful conversational manner."
    )


    return builder.generate()

# --- Test Execution ---
if __name__ == "__main__":
    # Example: Generate prompt for Anthropic
    prompt_text = generate_system_prompt("anthropic")
    print("--- Generated System Prompt (Anthropic) ---")
    print(prompt_text)
    print("\n--- End Prompt ---")

    # Example: Generate prompt without provider specifics
    # prompt_text_generic = generate_system_prompt()
    # print("\n--- Generated System Prompt (Generic) ---")
    # print(prompt_text_generic)
    # print("\n--- End Prompt ---")
