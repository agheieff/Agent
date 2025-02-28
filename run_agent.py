import asyncio
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

from core.agent import AutonomousAgent

def get_model_choice() -> str:
    """Get model choice interactively"""
    while True:
        print("\nAvailable models:")
        print("1. Anthropic Claude")
        print("2. DeepSeek-Reasoner")
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
            if not line and last_line_empty:
                break
            last_line_empty = not line
            lines.append(line)
        except EOFError:
            break
    if lines and not lines[-1]:
        lines.pop()
    return '\n'.join(lines)

def load_system_prompt(path: str) -> str:
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Warning: System prompt file not found at {path}")
        if input("Continue with empty system prompt? [y/N] ").lower() != 'y':
            sys.exit(1)
        return ""

async def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the Autonomous Agent.")
    parser.add_argument('--test', action='store_true', help="Run in test mode (no real commands executed).")
    args = parser.parse_args()
    test_mode = args.test

    system_prompt_path = Path("config/system_prompt.md")
    system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if not system_prompt_path.exists():
        with open(system_prompt_path, 'w') as f:
            f.write("# Default system prompt\n")

    model = get_model_choice()
    
    api_key = os.getenv(f"{model.upper()}_API_KEY")
    if not api_key:
        print(f"Error: {model.upper()}_API_KEY not found in environment.")
        print("Please set it in your .env file or environment variables.")
        sys.exit(1)
    
    initial_prompt = get_initial_prompt()
    if not initial_prompt.strip():
        print("Error: Empty prompt.")
        sys.exit(1)

    print("\nAgent Configuration:")
    print(f"- Model: {model}")
    print(f"- System Prompt: {system_prompt_path}")
    print(f"- Initial Prompt Length: {len(initial_prompt)} characters")
    print(f"- Test Mode: {'Enabled' if test_mode else 'Disabled'}")

    try:
        print("\nInitializing agent...")
        agent = AutonomousAgent(
            api_key=api_key,
            model=model,
            test_mode=test_mode
        )
        
        if agent.last_session_summary:
            print("\nLast Session Summary:")
            print("-" * 40)
            print(agent.last_session_summary)
            print("-" * 40)
        
        print("\nStarting agent...\n")
        system_prompt = load_system_prompt(str(system_prompt_path))

        # If test mode, add note to the system prompt as well
        if test_mode:
            system_prompt = "## TEST MODE: Commands are NOT executed.\n\n" + system_prompt

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
