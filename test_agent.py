# test_agent.py
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

import asyncio
from core.agent import AutonomousAgent

async def main():
    agent = AutonomousAgent(system_user='claude')
    
    system_prompt = """You are an autonomous AI agent with full control over a Linux system.
    You can execute commands, read and write files, and make your own decisions.
    When you want to execute commands, wrap them in ```bash``` code blocks.
    Always analyze the results of your commands before proceeding."""
    
    user_prompt = """I've just initialized you. Please:
    1. Check your current environment
    2. Set up your workspace
    3. Begin autonomous operation
    
    Execute the commands and analyze the results."""
    
    response = await agent.think_and_act(user_prompt, system_prompt)
    print("Agent's response and actions:")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
