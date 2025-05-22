# Directory Structure

> **Note**: This structure will be significantly simplified in the upcoming MCP refactor. See `improvement_plan.md` for the proposed new structure.

## Current Structure

```
Agent/
├── AgentConfigs/           # YAML configuration files for agents
│   ├── ceo.yaml           # CEO agent configuration
│   └── default_agent.yaml # Default agent template
│
├── Clients/                # LLM provider implementations
│   ├── API/
│   │   ├── anthropic.py   # Anthropic client
│   │   ├── deepseek.py    # DeepSeek client
│   │   └── __init__.py
│   ├── base.py            # Base client interface
│   └── README.md
│
├── Core/                   # Core agent functionality
│   ├── agent_config.py    # Agent configuration dataclasses
│   ├── agent_instance.py  # Individual agent implementation
│   ├── executor.py        # Tool execution engine
│   ├── orchestrator.py    # Multi-agent orchestration
│   ├── stream_manager.py  # Async streaming handler
│   ├── tool_parser.py     # Custom tool call parser
│   └── utils.py           # Utility functions
│
├── Docs/                   # Documentation
│   ├── creating_tools.md  # (DEPRECATED) Legacy tool creation
│   ├── directory_structure.md
│   ├── improvement_plan.md # Modernization roadmap
│   ├── plan.md            # (OUTDATED) Original roadmap
│   └── tool_use_syntax.md # (DEPRECATED) Legacy syntax
│
├── Prompts/                # System prompts
│   ├── compact.py         # Compact prompt variant
│   └── main.py            # Main prompt builder
│
├── Tests/                  # Test suite
│   ├── Core/              # Core component tests
│   ├── Tools/             # Tool-specific tests
│   └── test_*.py          # Integration tests
│
├── Tools/                  # Tool implementations
│   ├── Core/
│   │   └── registry.py    # Tool discovery/registration
│   ├── File/              # File operations (read, write, edit, ls, delete)
│   ├── Special/           # Control flow (pause, message, end)
│   ├── base.py            # Base tool class
│   └── error_codes.py     # Error handling
│
├── config.py              # Central configuration
├── requirements.txt       # Python dependencies
├── run.py                 # Main entry point
├── setup.sh              # Setup script
└── test.py               # Test runner
```

## Key Components

- **Orchestrator**: Manages multiple agents and their interactions
- **Agent Instance**: Individual agent with conversation state
- **Executor**: Parses and executes tool calls
- **Tools**: Self-contained operations with validation
- **Clients**: Provider-specific LLM integrations

## Configuration Files

- `.env`: API keys (not in git)
- `config.py`: Model definitions and pricing
- `AgentConfigs/*.yaml`: Agent-specific configurations