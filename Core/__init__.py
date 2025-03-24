"""
Core package for the Agent.

This package provides the core functionality of the agent system:
- AgentRunner: Main class for running the agent
- ModelInterface: Abstract interface for interacting with language models
- utils: Utility functions for the agent
"""

from Core.agent_runner import AgentRunner, AgentConversation, ToolRegistry
from Core.model_interface import ModelInterface, get_model_interface
from Core.utils import get_multiline_input

__all__ = [
    'AgentRunner',
    'AgentConversation',
    'ToolRegistry',
    'ModelInterface',
    'get_model_interface',
    'get_multiline_input',
]
