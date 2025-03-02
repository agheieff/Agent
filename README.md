# Arcadia Agent

An autonomous agent framework powered by large language models (LLMs) that can reason, plan, and execute tasks with memory persistence.

## Overview

Arcadia Agent is a sophisticated autonomous agent system that leverages LLMs (like Claude from Anthropic) to:

- Execute complex tasks through natural language instructions
- Maintain persistent memory of past interactions and knowledge
- Perform system operations with security constraints
- Self-reflect and improve its capabilities over time

The agent incorporates a hierarchical memory system with vector indexing for knowledge retrieval, session management for continuous operation, and a secure command execution framework.

## Project Organization

The system is structured into three main directories:

1. **Agent** - Contains all code related to the agent functionality
   - Core modules
   - Configuration
   - System prompts

2. **AgentMemory** - Storage for all memory and persistent data
   - Documents
   - Conversations
   - Working memory 
   - Vector indices
   - Session history

3. **Projects** - Working directory for individual projects
   - Each project should be contained in its own subdirectory
   - Code you're working on stays separate from agent code

### Directory Structure

```
/Arcadia/
├── Agent/               # Agent code and functionality
│   ├── core/            # Core agent modules
│   ├── config/          # Configuration files 
│   └── run_agent.py     # Agent entry point
│
├── AgentMemory/         # Persistent memory storage
│   ├── documents/       # Stored documents
│   ├── conversations/   # Stored conversations
│   ├── vector_index/    # Vector embeddings for search
│   ├── tasks/           # Task tracking
│   └── ...              # Other memory components
│
└── Projects/            # Project working directories
    ├── Project1/        # Individual project
    ├── Project2/        # Another project
    └── ...
```

## Features

- **Intelligent Task Execution**: Break down complex tasks into manageable steps and execute them
- **Memory Management**: Store and retrieve information using vector embeddings and knowledge graphs
- **Multi-Session Support**: Maintain context across multiple interactions
- **Security Controls**: Execute commands within a configurable security framework
- **File Operations**: Create, read, modify, and organize files
- **Self-Improvement**: Learn from past experiences and refine reasoning

## Installation

### Prerequisites
- Python 3.12 or higher
- (Optional) NVIDIA GPU with CUDA support
- (Optional) AMD GPU with ROCm support

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/arcadia-agent.git
   cd arcadia-agent
   ```

2. Run the setup script:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

   The setup script will:
   - Detect your hardware (CPU, NVIDIA GPU, or AMD GPU)
   - Install appropriate dependencies
   - Configure the virtual environment
   - Clean up unnecessary files

3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate  # For Bash
   ```
   or

4. Create a `.env` file with your API keys:
   ```
   ANTHROPIC_API_KEY=your_key_here
   # Optionally, add other API keys:
   # DEEPSEEK_API_KEY=your_key_here
   ```

## Usage

### Running the Agent

Start the agent by running:

```bash
python run_agent.py [options]
```

The agent will initialize its memory, load previous sessions (if available), and wait for your instructions.

### Command Line Options

```
--model [anthropic|deepseek]     # Specify the LLM model to use
--memory-dir PATH                # Path to memory directory (default: ../AgentMemory)
--projects-dir PATH              # Path to projects directory (default: ../Projects)
--test                           # Run in test mode (no commands executed)
```

### Memory & Projects Configuration

The agent uses configuration files to manage its memory and projects locations:

- `memory.config` - Contains the path to the memory directory
- `projects.config` - Contains the path to the projects directory

These configs are automatically managed by the agent. When you run the agent with specific paths:

```bash
python run_agent.py --memory-dir /path/to/memory --projects-dir /path/to/projects
```

The agent will update its configuration files accordingly.

The agent can also use environment variables as fallback:
- `AGENT_MEMORY_DIR` - Path to the memory directory
- `AGENT_PROJECTS_DIR` - Path to the projects directory

### Memory Persistence

The memory system is designed to persist between agent restarts. You can safely:

1. Stop the agent
2. Update agent code
3. Restart the agent

Memory and project data will be preserved.

### Example Commands

- **Start a new project**:
  ```
  Create a new project in the Projects directory called "Data Analysis" and plan the steps to analyze the iris dataset
  ```

- **Analyze a file**:
  ```
  Read the iris.parquet file from the Projects/Data Analysis directory and plot the relationship between sepal length and width
  ```

- **Execute system operations**:
  ```
  List all Python files in the current project and summarize their contents
  ```

### Best Practices

1. **Keep projects in the Projects directory** - All project files should be created and managed there
2. **Don't modify agent code** unless you're upgrading the agent itself
3. **Back up the AgentMemory directory** periodically to prevent data loss

## Configuration

Configuration files are stored in the `config/` directory:

- `system_prompt.md`: Contains the core system prompt for the agent
- Additional configuration options can be modified directly in the `config/` directory files

## Development

To contribute to the project:

1. Create a new branch for your feature
2. Make your changes
3. Run tests: `pytest`
4. Submit a pull request

## License

[MIT License](LICENSE) - See license file for details.

## Acknowledgements

This project uses various open-source libraries, including:
- Anthropic's Claude API for language model capabilities
- FAISS for vector similarity search
- Sentence Transformers for text embeddings
- NetworkX for knowledge graph representation
