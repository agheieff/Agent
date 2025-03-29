import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

# No longer imports MCP registry directly
from MCP.Operations.base import Operation, ArgumentDefinition # Keep base types

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
    op_arguments = getattr(op_instance, "arguments", [])
    op_name_for_log = getattr(op_instance, "name", "unknown")

    if not isinstance(op_arguments, list):
        logger.warning(f"Operation '{op_name_for_log}' has invalid 'arguments' attribute (not a list). Skipping args.")
        op_arguments = []

    for arg_def in op_arguments:
        if not isinstance(arg_def, ArgumentDefinition):
            logger.warning(f"Skipping invalid argument definition in operation '{op_name_for_log}': Object is not an ArgumentDefinition ({arg_def})")
            continue

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
        name=getattr(op_instance, "name", "Unknown Operation"),
        description=getattr(op_instance, "description", ""),
        args=arg_list,
    )

def generate_operations_documentation(operations_dict: Dict[str, Operation]) -> str:
    """
    Generate Markdown documentation for the provided MCP operations.

    Args:
        operations_dict: A dictionary mapping operation names to their instances.

    Returns:
        A string containing Markdown documentation.
    """
    if not operations_dict:
        logger.warning("generate_operations_documentation received an empty operations dictionary.")
        return ("## Available MCP Operations\n\n"
                "No MCP operations were provided. You may only use general conversation abilities.")

    # Sort operations by name for consistent output
    operations = sorted(operations_dict.values(), key=lambda op: getattr(op, 'name', 'zzzz'))

    docs = ["## Available MCP Operations"]

    for op in operations:
        try:
            info = get_operation_info(op)
            docs.append(f"### `{info.name}`")
            if info.name == "execute_command":
                docs.append("**\\[SECURITY WARNING]** This operation executes system commands and is HIGHLY SENSITIVE. Use with extreme caution and only when absolutely necessary and permitted.")
            docs.append(f"{info.description}")

            if info.args:
                docs.append("**Arguments:**")
                for arg in info.args:
                    arg_name = arg.get('name', 'unknown_arg')
                    arg_type = arg.get('type', 'unknown')
                    arg_desc = arg.get('description', 'No description.')
                    is_required = arg.get('required', True)

                    if is_required:
                        req_status = "Required"
                    else:
                        default_val = arg.get('default')
                        req_status = f"Optional (default: `{default_val}`)" if default_val is not None else "Optional"

                    docs.append(f"- `{arg_name}` ({arg_type}): {arg_desc} [{req_status}]")
            docs.append("") # Add spacing
        except Exception as e:
            op_name = getattr(op, 'name', 'unknown')
            logger.error(f"Error generating documentation for operation '{op_name}': {e}", exc_info=True)
            docs.append(f"### `{op_name}`\n*Error generating documentation for this operation.*")
            docs.append("")

    return "\n".join(docs)


def generate_system_prompt(
    operations_doc: str, # Accept pre-generated documentation
    provider: Optional[str] = None,
    goal: Optional[str] = None
) -> str:
    """
    Generate a complete system prompt, including MCP operation usage, goal, and behavior instructions.

    Args:
        operations_doc: Pre-generated Markdown documentation of available operations.
        provider: Name of the LLM provider (e.g., "anthropic") for specific instructions.
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
        sections.append(
            "# GOAL\n"
            "Your goal has not been explicitly set. Your primary objective is to assist the user by understanding their requests and executing tasks accurately using the available MCP Operations. Ask the user for a goal if unclear."
        )

    # --- MCP Operation Usage Instructions ---
    # (Keep the detailed instructions as they were)
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
        '      "..."\n'
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
    # (Keep the detailed instructions as they were)
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
    if provider == "anthropic":
        sections.append(
            "# PROVIDER NOTES (ANTHROPIC)\n"
            "- Use `<thinking>...</thinking>` tags extensively to show your reasoning process before deciding on an action (operation call, asking user, or finishing).\n"
            "- Ensure that if you decide to call an operation, your *entire* final response consists *only* of the ` ```json ... ``` ` block."
        )
    # Add elif for other providers if necessary

    # --- Available Operations (Use the provided documentation) ---
    # Append the pre-generated documentation string
    sections.append(operations_doc)

    # --- Final Instruction ---
    sections.append(
        "# FINAL INSTRUCTION\n"
        "Begin working towards your goal. Remember to plan, use operations correctly via the JSON format when needed, ask the user if necessary, and call `finish_goal` upon completion."
    )

    # Join all sections with double newlines
    return "\n\n".join(sections)


# Keep the __main__ block for standalone testing/debugging if desired
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger.info("Generating example system prompt (requires MCP components)...")

    # Example of how to use the refactored functions if run standalone
    # This now requires manual registry access IF run directly
    try:
        # If run directly, need to manually ensure registry is populated
        from MCP.registry import operation_registry
        try:
            operation_registry.discover_operations() # Manually discover
        except Exception as discovery_err:
             logger.error(f"Standalone discovery failed: {discovery_err}. Using dummy ops.")
             # Create dummy ops if discovery fails
             class DummyOp(Operation): name="dummy"; description="dummy"; arguments=[]
             example_ops = {"dummy": DummyOp()}
        else:
             example_ops = operation_registry.get_all()

        ops_docs = generate_operations_documentation(example_ops)

        test_goal = "Read '/tmp/input.txt' and write summary to '/tmp/summary.txt'."
        prompt_text = generate_system_prompt(
            operations_doc=ops_docs,
            provider="anthropic",
            goal=test_goal
        )
        print("\n--- Generated System Prompt (Example with Goal) ---")
        print(prompt_text)
        print("\n--- End Prompt ---")

    except ImportError as e:
        logger.error(f"Could not run standalone example: MCP components import failed. {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in standalone example: {e}", exc_info=True)
