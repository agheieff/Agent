# test_agent.py
import os
import sys
import asyncio
import logging
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from core.agent import AutonomousAgent

async def main():
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Initialize agent
    api_key = os.getenv('ANTHROPIC_API_KEY')
    agent = AutonomousAgent(api_key=api_key, system_user='claude')
    
    # Start a new conversation
    conversation_id = agent.start_conversation()
    logger.info(f"Started conversation: {conversation_id}")
    
    system_prompt = """You are an autonomous AI agent with full control over a Linux system.
    You can execute commands, read and write files, and make your own decisions.
    When you want to execute commands, wrap them in ```bash``` code blocks.
    Always analyze the results of your commands before proceeding.
    Be thorough in your analysis and planning."""
    
    user_prompt = """I've just initialized you. Please:
    1. Check your current environment (OS, user, permissions)
    2. Create a workspace directory
    3. Set up basic monitoring (disk space, memory, CPU usage)
    4. Report back with your findings
    
    Execute the commands and analyze the results carefully."""
    
    try:
        # Get initial response and actions
        response = await agent.think_and_act(user_prompt, system_prompt)
        print("\nInitial response and actions:")
        print(response)
        
        # Let's test multi-command handling
        follow_up_prompt = """Great! Now please:
        1. Create a simple test file in the workspace
        2. Monitor system resources for 30 seconds
        3. Summarize the findings"""
        
        response = await agent.think_and_act(follow_up_prompt, system_prompt)
        print("\nFollow-up response and actions:")
        print(response)
        
        # Analyze the conversation
        print("\nAnalyzing conversation history...")
        analysis = await agent.analyze_conversation()
        print(analysis)
        
    except Exception as e:
        logger.error(f"Error during execution: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
