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
                    # Note: Made text non-optional
                ),
                Argument(
                    name="important",
                    arg_type=ArgumentType.BOOLEAN,
                    optional=True,
                    default=False, # Default is False
                    description="Whether to highlight this message as important"
                )
            ],
            config=config
        )

    def _run(self, args):
        text = args.get("text")
        important_arg = args.get("important", False) # Get arg, default to False

        if text is None:
            # This check might be redundant if argument validation is added to base Tool
            return ToolResult(success=False, code=ErrorCodes.MISSING_REQUIRED_ARGUMENT, message="Missing required argument: text")

        # --- Handle string 'true'/'false' conversion for important flag ---
        is_important = False
        if isinstance(important_arg, bool):
            is_important = important_arg
        elif isinstance(important_arg, str):
            is_important = important_arg.lower() == 'true'
        # ---------------------------------------------------------------

        if is_important:
            formatted_message = f"\n!!! IMPORTANT MESSAGE !!!\n{text}\n!!!\n"
        else:
            formatted_message = f"\n{text}\n"

        # Use print for direct user visibility in terminal
        print(formatted_message)
        # Return success, message indicates display happened
        return ToolResult(success=True, code=ErrorCodes.SUCCESS, message="Message displayed.")
