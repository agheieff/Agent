# run_agent.py
import asyncio
import os
import sys
import argparse
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from core.agent import AutonomousAgent

def setup_argparser() -> argparse.ArgumentParser:
    """Setup command line argument parser"""
    parser = argparse.ArgumentParser(description="Run the autonomous agent")
    parser.add_argument(
        "--prompt", "-p",
        help="Initial prompt text (if not provided, will be requested interactively)"
    )
    parser.add_argument(
        "--system-prompt", "-s",
        help="Path to system prompt file (default: memory/config/system_prompt.txt)",
        default="memory/config/system_prompt.txt"
    )
    parser.add_argument(
        "--model", "-m",
        help="LLM provider to use (default: anthropic)",
        default="anthropic",
        choices=["anthropic", "deepseek"]
    )
    return parser

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

def get_initial_prompt(args_prompt: Optional[str] = None) -> str:
    """Get initial prompt from args or user input"""
    if args_prompt:
        return args_prompt
        
    print("\nEnter your prompt (type 'EOF' on a new line to finish):")
    lines = []
    while True:
        try:
            line = input()
            if line.strip() == 'EOF':
                break
            lines.append(line)
        except EOFError:
            break
    return '\n'.join(lines)

async def main():
    # Parse command line arguments
    parser = setup_argparser()
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    
    # Get API key
    api_key = os.getenv(f"{args.model.upper()}_API_KEY")
    if not api_key:
        print(f"Error: {args.model.upper()}_API_KEY not found in environment")
        print("Please set it in your .env file or environment variables")
        sys.exit(1)

    # Load system prompt
    system_prompt_path = Path(args.system_prompt)
    if not system_prompt_path.is_absolute():
        system_prompt_path = Path.cwd() / system_prompt_path
    
    # Get initial prompt
    initial_prompt = get_initial_prompt(args.prompt)
    if not initial_prompt.strip():
        print("Error: Empty prompt")
        sys.exit(1)

    # Show configuration
    print("\nAgent Configuration:")
    print(f"- System Prompt: {system_prompt_path}")
    print(f"- Initial Prompt Length: {len(initial_prompt)} characters")
    
    try:
        # Initialize and run agent
        print("\nInitializing agent...")
        agent = AutonomousAgent(api_key=api_key, model=args.model)
        
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
