import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

try:
    # Use relative import within the package structure
    from ..MCP.registry import operation_registry
    from ..MCP.Operations.base import Operation, ArgumentDefinition # Import ArgumentDefinition
except ImportError:
    # Fallback for direct execution or path issues
    try:
        # This assumes script is run from project root or MCP directory structure is in path
        from MCP.registry import operation_registry
        from MCP.Operations.base import Operation, ArgumentDefinition
    except ImportError as e:
        # Define dummy classes if MCP cannot be found at all
        logger = logging.getLogger(__name__) # Define logger here if import fails early
        logger.warning(f"MCP components not found. Using dummy OperationRegistry/Operation. Error: {e}")
        class ArgumentDefinition: # Dummy definition
             name: str = "error"
             type: str = "string"
             required: bool = False
             description: str = "MCP components not found"
             default: Any = None
        class OperationRegistry:
            def get_all(self) -> Dict[str, Any]: return {}
        class Operation:
            name: str = "unavailable"
            description: str = "MCP components not found"
            arguments: List[ArgumentDefinition] = []
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
    op_arguments = getattr(op_instance, "arguments", [])
    op_name_for_log = getattr(op_instance, "name", "unknown")

    if not isinstance(op_arguments, list):
        logger.warning(f"Operation '{op_name_for_log}' has invalid 'arguments' attribute (not a list). Skipping args.")
        op_arguments = [] # Treat as empty list

    for arg_def in op_arguments:
        # Check if arg_def has the expected attributes (basic check using isinstance)
        if not isinstance(arg_def, ArgumentDefinition):
             logger.warning(f"Skipping invalid argument definition in operation '{op_name_for_log}': Object is not an ArgumentDefinition ({arg_def})")
             continue
        # Now we know it's an ArgumentDefinition, access attributes directly
        arg_data = {
            "name": arg_def.name,
            "type": arg_def.type,
            "required": arg_def.required,
            "description": arg_def.description,
        }
        # Only add default if it's explicitly defined and not None
        if getattr(arg_def, "default", None) is not None:
            arg_data["default"] = arg_def.default
        arg_list.append(arg_data)

    return OperationInfo(
        name=getattr(op_instance, "name", "Unknown Operation"),
        description=getattr(op_instance, "description", ""),
        args=arg_list,
    )

def generate_operations_documentation() -> str:
    """Generate Markdown documentation for available MCP operations."""
    ops_dict: Dict[str, Operation] = {} # Type hint
    try:
        # Ensure registry is discovered (usually done at server start)
        # operation_registry.discover_operations() # Uncomment if running standalone and discovery needed here
        ops_dict = operation_registry.get_all()
        if not ops_dict: # Check if registry discovery worked
            logger.warning("Operation registry returned no operations. MCP might not be initialized correctly or no operations found.")
            # Provide instructions for the LLM even if ops are missing
            return ("## Available MCP Operations\n\n"
                    "No MCP operations were discovered. You may only use general conversation abilities.")

    except Exception as e:
        logger.error(f"Error getting operations from registry: {e}", exc_info=True)
        return f"## Available MCP Operations\n\nError retrieving operations: {e}"

    # Sort operations by name for consistent output
    operations = sorted(ops_dict.values(), key=lambda op: getattr(op, 'name', 'zzzz'))

    docs = ["## Available MCP Operations"]

    for op in operations:
        try:
            info = get_operation_info(op) # Use helper function
            docs.append(f"### `{info.name}`")
            # Add security warning for execute_command
            if info.name == "execute_command":
                 docs.append("**\\[SECURITY WARNING]** This operation executes system commands and is HIGHLY SENSITIVE. Use with extreme caution and only when absolutely necessary and permitted.")
            docs.append(f"{info.description}")

            if info.args:
                docs.append("**Arguments:**")
                for arg in info.args:
                    # Use .get() for safer access, provide defaults
                    arg_name = arg.get('name', 'unknown_arg')
                    arg_type = arg.get('type', 'unknown')
                    arg_desc = arg.get('description', 'No description.')
                    is_required = arg.get('required', True) # Assume required if missing

                    if is_required:
                        req_status = "Required"
                    else:
                        default_val = arg.get('default') # Get default value
                        req_status = f"Optional (default: `{default_val}`)" if default_val is not None else "Optional"

                    docs.append(f"- `{arg_name}` ({arg_type}): {arg_desc} [{req_status}]")
            docs.append("") # Add spacing between operations
        except Exception as e:
            op_name = getattr(op, 'name', 'unknown')
            logger.error(f"Error generating documentation for operation '{op_name}': {e}", exc_info=True)
            docs.append(f"### `{op_name}`\n*Error generating documentation for this operation.*")
            docs.append("")

    return "\n".join(docs)


def generate_system_prompt(provider: Optional[str] = None, goal: Optional[str] = None) -> str:
    """
    Generate a complete system prompt, including MCP operation usage, goal, and behavior instructions.

    Args:
        provider: Name of the LLM provider (e.g., "anthropic") for potential specific instructions.
        goal: The specific goal for the agent.

    Returns:
        The formatted system prompt string.
    """
    sections = []

    # --- Role Definition ---
    sections.append(
        "# ROLE\n"
        "You are an autonomous AI assistant. Your primary function is to achieve a specific goal by leveraging a set of available tools called MCP Operations. "
        "You must think step-by-step, plan your actions, execute operations when necessary, and adapt based on the results."
    )

    # --- Goal ---
    if goal:
        sections.append(
            f"# GOAL\n"
            f"Your current objective is: **{goal}**\n"
            "Analyze this goal carefully. Break it down into smaller, manageable steps. Determine which MCP Operations are needed for each step. "
            "Execute the plan, evaluate the results of each operation, and adjust your plan as needed."
        )
    else:
        # Fallback if no specific goal is provided (less common for autonomous agents)
        sections.append(
            "# GOAL\n"
            "Your goal has not been explicitly set. Your primary objective is to assist the user by understanding their requests and executing tasks accurately using the available MCP Operations. Ask the user for a goal if unclear."
        )

    # --- MCP Operation Usage Instructions ---
    sections.append(
        "# MCP OPERATION USAGE\n"
        "When you need to use a tool to interact with the system or perform an action, you MUST format your response as a single JSON code block containing the operation details. "
        "**CRITICAL: Your response must ONLY contain the JSON block and nothing else (no introductory text, no explanations before or after).**\n\n"
        "The required format is:\n"
        "```json\n"
        "{\n"
        '  "mcp_operation": {\n'
        '    "operation_name": "name_of_the_operation_to_call",\n'
        '    "arguments": {\n'
        '      "argument_name_1": "value_for_argument_1",\n'
        '      "argument_name_2": value_for_argument_2,\n'
        '      "..."\n' # Indicate more args possible
        '    }\n'
        '  }\n'
        '}\n'
        "```\n"
        "- Refer to the 'Available MCP Operations' section below for the correct `operation_name` and required `arguments` for each tool.\n"
        "- Ensure the JSON is perfectly valid. Invalid JSON will cause an error.\n"
        "- Only include arguments specified for the operation. Provide values for all required arguments.\n"
        "- For file paths, use absolute paths where possible unless relative paths are clearly appropriate for the context (e.g., within a specified working directory)."
    )

    # --- Interaction and Response Format ---
    sections.append(
        "# INTERACTION & RESPONSE FORMAT\n"
        "1.  **Think Step-by-Step:** Before responding, outline your plan or reasoning. You can use `<thinking>...</thinking>` tags to enclose your thought process. This helps in debugging but might not always be visible externally.\n"
        "2.  **Choose Action:** Based on your plan and the current state, decide your next action:\n"
        "    * **Execute Operation:** If an MCP operation is needed, generate *only* the JSON code block as specified above.\n"
        "    * **Ask User:** If you require information from the user to proceed, formulate a clear question in plain text. Do NOT use the JSON format for asking questions. The system will prompt the user for input based on your text response.\n"
        "    * **Report Final Answer / Goal Completion:** If you believe the goal is fully achieved, call the `finish_goal` operation with a summary of the outcome.\n"
        "    * **Report Inability:** If you determine you cannot achieve the goal due to errors, missing capabilities, or permissions, explain why in plain text.\n"
        "3.  **Handle Results:** After an operation is executed, the system will provide the result (success or error) in a 'system' message. Carefully analyze this result before planning your next step. If an error occurred, decide whether to retry (perhaps with different arguments), use a different approach, or ask the user.\n"
        "4.  **Autonomy:** Continue this cycle of thinking, acting, and analyzing results until the `finish_goal` operation is called or you determine the goal cannot be met."
    )

    # --- Provider-Specific Notes ---
    # Add notes based on LLM provider if needed
    if provider == "anthropic":
        sections.append(
            "# PROVIDER NOTES (ANTHROPIC)\n"
            "- Use `<thinking>...</thinking>` tags extensively to show your reasoning process before deciding on an action (operation call, asking user, or finishing).\n"
            "- Ensure that if you decide to call an operation, your *entire* final response consists *only* of the ` ```json ... ``` ` block."
        )
    # Add elif for other providers if necessary

    # --- Available Operations ---
    # Generate and append the documentation for available MCP operations
    sections.append(generate_operations_documentation())

    # --- Final Instruction ---
    sections.append(
        "# FINAL INSTRUCTION\n"
        "Begin working towards your goal. Remember to plan, use operations correctly via the JSON format when needed, ask the user if necessary, and call `finish_goal` upon completion."
    )

    # Join all sections with double newlines
    return "\n\n".join(sections)


if __name__ == "__main__":
    # Example usage when run directly
    logging.basicConfig(level=logging.DEBUG) # Enable debug logging for detailed output
    logger.info("Generating example system prompt...")

    # Ensure MCP operations are discovered if running standalone
    try:
        # This assumes the script is run from the project root
        op_path = os.path.join(root_dir, "MCP", "Operations")
        if not os.path.isdir(op_path):
             logger.warning(f"MCP Operations directory not found at expected location: {op_path}. Discovery might fail.")
        operation_registry.discover_operations()
    except Exception as e:
        logger.error(f"Error during standalone operation discovery: {e}")


    test_goal = "Read the file '/tmp/agent_data/input.txt', summarize its content, and write the summary to '/tmp/agent_data/summary.txt'."
    prompt_text = generate_system_prompt(provider="anthropic", goal=test_goal)
    print("\n--- Generated System Prompt (Example with Goal) ---")
    print(prompt_text)
    print("\n--- End Prompt ---")

    # Example without goal
    # logger.info("Generating example system prompt (no goal)...")
    # prompt_text_no_goal = generate_system_prompt(provider="anthropic")
    # print("\n--- Generated System Prompt (Example without Goal) ---")
    # print(prompt_text_no_goal)
    # print("\n--- End Prompt ---")
