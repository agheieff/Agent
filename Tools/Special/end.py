from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType, ToolResult

class End(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )

        super().__init__(
            name="end",
            description="Finishes the conversation with the agent",
            args=[
                Argument(
                    name="message",
                    arg_type=ArgumentType.STRING,
                    optional=True,
                    default="Task completed successfully.",
                    description="The final message to display before ending"
                ),
                Argument(
                    name="status",
                    arg_type=ArgumentType.STRING,
                    optional=True,
                    default="success",
                    description="The status of the task (success, failure, or incomplete)"
                )
            ],
            config=config
        )

    def _run(self, args):
        message = args.get("message")
        status = args.get("status")
        valid_statuses = ["success", "failure", "incomplete"]
        if status not in valid_statuses:
             return ToolResult(success=False, code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                               message=f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}.")

        status_symbols = {
            "success": "✓",
            "failure": "✗",
            "incomplete": "⚠"
        }
        symbol = status_symbols.get(status, "")
        formatted_message = f"\n{symbol} CONVERSATION ENDED ({status}): {message}\n"
        print(formatted_message)

        raise ConversationEnded(formatted_message)
