from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class Pause(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="pause",
            description="Pauses the agent and waits for user input",
            help_text="Stops the conversation, displays a message to the user, and waits for their input before continuing.",
            arguments=[
                Argument(
                    name="message",
                    arg_type=ArgumentType.STRING,
                    is_optional=True,
                    default_value="The agent is waiting for your input. Please provide any additional information or press Enter to continue.",
                    description="The message to display to the user when pausing"
                )
            ],
            config=config
        )

    def _execute(self, message="The agent is waiting for your input. Please provide any additional information or press Enter to continue."):
        """
        Pauses execution and waits for user input.
        
        Args:
            message: Message to display to the user
            
        Returns:
            A tuple containing the error code and the user's input message
        """
        # Print the message
        print(f"\n{message}\n")
        
        # Wait for user input
        user_input = input("> ")
        
        # Return the user input to be added to the conversation
        return ErrorCodes.SUCCESS, f"User input: {user_input}" 