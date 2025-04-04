from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType, ToolResult

class Pause(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )

        super().__init__(
            name="pause",
            description="Pauses the agent and waits for user input",
            args=[
                Argument(
                    name="message",
                    arg_type=ArgumentType.STRING,
                    optional=True,
                    default="The agent is waiting for your input. Please provide any additional information or press Enter to continue.",
                    description="The message to display to the user when pausing"
                )
            ],
            config=config
        )

    def _run(self, args):
        message = args.get("message")
        print(f"\n{message}\n")
        user_input = input("> ")
        return ToolResult(success=True, code=ErrorCodes.SUCCESS, message=f"User input: {user_input}")
