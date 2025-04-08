import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING
import inspect

from Tools.Core.registry import ToolRegistry
from Tools.base import Tool, Argument, ArgumentType # Added ArgumentType

# Avoid circular import, only needed for type hints
if TYPE_CHECKING:
    from Core.agent_config import AgentConfiguration

# --- Tool Discovery Logic (Keep as is or refine) ---

@dataclass
class ToolInfo:
    name: str
    description: str
    args: List[Dict[str, str]] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

def get_tool_info(tool_instance: Tool) -> ToolInfo:
    """Extracts metadata from a Tool instance."""
    arg_list = []
    if hasattr(tool_instance, "args"):
        for arg in tool_instance.args:
            arg_info = {
                "name": arg.name,
                "type": arg.arg_type.name, # Use Enum name
                "description": arg.description,
                "optional": arg.optional,
            }
            if arg.optional and arg.default is not None:
                arg_info["default"] = str(arg.default) # Include default if present
            arg_list.append(arg_info)

    examples = getattr(tool_instance, "examples", [])
    return ToolInfo(
        name=tool_instance.name,
        description=tool_instance.description,
        args=arg_list,
        examples=examples
    )

def discover_tools() -> Dict[str, Tool]:
    """Discovers tools and returns them as a dictionary."""
    registry = ToolRegistry()
    # Ensure discovery runs if it hasn't already
    if not registry._discovered:
        print("Running tool discovery...")
        registry.discover_tools()
    return registry.get_all() # Return the dict

# --- Prompt Building Logic ---

class PromptGenerator:
    """Simple builder for constructing multi-section prompts."""
    def __init__(self):
        self.sections = []

    def add_section(self, title: str, content: str):
        if content and content.strip(): # Only add sections with content
            self.sections.append((title.strip(), content.strip()))
        return self

    def generate(self) -> str:
        return "\n\n".join(
            f"# {title.upper()}\n{content}"
            for title, content in self.sections
            if content # Ensure content exists before joining
        ).strip()

def build_allowed_tools_section(all_tools: Dict[str, Tool], allowed_tool_names: List[str]) -> str:
    """Generates Markdown documentation for allowed tools."""
    if not allowed_tool_names:
        return "No tools are available or allowed for this agent."

    tool_docs = []
    # Sort allowed names for consistent output
    sorted_allowed_names = sorted(list(set(allowed_tool_names)))

    for tool_name in sorted_allowed_names:
        tool_instance = all_tools.get(tool_name)
        if not tool_instance:
            tool_docs.append(f"### {tool_name}\n*Warning: Tool '{tool_name}' not found in registry.*")
            continue

        info = get_tool_info(tool_instance)
        tool_docs.append(f"### {info.name}\n{info.description}")
        if info.args:
            tool_docs.append("**Arguments:**")
            for arg in info.args:
                details = f"- `{arg['name']}` ({arg['type']})"
                if arg['optional']: details += " (optional"
                if 'default' in arg: details += f", default: `{arg['default']}`"
                if arg['optional']: details += ")"
                details += f": {arg['description']}"
                tool_docs.append(details)
        # Add examples if they exist
        # if info.examples:
        #     tool_docs.append("**Examples:**")
        #     for ex in info.examples:
        #         tool_docs.append(f"  ```\n  {ex}\n  ```") # Format examples nicely
        tool_docs.append("") # Add spacing between tools

    return "\n".join(tool_docs)


def build_system_prompt(config: 'AgentConfiguration', all_discovered_tools: Dict[str, Tool]) -> str:
    """
    Builds the system prompt for an agent based on its configuration.

    Args:
        config: The AgentConfiguration object.
        all_discovered_tools: A dictionary of all tools found by discover_tools().

    Returns:
        The fully constructed system prompt string.
    """
    builder = PromptGenerator()

    # 1. Core Directives (Enhanced)
    core_directives = """
You are an autonomous AI assistant.
Think step-by-step. Plan your actions carefully based on the user's request and conversation history.
Use available tools when necessary by following the specified format precisely.
Base your responses and actions *only* on the information provided in the conversation history and tool results.
Do not hallucinate tool availability or functionality.
If you lack necessary information or permissions, state it clearly.
**CRITICAL: After executing a tool and receiving the result, you MUST analyze the result, refer back to your original plan and the user's goal, and execute the *next* required step. Do NOT simply repeat the previous action unless explicitly instructed.**
""".strip() # Added CRITICAL instruction
    builder.add_section("Core Directives", core_directives)

    # 2. Role & Goal (From Config)
    # The config.system_prompt should contain the primary role definition and high-level goals.
    builder.add_section(f"Role: {config.role}", config.system_prompt)

    # 3. Tool Usage Instructions (Keep as is)
    tool_usage = """
To use a tool, output a block EXACTLY like this, replacing placeholders:
@tool <tool_name>
<argument_name_1>: <value_1>
<argument_name_2>: <value_2>
...
@end

- `<tool_name>` must be one of the tools listed below in the "Allowed Tools" section.
- Arguments should be listed one per line: `argument_name: value`.
- Values should be plain text/numbers/booleans. Do NOT enclose file paths or simple strings in extra quotes unless the quotes are part of the actual value required by the tool.
- For multi-line values (e.g., file content), you can potentially use multi-line formatting if the tool supports it, but typically provide content directly.
- Ensure the `@end` tag is on its own line.
- Only call tools listed under "Allowed Tools". Do not attempt to use other tools.
- After you output a tool call, execution will pause. You will receive the tool's result confirmation in the next turn as an assistant message. Analyze the result and your plan before proceeding.
""".strip() # Minor rephrase at the end
    builder.add_section("Tool Usage Format", tool_usage)


    # 4. State Management & Planning (New Section)
    state_management = """
- **Maintain Plan:** Keep track of the overall goal and the sequence of steps needed.
- **Refer Back:** Frequently check the initial user request and your previously stated plan.
- **Execute Next Step:** After a tool confirms execution, determine the *next logical step* according to your plan and execute it. Do not get stuck repeating the last tool.
- **Ask if Unsure:** If the next step is unclear after a tool result, ask the user for clarification.
""".strip()
    builder.add_section("State Management & Planning", state_management)


    # 5. File Path Rules (If any file tools are allowed - Keep as is)
    file_tools_allowed = any(t in config.allowed_tools for t in ['ls', 'read_file', 'write_file', 'edit_file', 'delete_file'])
    if file_tools_allowed:
        path_rules = """
- Use relative paths (e.g., `my_dir/file.txt`, `./output.log`) or absolute paths (e.g., `/app/data/config.json`).
- Assume the current working directory is the project root unless specified otherwise.
- Paths are case-sensitive on Linux/macOS.
- Do NOT add quotes around path arguments (e.g., use `path: my_file.txt`, NOT `path: 'my_file.txt'`).
""".strip()
        builder.add_section("File Path Handling", path_rules)


    # 6. Allowed Tools Documentation (Filtered based on Config - Keep as is)
    allowed_tools_docs = build_allowed_tools_section(all_discovered_tools, config.allowed_tools)
    builder.add_section("Allowed Tools", allowed_tools_docs)

    # 7. (Future) Add sections for Communication Protocols, Task Management Rules, etc.

    return builder.generate()
