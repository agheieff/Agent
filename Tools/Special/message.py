from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class Message(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
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
                    is_optional=True,
                    default_value=False,
                    description="Whether to highlight this message as important"
                )
            ],
            config=config
        )

    def _execute(self, text, important=False):
        """
        Displays a message to the user.
        
        Args:
            text: The message content to display
            important: Whether to highlight the message as important
            
        Returns:
            A tuple containing the error code and message (None if successful)
        """
        # Format the message
        if important:
            formatted_message = f"\n!!! IMPORTANT MESSAGE !!!\n{text}\n!!!\n"
        else:
            formatted_message = f"\n{text}\n"
            
        # Print the message to the user's screen
        print(formatted_message)
        
        # Return success with no additional message for the conversation
        return ErrorCodes.SUCCESS, None 