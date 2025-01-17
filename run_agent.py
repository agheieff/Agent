# run_agent.py
import asyncio
import os
from dotenv import load_dotenv
from core.agent import AutonomousAgent

async def main():
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment variable
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Please set ANTHROPIC_API_KEY in .env file")

    # Initialize agent
    agent = AutonomousAgent(api_key=api_key)
    
    # Load system prompt if it exists
    try:
        with open('memory/config/system_prompt.txt', 'r') as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print("Warning: system_prompt.txt not found, using default prompt")
        system_prompt = "You are an autonomous AI system with full system access."

    # Define initial prompt
    initial_prompt = """
    I am ready to help you with any tasks you need. I can:
    1. Execute system commands and analyze their output
    2. Process and transform data
    3. Monitor system status
    4. Perform maintenance tasks
    
    What would you like me to do?
    """
    
    # Run the agent
    try:
        await agent.run(initial_prompt, system_prompt)
    except KeyboardInterrupt:
        print("\nShutting down agent...")
    except Exception as e:
        print(f"\nError running agent: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
