#\!/usr/bin/env python

"""
A simpler test runner for the agent that avoids terminal I/O issues
and allows better automation of tests.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent))

from Core.agent import AutonomousAgent
from Config import get_config

async def main():
    # Load configuration
    config = get_config()
    
    # Set test mode and verbosity
    config.set_value("agent.test_mode", True)
    config.set_value("output.verbose_output", True)
    config.set_value("output.verbose_level", 2)  # Detailed level
    
    # Provider and model selection
    provider = "deepseek"
    model = "deepseek-reasoner"
    
    # Get API key from environment
    env_prefix = {"anthropic": "ANTHROPIC", "deepseek": "DEEPSEEK"}.get(provider, provider.upper())
    api_key = os.getenv(f"{env_prefix}_API_KEY")
    
    if not api_key:
        print(f"Error: {env_prefix}_API_KEY not found in environment")
        sys.exit(1)
    
    # Create agent
    print(f"Creating agent with {provider.title()} model: {model}")
    agent = AutonomousAgent(
        api_key=api_key,
        model=model,
        provider=provider,
        test_mode=True,
        config=config.to_dict()
    )
    
    # Test prompt
    test_prompt = "List the files in the project directory and explain their purpose"
    
    # System prompt - simple version
    system_prompt = "You are an AI assistant helping with coding tasks."
    
    # Run the agent
    print(f"Running agent with prompt: {test_prompt}")
    try:
        await agent.run(test_prompt, system_prompt)
    except Exception as e:
        print(f"Error running agent: {e}")
    
    print("Test completed")

if __name__ == "__main__":
    asyncio.run(main())
