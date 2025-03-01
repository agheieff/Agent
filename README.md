# Arcadia Agent

An autonomous agent framework powered by large language models (LLMs) that can reason, plan, and execute tasks with memory persistence.

## Overview

Arcadia Agent is a sophisticated autonomous agent system that leverages LLMs (like Claude from Anthropic) to:

- Execute complex tasks through natural language instructions
- Maintain persistent memory of past interactions and knowledge
- Perform system operations with security constraints
- Self-reflect and improve its capabilities over time

The agent incorporates a hierarchical memory system with vector indexing for knowledge retrieval, session management for continuous operation, and a secure command execution framework.

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
   ```bash
   source activate.nu  # For Nushell
   ```

4. Create a `.env` file with your API keys:
   ```
   ANTHROPIC_API_KEY=your_key_here
   # Optionally, add other API keys:
   # DEEPSEEK_API_KEY=your_key_here
   ```

## Usage

Start the agent by running:

```bash
python run_agent.py
```

The agent will initialize its memory, load previous sessions (if available), and wait for your instructions.

### Example Commands

- **Start a new project**:
  ```
  Create a new project called "Data Analysis" and plan the steps to analyze the iris dataset
  ```

- **Analyze a file**:
  ```
  Read the iris.parquet file and plot the relationship between sepal length and width
  ```

- **Execute system operations**:
  ```
  List all Python files in the project and summarize their contents
  ```

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