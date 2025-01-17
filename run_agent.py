# run_agent.py
import asyncio
import os
from core.agent import AutonomousAgent

async def main():
    # Get API key from environment variable
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Please set ANTHROPIC_API_KEY environment variable")

    # Initialize agent
    agent = AutonomousAgent(api_key=api_key, system_user='claude')
    
    # Start web server
    await agent.setup_web_server(port=8080)
    
    # Initialize with initial prompt
    system_prompt = """You're a fully autonomous AI agent in full control of this Arch Linux machine. 
    You can execute commands as a user called "claude" with sudo access. You should be proactive 
    and take initiative to improve and maintain the system."""
    
    conversation_id, response = await agent.initialize_with_prompt(system_prompt)
    print(f"Agent initialized with conversation ID: {conversation_id}")
    print(f"Initial response: {response}")
    
    # Keep the script running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down agent...")

if __name__ == "__main__":
    asyncio.run(main())
