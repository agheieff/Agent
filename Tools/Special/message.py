from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType, ToolResult

class Message(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )

        super().__init__(
            name="message",
            description="Sends a message from the agent to the user",
            args=[
                Argument(
                    name="text",
                    arg_type=ArgumentType.STRING,
                    description="The message text to display to the user"
                ),
                Argument(
                    name="important",
                    arg_type=ArgumentType.BOOLEAN,
                    optional=True,
                    default=False,
                    description="Whether to highlight this message as important"
                )
            ],
            config=config
        )

    def _run(self, args):
        text = args.get("text")
        important = args.get("important")

        if text is None:
             return ToolResult(success=False, code=ErrorCodes.MISSING_REQUIRED_ARGUMENT, message="Missing required argument: text")

        if important:
            formatted_message = f"\n!!! IMPORTANT MESSAGE !!!\n{text}\n!!!\n"
        else:
            formatted_message = f"\n{text}\n"

        print(formatted_message)
        return ToolResult(success=True, code=ErrorCodes.SUCCESS, message="Message displayed.")
