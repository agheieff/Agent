import asyncio
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import socket
from datetime import datetime

from core.agent import AutonomousAgent

def get_model_choice() -> str:
    """Get model choice interactively."""
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
    """
    Get initial prompt by reading until the user enters
    a blank line (press Enter on an empty line to finish).
    """
    print("\nEnter your prompt (press Enter on a blank line to finish):")
    lines = []
    while True:
        try:
            line = input()
            # If the line is empty (no text), we finish collecting.
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines)

def load_and_augment_system_prompt(path: str) -> str:
    """
    Load the system prompt from file and substitute system status placeholders.
    """
    try:
        with open(path, 'r') as f:
            prompt_text = f.read()
    except FileNotFoundError:
        print(f"Warning: System prompt file not found at {path}")
        if input("Continue with empty system prompt? [y/N] ").lower() != 'y':
            sys.exit(1)
        return ""

    # Gather system info
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = socket.gethostname()
    current_directory = os.getcwd()
    run_agent_path = str(Path(__file__).resolve())
    
    # Get memory directory from config
    memory_directory = ""
    try:
        memory_config = Path(__file__).resolve().parent / "memory.config"
        if memory_config.exists():
            with open(memory_config, 'r') as f:
                memory_directory = f.read().strip()
    except:
        memory_directory = os.environ.get("AGENT_MEMORY_DIR", "")
        
    # Get projects directory from config
    projects_directory = ""
    try:
        projects_config = Path(__file__).resolve().parent / "projects.config"
        if projects_config.exists():
            with open(projects_config, 'r') as f:
                projects_directory = f.read().strip()
    except:
        projects_directory = os.environ.get("AGENT_PROJECTS_DIR", "")

    # Replace placeholders
    prompt_text = prompt_text.replace("{CURRENT_DIRECTORY}", current_directory)
    prompt_text = prompt_text.replace("{RUN_AGENT_PATH}", run_agent_path)
    prompt_text = prompt_text.replace("{CURRENT_TIME}", current_time)
    prompt_text = prompt_text.replace("{HOSTNAME}", hostname)
    prompt_text = prompt_text.replace("{MEMORY_DIRECTORY}", memory_directory)
    prompt_text = prompt_text.replace("{PROJECTS_DIRECTORY}", projects_directory)

    return prompt_text

async def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the Autonomous Agent.")
    parser.add_argument('--test', action='store_true', help="Run in test mode (no real commands executed).")
    parser.add_argument('--model', choices=['anthropic', 'deepseek'], help="Specify model directly instead of prompting.")
    parser.add_argument('--memory-dir', help="Path to memory directory (will be saved in memory.config)")
    parser.add_argument('--projects-dir', help="Path to projects directory (will be saved in projects.config)")
    args = parser.parse_args()
    test_mode = args.test
    
    # Set up directories based on configuration files
    current_dir = Path(__file__).resolve().parent
    
    # Handle memory directory setting
    if args.memory_dir:
        # Save provided memory path to config file
        memory_path = Path(args.memory_dir).resolve()
        with open(current_dir / "memory.config", 'w') as f:
            f.write(str(memory_path))
        os.environ["AGENT_MEMORY_DIR"] = str(memory_path)
        
    # Handle projects directory
    if args.projects_dir:
        # Save provided projects path to config file
        projects_path = Path(args.projects_dir).resolve()
        with open(current_dir / "projects.config", 'w') as f:
            f.write(str(projects_path))
        os.environ["AGENT_PROJECTS_DIR"] = str(projects_path)
    else:
        # Try to load from config or use default
        try:
            if (current_dir / "projects.config").exists():
                with open(current_dir / "projects.config", 'r') as f:
                    projects_path = f.read().strip()
                    if projects_path:
                        os.environ["AGENT_PROJECTS_DIR"] = projects_path
            else:
                # Use default ../Projects path
                default_projects_dir = current_dir.parent / "Projects"
                default_projects_dir.mkdir(exist_ok=True)
                os.environ["AGENT_PROJECTS_DIR"] = str(default_projects_dir)
                # Save it for future use
                with open(current_dir / "projects.config", 'w') as f:
                    f.write(str(default_projects_dir))
        except:
            # Use default projects path if config read fails
            default_projects_dir = current_dir.parent / "Projects"
            default_projects_dir.mkdir(exist_ok=True)
            os.environ["AGENT_PROJECTS_DIR"] = str(default_projects_dir)

    system_prompt_path = Path("config/system_prompt.md")
    system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if not system_prompt_path.exists():
        # Just create a placeholder file if missing
        with open(system_prompt_path, 'w') as f:
            f.write("# Default system prompt\n")

    # Get model choice from argument or interactive prompt
    model = args.model if args.model else get_model_choice()
    
    api_key = os.getenv(f"{model.upper()}_API_KEY")
    if not api_key:
        print(f"Error: {model.upper()}_API_KEY not found in environment.")
        print("Please set it in your .env file or environment variables.")
        sys.exit(1)
    
    try:
        initial_prompt = get_initial_prompt()
        
        # Handle special slash commands
        if initial_prompt.strip().startswith('/'):
            cmd = initial_prompt.strip().lower()
            if cmd == '/help':
                print("\nAvailable slash commands:")
                print("  /help     - Show this help message")
                print("  /compact  - Compact conversation history to save context space")
                print("\nExample usage: Just type '/compact' as your input to compress the conversation.")
                sys.exit(0)
        
        if not initial_prompt.strip():
            print("Error: Empty prompt.")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting initial prompt: {str(e)}")
        sys.exit(1)

    print("\nAgent Configuration:")
    print(f"- Model: {model}")
    print(f"- System Prompt: {system_prompt_path}")
    print(f"- Initial Prompt Length: {len(initial_prompt)} characters")
    print(f"- Test Mode: {'Enabled - commands will NOT actually execute' if test_mode else 'Disabled - normal execution'}")
    
    # Display feature information
    print("\nAvailable Features:")
    print("- User Input Requests: The agent can pause and ask for additional information")
    print("- Task Planning: The agent can create and track long-term tasks")
    print("- System Detection: The agent will automatically detect and adapt to your OS environment")
    print("- File Operations: Enhanced file manipulation capabilities")
    print("- API Cost Tracking: Monitors and reports token usage and costs")

    agent = None
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
        
        print("\nStarting multi-turn session...\n")

        # Load system prompt and prepend system status
        try:
            system_prompt = load_and_augment_system_prompt(str(system_prompt_path))
        except Exception as e:
            print(f"Warning: Error loading system prompt: {str(e)}")
            print("Continuing with empty system prompt...")
            system_prompt = ""

        # If test mode, add note to the system prompt as well
        if test_mode:
            system_prompt = "## TEST MODE: Commands are NOT executed.\n\n" + system_prompt

        await agent.run(initial_prompt, system_prompt)
        
    except KeyboardInterrupt:
        print("\nShutting down agent (Ctrl+C pressed)...")
    except Exception as e:
        print(f"\nError running agent: {str(e)}")
        if agent:
            try:
                # Try to save current state if possible
                agent.memory_manager.create_backup(force=True)
                print("Emergency state backup created.")
            except Exception as backup_error:
                print(f"Failed to create emergency backup: {str(backup_error)}")
        raise
    finally:
        # Display API usage summary if available
        if agent and hasattr(agent, 'llm') and hasattr(agent.llm, 'usage_history') and agent.llm.usage_history:
            print("\n=== API USAGE SUMMARY ===")
            print(f"Total API Calls: {len(agent.llm.usage_history)}")
            print(f"Total Tokens: {agent.llm.total_tokens:,}")
            print(f"  - Input Tokens: {agent.llm.total_prompt_tokens:,}")
            print(f"  - Output Tokens: {agent.llm.total_completion_tokens:,}")
            print(f"Total Cost: ${agent.llm.total_cost:.6f}")
            print("=========================")
        
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

