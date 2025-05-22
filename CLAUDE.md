# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Setup and Installation
```bash
# Run the setup script to create virtual environment and install dependencies
./setup.sh

# Or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov pytest-mock  # dev dependencies
```

### Running the Agent
```bash
# Interactive provider/model selection
./run.py

# Specify provider (will prompt for model)
./run.py --provider anthropic

# Specify both provider and model
./run.py --provider openai --model gpt-4
```

### Testing
```bash
# Run all tests with pytest (preferred)
python test.py
# or directly:
pytest -v Tests/

# Run specific test file
pytest Tests/Tools/File/test_read.py

# Run with coverage
pytest --cov=. Tests/
```

### API Testing
```bash
# Test LLM provider connections
python api_test.py
```

## High-Level Architecture

### Core Components

1. **Orchestrator (`Core/orchestrator.py`)**: Main controller managing multi-agent systems
   - Initializes agents from YAML configs in `AgentConfigs/`
   - Manages conversation loops and agent interactions
   - Handles CEO agent delegation pattern

2. **Agent Instance (`Core/agent_instance.py`)**: Individual agent implementation
   - Maintains message history and conversation state
   - Streams LLM responses with tool call interruption
   - Executes tools via the Executor

3. **Executor (`Core/executor.py`)**: Tool execution engine
   - Parses tool calls from LLM responses
   - Validates arguments and executes tools
   - Returns results back to the agent

4. **Stream Manager (`Core/stream_manager.py`)**: Async streaming handler
   - Manages streaming responses from different LLM providers
   - Detects and interrupts on tool calls
   - Handles partial tool call accumulation

### Tool System

Tools inherit from `Tools/base.py` and follow this pattern:
- Define arguments with `Argument` dataclass specifying name, type, and description
- Implement `_run(args)` method that returns success/failure results
- Use `ToolResult` for consistent error handling
- Special exceptions (`ConversationEnded`, `ConversationPaused`) control flow

Tool categories:
- **File Tools** (`Tools/File/`): read, write, edit, delete, ls operations
- **Special Tools** (`Tools/Special/`): pause, message, end for control flow

### Provider Abstraction

LLM providers implement `Clients/base.py` interface:
- Unified message format across providers
- Streaming support with tool call detection
- Provider-specific clients in `Clients/API/`

### Configuration

- **API Keys**: Set in `.env` file (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
- **Models**: Defined in `config.py` with pricing and capability tiers
- **Agents**: YAML configurations in `AgentConfigs/` defining role, model, tools

### Error Handling

- Standardized error codes in `Tools/error_codes.py`
- `ToolException` hierarchy for different failure types
- Graceful degradation on tool failures