from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class End(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="end",
            description="Finishes the conversation with the agent",
            help_text="Signals that the agent has completed its task and ends the conversation.",
            arguments=[
                Argument(
                    name="message",
                    arg_type=ArgumentType.STRING,
                    is_optional=True,
                    default_value="Task completed successfully.",
                    description="The final message to display before ending"
                ),
                Argument(
                    name="status",
                    arg_type=ArgumentType.STRING,
                    is_optional=True,
                    default_value="success",
                    description="The status of the task (success, failure, or incomplete)"
                )
            ],
            config=config
        )

    def _execute(self, message="Task completed successfully.", status="success"):
        """
        Ends the conversation with the agent.
        
        Args:
            message: Final message to display
            status: Status of the task (success, failure, or incomplete)
            
        Returns:
            A tuple containing the error code and a message indicating the conversation has ended
        """
        # Validate status
        valid_statuses = ["success", "failure", "incomplete"]
        if status not in valid_statuses:
            return ErrorCodes.INVALID_ARGUMENT_VALUE, f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}."
        
        # Format the final message
        status_symbols = {
            "success": "✓",
            "failure": "✗",
            "incomplete": "⚠"
        }
        
        symbol = status_symbols.get(status, "")
        formatted_message = f"\n{symbol} CONVERSATION ENDED: {message}\n"
        
        # Print the message
        print(formatted_message)
        
        # Return a special code to indicate the conversation should end
        # This will be handled by the agent runner
        return 999, "CONVERSATION_END" 