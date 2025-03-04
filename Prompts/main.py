def generate_command_execution_guide(provider: str = "openai") -> str:
    """
    Generate model-specific command execution guidelines.
    Different providers have different ways of handling tool usage.
    
    Args:
        provider: The LLM provider (anthropic, deepseek, openai)
        
    Returns:
        A string with the command execution guidelines
    """
    provider = provider.lower()
    
    if provider == "anthropic":
        # Claude has native tool use - use its JSON format
        return """
## Command Execution for Claude

Claude supports native tool use. When you need to execute a command, use the following format:

<answer>I'll help solve this.</answer>

<tool_use>
{
  "name": "tool_name",
  "input": {
    "param1": "value1",
    "param2": "value2"
  }
}
</tool_use>

You can use reasoning naturally in your responses. After the command execution, you'll receive the result from the tool.

**Available Tools:**
- `read`: Read file contents
- `write`: Create a new file
- `edit`: Replace a single occurrence in a file
- `replace`: Replace entire file contents
- `bash`: Execute shell commands
- `curl`: Make HTTP requests
- `message`: Display a message to the user
- `compact`: Summarize conversation history
- `pause`: Wait for user input
- `finish`: End the conversation

Use the message tool to communicate your thoughts to the user when no other tool is needed.
"""
    elif provider == "deepseek":
        # DeepSeek doesn't have native tool use - expects JSON format
        return """
## Command Execution for DeepSeek

When executing commands, you MUST return a valid JSON object with the following structure:

```json
{
  "thinking": "Your hidden reasoning process (will not be shown to user)",
  "reasoning": "A concise explanation that will be shown to the user",
  "action": "tool_name",
  "action_input": {
    "param1": "value1",
    "param2": "value2"
  },
  "response": "Any additional information for the user"
}
```

Your entire response must be valid JSON. If you don't need to use a tool, use the `message` tool to display text to the user.

**Available Tools:**
- `read`: Read file contents
- `write`: Create a new file
- `edit`: Replace a single occurrence in a file
- `replace`: Replace entire file contents
- `bash`: Execute shell commands
- `curl`: Make HTTP requests
- `message`: Display a message to the user
- `compact`: Summarize conversation history
- `pause`: Wait for user input
- `finish`: End the conversation

Always respond with valid JSON, even when simply communicating with the user.
"""
    else:
        # Default format (OpenAI and others)
        return """
## Command Execution

Return a valid JSON object with this structure:

```json
{
  "thinking": "Your hidden reasoning process (will not be shown to user)",
  "analysis": "A concise explanation that will be shown to the user",
  "tool_calls": [
    {
      "name": "tool_name",
      "params": {
        "param1": "value1",
        "param2": "value2"
      }
    }
  ],
  "answer": "Any additional explanation or answer for the user"
}
```

You can include multiple tool calls in a single response if needed.

**Available Tools:**
- `read`: Read file contents
- `write`: Create a new file
- `edit`: Replace a single occurrence in a file
- `replace`: Replace entire file contents
- `bash`: Execute shell commands
- `curl`: Make HTTP requests
- `message`: Display a message to the user
- `compact`: Summarize conversation history
- `pause`: Wait for user input
- `finish`: End the conversation

If you don't need to use a tool, use the `message` tool to display text to the user.
"""

def generate_agent_role_explanation() -> str:
    """
    Generate an explanation of the agent's role in the system.
    """
    return """
## Agent Role

You are not communicating directly with a human. You are an autonomous agent operating a system.

1. Your responses will be parsed to extract tool calls.
2. Tools will be executed on your behalf.
3. Results of tool execution will be returned to you.
4. You should use the `message` tool to communicate with the user.
5. Use the `finish` tool when the conversation should end.
6. Use the `pause` tool when you need direct user input.
7. Use the `compact` tool to summarize the conversation when it gets too long.

Remember: Whatever you output will be treated as a command to the system unless formatted as a message.
"""

def generate_conversation_tracking() -> str:
    """
    Generate an explanation of conversation tracking.
    """
    return """
## Conversation Tracking

Each tool result will include:
- Success/failure status
- Output or error message
- Timestamp
- Conversation statistics:
  - Current turn number
  - Tokens used so far
  - Time elapsed since conversation start
  - Time since last compact operation

Monitor these statistics to manage the conversation efficiently:
- Use `compact` when the conversation gets lengthy
- Use `finish` when the task is complete
- Be mindful of token usage for efficient operation
"""

def generate_system_prompt(config_path: Optional[str] = None, summary_path: Optional[str] = None) -> str:
    config = load_config(config_path)
    provider = config.get("llm", {}).get("default_model", "openai").lower()
    
    # If provider is a model name rather than a provider name, extract the provider
    if "claude" in provider:
        provider = "anthropic"
    elif "gpt" in provider or "openai" in provider:
        provider = "openai"
    elif "deepseek" in provider:
        provider = "deepseek"
    
    sections = [
        generate_system_info(config),
        generate_introduction(config),
        generate_reasoning_protocol(),
        generate_command_execution_guide(provider),  # Now provider-specific
        generate_agent_role_explanation(),  # New section
        generate_tools_section(config),
        generate_conversation_tracking(),  # New section
        generate_best_practices(),
        generate_memory_management(),
        generate_security_restrictions(config),
        generate_config_summary(config),
        generate_session_summary_wrapper(summary_path),
        generate_final_guidelines()
    ]

    prompt = "\n".join(sections)

    if config.get("agent", {}).get("test_mode", False):
        prompt = generate_test_mode_warning() + prompt

    return prompt
