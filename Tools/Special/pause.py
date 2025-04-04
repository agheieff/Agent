from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class Pause(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )

        super().__init__(
            name="pause",
            description="Pauses the agent and waits for user input",
            help_text="Stops the conversation, displays a message to the user, and waits for their input before continuing.",
            arguments=[
                Argument(
                    name="message",
                    arg_type=ArgumentType.STRING,
                    optional=True,
                    default_value="The agent is waiting for your input. Please provide any additional information or press Enter to continue.",
                    description="The message to display to the user when pausing"
                )
            ],
            config=config
        )

    def _execute(self, message="The agent is waiting for your input. Please provide any additional information or press Enter to continue."):
        print(f"\n{message}\n")
        user_input = input("> ")
        return ErrorCodes.SUCCESS, f"User input: {user_input}" 
