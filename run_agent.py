# run_agent.py
import asyncio
import os
import socket
from dotenv import load_dotenv
from core.agent import AutonomousAgent

def get_local_ip():
    """Get the local IP address"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

async def main():
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment variable
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Please set ANTHROPIC_API_KEY in .env file")

    # Get local IP
    local_ip = get_local_ip()
    
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
    print(f"\nStarting web server...")
    await agent.setup_web_server(host='0.0.0.0', port=8080)
    print(f"Web server running at: http://{local_ip}:8080")
    print(f"Available endpoints:")
    print(f"  - Send commands: POST http://{local_ip}:8080/message")
    print(f"  - Check status: GET  http://{local_ip}:8080/status")
    
    # Initialize agent with system prompt
    print("\nInitializing agent...")
    conv_id, response = await agent.initialize_with_prompt(system_prompt)
    print(f"Agent initialized with conversation ID: {conv_id}")
    print("Initial response:", response)
    
    # Keep the script running
    try:
        print(f"\nAgent is running and accessible on local network")
        print("Example usage:")
        print(f"curl -X POST http://{local_ip}:8080/message \\")
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"message": "Check system status"}\'')
        print("\nPress Ctrl+C to stop")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down agent...")

if __name__ == "__main__":
    asyncio.run(main())
