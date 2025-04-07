from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType, ToolResult

class Pause(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )
        super().__init__(
            name="pause",
            description="Pauses the agent and signals the orchestrator to wait for user input",
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
        """Signals that a pause is requested, returning the message to display."""
        message = args.get("message")
        print(f"[Pause Tool Executed] Signaling pause with message: '{message}'")
        # Return the specific message the orchestrator should show the user
        return ToolResult(success=True, code=ErrorCodes.SUCCESS, message=message)
