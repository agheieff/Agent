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
    agent = AutonomousAgent(api_key=api_key, system_user='claude')
    
    # Read system prompt
    try:
        with open('memory/config/system_prompt.txt', 'r') as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print("Warning: system_prompt.txt not found, using default prompt")
        system_prompt = "You are an autonomous AI system with full system access."

    # Start web server with network access
    print("Starting web server...")
    await agent.setup_web_server(host='0.0.0.0', port=8080)  # Allow external access
    print("Web server running on port 8080")
    
    # Initialize agent with system prompt
    print("Initializing agent...")
    conv_id, response = await agent.initialize_with_prompt(system_prompt)
    print(f"Agent initialized with conversation ID: {conv_id}")
    print("Initial response:", response)
    
    # Keep the script running
    try:
        print("\nAgent is running and accessible on local network")
        print("To interact, send POST requests to: http://<your-ip>:8080/message")
        print("Press Ctrl+C to stop")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down agent...")

if __name__ == "__main__":
    asyncio.run(main())
