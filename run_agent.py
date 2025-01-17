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

    # Load system prompt and initial prompt
    try:
        with open('memory/config/system_prompt.txt', 'r') as f:
            system_prompt = f.read().strip()
    except FileNotFoundError:
        print("Warning: system_prompt.txt not found, using empty system prompt")
        system_prompt = ""

    try:
        with open('memory/config/initial_prompt.txt', 'r') as f:
            initial_prompt = f.read().strip()
    except FileNotFoundError:
        raise ValueError("initial_prompt.txt is required but was not found in memory/config/")
    
    # Run the agent
    try:
        agent = AutonomousAgent(api_key=api_key)
        await agent.run(initial_prompt, system_prompt)
    except KeyboardInterrupt:
        print("\nShutting down agent...")
    except Exception as e:
        print(f"\nError running agent: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
