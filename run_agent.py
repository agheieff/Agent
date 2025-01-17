# run_agent.py
import asyncio
import os
import socket
from dotenv import load_dotenv
from core.agent import AutonomousAgent

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return '127.0.0.1'

async def main():
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment variable
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Please set ANTHROPIC_API_KEY in .env file")

    # Get local IP address
    local_ip = get_local_ip()
    port = 8080

    print("\n" + "="*50)
    print("Starting AI Agent System")
    print("="*50)
    print(f"\nWeb Interface URLs:")
    print(f"Local machine: http://localhost:{port}")
    print(f"Other devices: http://{local_ip}:{port}")
    print("\nYou can access the dashboard from any device on your local network")
    print("="*50 + "\n")

    # Initialize agent without specific system user
    agent = AutonomousAgent(api_key=api_key)
    
    # Initialize with system prompt
    try:
        with open('memory/config/system_prompt.txt', 'r') as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print("Warning: system_prompt.txt not found, using default prompt")
        system_prompt = "You are an autonomous AI system with full system access."

    # Initialize and run agent
    print("Initializing agent...")
    conv_id, response = await agent.initialize_with_prompt(system_prompt)
    print(f"Agent initialized with conversation ID: {conv_id}")
    print(f"Initial response: {response}")
    
    try:
        await agent.run(host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        print("\nShutting down agent...")
    except Exception as e:
        print(f"\nError running agent: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
