# LLM API Clients

A lightweight, modular interface for interacting with various Language Model APIs (OpenAI, Anthropic, Google, DeepSeek).

## Architecture

This package uses a modular design with:

- **Composition over inheritance**: Components are designed as separate classes that work together
- **Single responsibility**: Each class has a clear, focused purpose
- **Context managers**: Rate limiting via Python context managers for cleaner code
- **Consistent interfaces**: All clients implement the same methods with identical signatures

## Features

- **Unified Interface**: Common API across different providers
- **Clean System Prompt Handling**: Smart handling of system prompts based on model capabilities
- **Usage Tracking**: Automatic token counting and cost calculation
- **Chain-of-Thought Support**: Option to extract final answers from reasoning

## Supported Models

- **OpenAI**: GPT-3.5, GPT-4
- **Anthropic**: Claude 3.7 Sonnet, Claude 3.5 Sonnet
- **Google**: Gemini Pro
- **DeepSeek**: DeepSeek Chat, DeepSeek Reasoner (with optional reasoning discard)

## Installation

Install the required packages for the providers you want to use:

```bash
# For OpenAI support (also required for DeepSeek)
pip install openai

# For Anthropic support
pip install anthropic

# For Google Gemini support
pip install google-generativeai
```

## Usage

### Basic Example

```python
from Clients import OpenAIClient, Message

# Initialize the client
client = OpenAIClient(api_key="your-api-key")

# Create messages
messages = [
    Message(role="user", content="Tell me about artificial intelligence")
]

# Get a response
response = client.chat_completion(
    messages=messages,
    model="gpt-3.5-turbo",
    system_prompt="You are an AI assistant that provides clear, concise information.",
    max_tokens=150
)

print(response.choices[0].message.content)
```

### Using Different Providers

Each client follows the same interface pattern:

```python
# Using Anthropic's Claude
from Clients import AnthropicClient, Message

messages = [Message(role="user", content="Explain neural networks")]
system_prompt = "You are an AI expert."

client = AnthropicClient(api_key="your-anthropic-api-key")
response = client.chat_completion(
    messages=messages,
    model="claude-3-5-sonnet",
    system_prompt=system_prompt
)
print(response.content[0].text)

# Using Google's Gemini
from Clients import GeminiClient

client = GeminiClient(api_key="your-google-api-key")
response = client.chat_completion(
    messages=messages,
    model="gemini-pro",
    system_prompt=system_prompt
)
print(response.text)

# Using DeepSeek
from Clients import DeepSeekClient

client = DeepSeekClient(api_key="your-deepseek-api-key")
response = client.chat_completion(
    messages=messages,
    model="deepseek-chat",
    system_prompt=system_prompt
)
print(response.choices[0].message.content)
```

### Handling Chain-of-Thought Reasoning

DeepSeek's reasoner model provides step-by-step thinking that can be extracted:

```python
from Clients import DeepSeekClient, Message

client = DeepSeekClient()

# Math problem requiring reasoning
messages = [
    Message(role="user", content=(
        "A train travels at 120 km/h for 2 hours, then slows down to 90 km/h for the next 3 hours. "
        "What is the average speed of the train for the entire journey?"
    ))
]

# Get full reasoning with step-by-step work
full_response = client.chat_completion(
    messages=messages,
    model="deepseek-reasoner",
    discard_reasoning=False
)
print("FULL REASONING:")
print(full_response.choices[0].message.content)

# Get only the final answer (more concise)
concise_response = client.chat_completion(
    messages=messages,
    model="deepseek-reasoner",
    discard_reasoning=True
)
print("\nFINAL ANSWER ONLY:")
print(concise_response.choices[0].message.content)
```

### Environment Variables

API keys can be automatically loaded from environment variables:

- `OPENAI_API_KEY` for OpenAI
- `ANTHROPIC_API_KEY` for Anthropic
- `GOOGLE_API_KEY` for Google Gemini
- `DEEPSEEK_API_KEY` for DeepSeek models

```python
# Will automatically use OPENAI_API_KEY if set
client = OpenAIClient()
```

## Architecture Details

The package uses a modular design with:

1. **BaseClient**: Core functionality for all clients
2. **SystemPromptHandler**: Specialized handling of system prompts  
3. **ReasoningExtractor**: Extracts final answers from reasoning chains
4. **Provider-specific clients**: Implement provider-specific logic

This separation of concerns makes the code more maintainable and easier to extend.

## See Also

Check `example.py` for more usage examples. 