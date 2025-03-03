# Arcadia Agent

An autonomous agent framework powered by large language models (LLMs) that can reason, plan, and execute tasks with memory persistence.

## Overview

Arcadia Agent is a sophisticated autonomous agent system that leverages LLMs (like Claude from Anthropic, DeepSeek, or OpenAI GPT) to:

- Execute complex tasks through natural language instructions
- Maintain persistent memory of past interactions and knowledge
- Perform system operations with security constraints
- Self-reflect and improve its capabilities over time

The agent incorporates a hierarchical memory system with vector indexing for knowledge retrieval, session management for continuous operation, and a secure command execution framework.

## Project Organization

The system is structured into multiple directories:

- **Clients/**: Contains client classes for various LLM providers (Anthropic, DeepSeek, OpenAI, etc.)
- **Config/**: Handles configuration loading and defaults
- **Core/**: Core agent code (agent logic, parsing, composer, etc.)
- **Memory/**: In practice, your agent's memory is stored here (subdirectories like `Data`, `Vector`, etc.)
- **Tools/**: A collection of tools the agent can invoke (File editing, Internet/curl, Telegram, System commands, etc.)
- **Output/**: Manages output formatting
- **Prompts/**: Contains system prompt generation and specialized prompts (like `compact.py`)

Example directory structure:

./
 ├── Clients/
 ├── Config/
 ├── Core/
 ├── Memory/
 ├── Output/
 ├── Prompts/
 ├── Tools/
 │ ├── File/
 │ ├── Internet/
 │ ├── System/
 │ └── Telegram/
 ├── README.md
 ├── run.py
 └── setup.sh
