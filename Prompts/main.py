import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

try:
    # Use relative import within the package structure
    from ..MCP.registry import operation_registry
    from ..MCP.Operations.base import Operation
except ImportError:
    # Fallback for direct execution or path issues
    try:
        from MCP.registry import operation_registry
        from MCP.Operations.base import Operation
    except ImportError:
        # Define dummy classes if MCP cannot be found at all
        logger.warning("MCP components not found. Using dummy OperationRegistry/Operation.")
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
    # Ensure op_instance has 'arguments' attribute and it's iterable
    for arg_def in getattr(op_instance, "arguments", []):
        # Check if arg_def has the expected attributes (basic check)
        if not all(hasattr(arg_def, attr) for attr in ['name', 'type', 'required', 'description']):
            logger.warning(f"Skipping invalid argument definition in operation '{getattr(op_instance, 'name', 'unknown')}': {arg_def}")
            continue

        arg_data = {
            "name": arg_def.name,
            "type": arg_def.type,
            "required": arg_def.required,
            "description": arg_def.description,
        }
        # Use getattr for default as it might not always be present
        default_val = getattr(arg_def, "default", None)
        if default_val is not None:
            arg_data["default"] = default_val
        arg_list.append(arg_data)

    return OperationInfo(
        name=getattr(op_instance, "name", "Unknown Operation"),
        description=getattr(op_instance, "description", ""),
        args=arg_list,
    )

def generate_operations_documentation() -> str:
    """Generate Markdown documentation for MCP operations."""
    try:
        ops_dict = operation_registry.get_all()
        if not ops_dict: # Check if registry discovery worked
             logger.warning("Operation registry returned no operations. MCP might not be initialized correctly.")
             return "## Available MCP Operations\n\nNo MCP operations discovered or available."

        operations = sorted(list(ops_dict.values()), key=lambda op: getattr(op, 'name', 'zzzz'))
    except Exception as e:
        logger.error(f"Error getting operations from registry: {e}", exc_info=True)
        return f"## Available MCP Operations\n\nError retrieving operations: {e}"

    if not operations:
        return "## Available MCP Operations\n\nNo MCP operations discovered."

    docs = ["## Available MCP Operations"]

    for op in operations:
        try:
            info = get_operation_info(op)
            docs.append(f"### `{info.name}`\n{info.description}")

            if info.args:
                docs.append("**Arguments:**")
                for arg in info.args:
                    req_status = "Required" if arg.get('required', True) else f"Optional (default: `{arg.get('default', 'None')}`)"
                    docs.append(f"- `{arg['name']}` ({arg['type']}): {arg['description']} [{req_status}]")
            docs.append("") # Add spacing
        except Exception as e:
            op_name = getattr(op, 'name', 'unknown')
            logger.error(f"Error generating documentation for operation '{op_name}': {e}", exc_info=True)
            docs.append(f"### `{op_name}`\n*Error generating documentation for this operation.*")
            docs.append("")

    return "\n".join(docs)

# --- MODIFIED FUNCTION ---
def generate_system_prompt(provider: Optional[str] = None, goal: Optional[str] = None) -> str:
    """
    Generate a complete system prompt, including an optional goal.

    Args:
        provider: Name of the LLM provider (e.g., "anthropic") for potential specific instructions.
        goal: The specific goal for the agent.

    Returns:
        The formatted system prompt string.
    """
    sections = []

    # Role section
    sections.append("# ROLE\nYou are an autonomous AI assistant designed to achieve a specific goal using available tools (MCP Operations).")

    # Goal section - Include the specific goal if provided
    if goal:
        sections.append(f"# GOAL\nYour current objective is: **{goal}**\n"
                        "Break down this goal into steps and use the available MCP Operations to achieve it. "
                        "Think step-by-step about your plan and the operations needed.")
    else:
         sections.append("# GOAL\nYour primary goal is to assist the user by understanding their requests and executing tasks accurately using the available MCP Operations.")


    # Usage instructions
    sections.append(
        "# MCP OPERATION USAGE\n"
        "When you determine that an MCP Operation is necessary to progress towards your goal, you MUST respond *only* with a single JSON code block formatted exactly like this:\n"
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
        "- Ensure the JSON is valid.\n"
        "- Provide *only* the arguments required by the specific operation (see documentation below).\n"
        "- Do not include any other text, explanations, or conversational filler before or after the JSON block if you are calling an operation."
    )

    # Add provider-specific notes if needed
    if provider == "anthropic":
        sections.append(
            "# PROVIDER NOTES (ANTHROPIC)\n"
            "- Think step-by-step within your response *before* deciding to call an operation or providing a final answer. Use <thinking>...</thinking> tags if helpful.\n"
            "- If calling an operation, your final response should *only* be the JSON block."
        )

    # Add operations documentation
    sections.append(generate_operations_documentation())

    # Response format and autonomous behavior
    sections.append(
        "# RESPONSE AND BEHAVIOR\n"
        "1. **Analyze**: Review the goal and the conversation history, including previous operation results.\n"
        "2. **Plan**: Decide the next logical step towards the goal.\n"
        "3. **Execute or Respond**: \n"
        "   - If an MCP operation is needed for the next step, provide the JSON call as described above.\n"
        "   - If no operation is needed, or you need clarification, respond with your reasoning or questions in plain text.\n"
        "   - If you believe the goal has been successfully achieved, clearly state 'Goal Achieved:' followed by a summary of the outcome.\n"
        "4. **Error Handling**: If an operation fails, analyze the error message provided in the system response and decide whether to retry, try a different approach, or report that you cannot proceed.\n"
        "5. **Autonomy**: Continue this loop until the goal is achieved or you determine it's impossible."
    )

    return "\n\n".join(sections)

if __name__ == "__main__":
    # Example usage when run directly
    test_goal = "Read the first 5 lines of '/tmp/my_test_file.txt' and then write 'Done' to '/tmp/my_test_output.txt'."
    prompt_text = generate_system_prompt(provider="anthropic", goal=test_goal)
    print("--- Generated System Prompt (Example) ---")
    print(prompt_text)
    print("\n--- End Prompt ---")

    # Example without goal
    # prompt_text_no_goal = generate_system_prompt()
    # print("\n--- Generated System Prompt (No Goal) ---")
    # print(prompt_text_no_goal)
    # print("\n--- End Prompt ---")
