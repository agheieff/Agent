import asyncio
import os
import sys
import argparse
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from core.agent import AutonomousAgent

def get_model_choice() -> str:
    """Get model choice interactively"""
    while True:
        print("\nAvailable models:")
        print("1. Anthropic Claude")
        print("2. DeepSeek")
        try:
            choice = input("\nChoose a model (1-2): ").strip()
            if choice == "1":
                return "anthropic"
            elif choice == "2":
                return "deepseek"
            else:
                print("Invalid choice. Please enter 1 or 2.")
        except EOFError:
            sys.exit(0)

def get_initial_prompt() -> str:
    """Get initial prompt with double-return detection"""
    print("\nEnter your prompt (press Enter twice to finish):")
    lines = []
    last_line_empty = False
    
    while True:
        try:
            line = input()
            if not line and last_line_empty:  # Two empty lines in a row
                break
            last_line_empty = not line
            lines.append(line)
        except EOFError:
            break
    
    # Remove the last empty line if it exists
    if lines and not lines[-1]:
        lines.pop()
    
    return '\n'.join(lines)

def load_system_prompt(path: str) -> str:
    """Load system prompt from file"""
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Warning: System prompt file not found at {path}")
        if input("Continue with empty system prompt? [y/N] ").lower() != 'y':
            sys.exit(1)
        return ""

async def main():
    system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if not system_prompt_path.exists():
        with open(system_prompt_path, 'w') as f:
            f.write(Path("system_prompt.txt").read_text())
    # Load environment variables
    load_dotenv()
    
    # Get model choice interactively
    model = get_model_choice()
    
    # Get API key
    api_key = os.getenv(f"{model.upper()}_API_KEY")
    if not api_key:
        print(f"Error: {model.upper()}_API_KEY not found in environment")
        print("Please set it in your .env file or environment variables")
        sys.exit(1)

    # Load system prompt
    system_prompt_path = Path("memory/config/system_prompt.txt")
    if not system_prompt_path.is_absolute():
        system_prompt_path = Path.cwd() / system_prompt_path
    
    # Get initial prompt
    initial_prompt = get_initial_prompt()
    if not initial_prompt.strip():
        print("Error: Empty prompt")
        sys.exit(1)

    # Show configuration
    print("\nAgent Configuration:")
    print(f"- Model: {model}")
    print(f"- System Prompt: {system_prompt_path}")
    print(f"- Initial Prompt Length: {len(initial_prompt)} characters")
    
    try:
        # Initialize and run agent
        print("\nInitializing agent...")
        agent = AutonomousAgent(api_key=api_key, model=model)
        
        # Show last session summary if available
        if agent.last_session_summary:
            print("\nLast Session Summary:")
            print("-" * 40)
            print(agent.last_session_summary)
            print("-" * 40)
        
        print("\nStarting agent...\n")
        system_prompt = load_system_prompt(str(system_prompt_path))
        await agent.run(initial_prompt, system_prompt)
        
    except KeyboardInterrupt:
        print("\nShutting down agent (Ctrl+C pressed)...")
    except Exception as e:
        print(f"\nError running agent: {str(e)}")
        raise
    finally:
        print("\nAgent session ended")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        sys.exit(1)
