# test_agent.py
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

import asyncio
from core.agent import AutonomousAgent

async def main():
    agent = AutonomousAgent()
    
    # Test basic conversation
    system_prompt = """You are an autonomous AI agent with full control over a Linux system.
    (You will be, right now this I'm just testing this code in my personal PC environment.)
    You can execute commands, read and write files, and make your own decisions.
    Respond with clear, structured thoughts about what you want to do next."""
    
    user_prompt = """I've just initialized you. What would be your first steps to:
    1. Understand your environment
    2. Set up your working space
    3. Begin autonomous operation
    
    Format your response clearly, indicating any commands you'd want to execute."""
    
    response = await agent.think(user_prompt, system_prompt)
    print("Agent's response:")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
