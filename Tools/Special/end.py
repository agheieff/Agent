from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class End(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )

        super().__init__(
            name="end",
            description="Finishes the conversation with the agent",
            help_text="Signals that the agent has completed its task and ends the conversation.",
            arguments=[
                Argument(
                    name="message",
                    arg_type=ArgumentType.STRING,
                    optional=True,
                    default_value="Task completed successfully.",
                    description="The final message to display before ending"
                ),
                Argument(
                    name="status",
                    arg_type=ArgumentType.STRING,
                    optional=True,
                    default_value="success",
                    description="The status of the task (success, failure, or incomplete)"
                )
            ],
            config=config
        )

    def _execute(self, message="Task completed successfully.", status="success"):
        valid_statuses = ["success", "failure", "incomplete"]
        if status not in valid_statuses:
            return ErrorCodes.INVALID_ARGUMENT_VALUE, f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}."

        status_symbols = {
            "success": "✓",
            "failure": "✗",
            "incomplete": "⚠"
        }

        symbol = status_symbols.get(status, "")
        formatted_message = f"\n{symbol} CONVERSATION ENDED: {message}\n"

        print(formatted_message)

        return 999, "CONVERSATION_END" 
