# Directory Structure

Agent/
├── Clients/ # API client implementations
│ ├── API/ # Provider-specific clients
│ │ ├── openai.py # OpenAI client
│ │ ├── anthropic.py # Anthropic client
│ │ └── ... # Other providers
│ └── base.py # Base client class
│
├── Core/ # Core agent functionality
│ ├── agent_runner.py # Main agent class (replaces ModelInterface)
│ └── executor.py # Tool execution system
│
├── Tools/ # All available tools
│ ├── File/ # File operations
│ ├── Network/ # Network tools
│ └── Special/ # Agent control tools
│
├── Tests/ # Test cases
└── README.md # Main documentation
