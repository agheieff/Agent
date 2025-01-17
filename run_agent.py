import asyncio
from core.agent import AutonomousAgent

async def main():
    agent = AutonomousAgent(api_key="your-api-key")
    # Initialize the agent with your system prompt
    conv_id, response = await agent.initialize_with_prompt("Your system prompt")
    print(f"Agent initialized with conversation ID: {conv_id}")
    print(f"Initial response: {response}")
    
    # Run the agent with web interface
    await agent.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    asyncio.run(main())
