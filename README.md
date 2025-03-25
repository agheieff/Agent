# Arcadia Agent

A lightweight framework for building AI agents with tool usage capabilities.

## Key Features

- **Simplified Architecture**: Single core class (`AgentRunner`)
- **Easy Tool Creation**: Straightforward tool development pattern
- **Multi-provider Support**: OpenAI, Anthropic, Gemini, etc.
- **Clean Error Handling**: Consistent error reporting

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a simple tool:

```python
# tools/greeter.py
from Tools.base import Tool, Argument

class Greeter(Tool):
    def __init__(self):
        super().__init__(
            name="greeter",
            description="Greets a person",
            args=[Argument("name", ArgumentType.STRING, "Name to greet")]
        )

    def _run(self, args):
        return {"greeting": f"Hello, {args['name']}!"}
```

3. Run the agent:
```python
from Core.agent_runner import AgentRunner

agent = AgentRunner(provider="openai")
agent.run("Say hello to John using the greeter tool")
```


## Architecture Overview

1. AgentRunner: Main controller that:
    - Manages conversation state
    - Handles model interactions
    - Coordinates tool usage

2. Tools: Self-contained operations that:
    - Declare their interface
    - Implement single functions
    - Return simple data structures

3. Clients: Provider-specific implementations that:
    - Handle API communication
    - Normalize responses
    - Manage rate limiting
