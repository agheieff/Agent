#!/usr/bin/env python

"""
A simple integration test for the agent
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Core.agent import AutonomousAgent
from Config import get_config

async def main():
    """Test the agent with a simple prompt"""
    # Load configuration
    config = get_config()
    
    # Set test mode and verbosity
    config.set_value("agent.test_mode", True)
    config.set_value("output.verbose_output", True)
    config.set_value("output.verbose_level", 2)  # Detailed level
    
    # Provider detection - try available providers in order
    api_key = None
    provider = None
    model = None
    
    # Try DeepSeek first
    if os.getenv("DEEPSEEK_API_KEY"):
        provider = "deepseek"
        model = "deepseek-reasoner"
        api_key = os.getenv("DEEPSEEK_API_KEY")
    # Then try Anthropic
    elif os.getenv("ANTHROPIC_API_KEY"):
        provider = "anthropic"
        model = "claude-3-7-sonnet"
        api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        print("No API keys found for any provider. Please set DEEPSEEK_API_KEY or ANTHROPIC_API_KEY.")
        return False
    
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
    test_prompt = "List the files in the current directory and explain their purpose"
    
    # System prompt - simple version
    system_prompt = "You are an AI assistant helping with coding tasks."
    
    # Run the agent
    print(f"Running agent with prompt: {test_prompt}")
    try:
        await agent.run(test_prompt, system_prompt)
        print("\n✅ Agent test completed successfully")
        return True
    except Exception as e:
        print(f"\n❌ Error running agent: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)