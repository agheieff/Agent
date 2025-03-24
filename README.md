# Arcadia Agent

A framework for building agents that can use tools to accomplish tasks, with special handling for output and user interaction.

## Features

- **Tool Execution**: Execute tools and manage their outputs
- **Dual Output System**: Separate outputs for the conversation history and user screen
- **Token Management**: Handles truncating conversation to stay within token limits
- **Streaming Responses**: Stream model responses in real-time
- **User Interaction**: Pause and wait for user input
- **Conversation Management**: Save and load conversations

## Available Tools

The agent comes with several built-in tools:

### File Tools
- `read_file`: Read the contents of a file
- `write_file`: Create a new file with content
- `edit_file`: Edit an existing file
- `delete_file`: Delete a file
- `ls`: List directory contents with various formatting options

### Special Tools
- `message`: Display a message to the user without adding it to the conversation
- `pause`: Pause execution and wait for user input
- `end`: End the conversation with a final message

## Setup

1. Clone this repository
2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
3. Set up your API keys as environment variables:
   ```
   export OPENAI_API_KEY=your_openai_api_key
   export ANTHROPIC_API_KEY=your_anthropic_api_key
   ```

## Usage

Run the agent with a specific model and initial prompt:

```
python agent_runner.py --provider openai --model gpt-4 --prompt "Your initial prompt here"
```

Or run without a prompt to enter it interactively:

```
python agent_runner.py --provider anthropic --model claude-3-haiku-20240307
```

## Creating Custom Tools

You can create custom tools by subclassing the `Tool` class and implementing the `_execute` method. Place your custom tools in the appropriate directory within the `Tools/` folder.

Example:

```python
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType

class MyCustomTool(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="my_custom_tool",
            description="Description of what my tool does",
            help_text="Detailed help text for my tool",
            arguments=[
                Argument(
                    name="param1",
                    arg_type=ArgumentType.STRING,
                    description="Description of parameter 1"
                ),
                Argument(
                    name="param2",
                    arg_type=ArgumentType.INT,
                    is_optional=True,
                    default_value=42,
                    description="Description of parameter 2"
                )
            ],
            config=config
        )
    
    def _execute(self, param1, param2=42):
        # Implement your tool logic here
        result = f"Processed {param1} with value {param2}"
        return ErrorCodes.SUCCESS, result
```

## Architecture

The system is built with modularity in mind:

- `Tools/`: Contains all tool implementations
- `agent_runner.py`: Main agent runner class
- `model_interface.py`: Interface for language models
- `system_prompt.py`: Generates system prompts with tool information

## License

MIT License 