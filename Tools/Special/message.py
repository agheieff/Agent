from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class Message(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )

        super().__init__(
            name="message",
            description="Sends a message from the agent to the user",
            help_text="Outputs a message to the user's screen without adding it to the conversation history.",
            arguments=[
                Argument(
                    name="text",
                    arg_type=ArgumentType.STRING,
                    description="The message text to display to the user"
                ),
                Argument(
                    name="important",
                    arg_type=ArgumentType.BOOLEAN,
                    optional=True,
                    default_value=False,
                    description="Whether to highlight this message as important"
                )
            ],
            config=config
        )

    def _execute(self, text, important=False):
        if important:
            formatted_message = f"\n!!! IMPORTANT MESSAGE !!!\n{text}\n!!!\n"
        else:
            formatted_message = f"\n{text}\n"

        print(formatted_message)

        return ErrorCodes.SUCCESS, None 
