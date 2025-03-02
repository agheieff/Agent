"""Main entry point for the autonomous agent."""

import asyncio
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import socket
import signal
from datetime import datetime
import yaml

from Config import get_config, ConfigManager
from Core.agent import AutonomousAgent

def get_model_choice() -> str:
    """Get model choice interactively from the available models in config."""
    config = get_config()
    available_models = config.get_value("llm.models", ["anthropic", "deepseek"])
    default_model = config.get_value("llm.default_model", "deepseek")
    
    # If headless mode is enabled or only one model is available, use the default
    if config.is_headless() or len(available_models) == 1:
        print(f"\nUsing default model: {default_model}")
        return default_model
    
    while True:
        print("\nAvailable models:")
        for i, model in enumerate(available_models, 1):
            print(f"{i}. {model.title()}")
            
        try:
            choice = input(f"\nChoose a model (1-{len(available_models)}), or press Enter for default [{default_model}]: ").strip()
            if not choice:
                return default_model
                
            try:
                index = int(choice) - 1
                if 0 <= index < len(available_models):
                    return available_models[index]
                else:
                    print(f"Invalid choice. Please enter a number between 1 and {len(available_models)}.")
            except ValueError:
                print("Invalid input. Please enter a number.")
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
    Also add configuration information to the system prompt.
    """
    try:
        with open(path, 'r') as f:
            prompt_text = f.read()
    except FileNotFoundError:
        print(f"Warning: System prompt file not found at {path}")
        if input("Continue with empty system prompt? [y/N] ").lower() != 'y':
            sys.exit(1)
        return ""

    # Get configuration
    config = get_config()
    
    # Gather system info
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = socket.gethostname()
    current_directory = os.getcwd()
    run_agent_path = str(Path(__file__).resolve())
    
    # Get paths from config
    memory_directory = str(config.get_memory_path())
    projects_directory = str(config.get_projects_path())
    
    # Replace placeholders
    prompt_text = prompt_text.replace("{CURRENT_DIRECTORY}", current_directory)
    prompt_text = prompt_text.replace("{RUN_AGENT_PATH}", run_agent_path)
    prompt_text = prompt_text.replace("{CURRENT_TIME}", current_time)
    prompt_text = prompt_text.replace("{HOSTNAME}", hostname)
    prompt_text = prompt_text.replace("{MEMORY_DIRECTORY}", memory_directory)
    prompt_text = prompt_text.replace("{PROJECTS_DIRECTORY}", projects_directory)
    
    # Add configuration summary to the system prompt
    config_summary = config.get_config_summary()
    prompt_text += f"\n\n## Agent Configuration\n{config_summary}\n"
    
    # Add information about allowed/disallowed operations based on config
    security_settings = ""
    security_settings += f"\n### Security Restrictions\n"
    security_settings += f"- Restricted directories: {', '.join(config.get_value('security.restricted_dirs', []))}\n"
    security_settings += f"- Blocked commands: {', '.join(config.get_value('security.blocked_commands', []))}\n"
    security_settings += f"- Maximum allowed file size: {config.get_value('security.max_file_size', 0) // (1024 * 1024)} MB\n"
    security_settings += f"- Internet access: {'Allowed' if config.get_value('agent.allow_internet', False) else 'Disabled'}\n"
    
    prompt_text += security_settings
    
    return prompt_text

# Global variable to store the agent instance for signal handling
current_agent = None
paused_for_context = False

def handle_pause_signal(signum, frame):
    """Handle SIGTSTP (Ctrl+Z) to pause the agent for adding context"""
    global current_agent, paused_for_context
    if current_agent and not paused_for_context:
        paused_for_context = True
        asyncio.create_task(pause_for_context_input())

async def pause_for_context_input():
    """Pause the agent and collect additional context from the user"""
    global current_agent, paused_for_context

    print("\n" + "=" * 60)
    print("AGENT PAUSED FOR ADDITIONAL CONTEXT")
    print("-" * 60)
    print("Enter additional context to add to the conversation.")
    print("This will be added to the agent's last response before continuing.")
    print("Press Enter on a blank line when finished.")
    print("-" * 60)

    # Collect multi-line input
    lines = []
    while True:
        try:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break

    additional_context = "\n".join(lines)

    if additional_context.strip():
        # Add the context to the conversation with special formatting
        await current_agent.add_human_context(additional_context)
        print("=" * 60)
        print("Context added. Conversation will continue.")
        print("=" * 60 + "\n")
    else:
        print("No additional context provided. Continuing without changes.")

    paused_for_context = False

async def main():
    global current_agent
    load_dotenv()

    # Register signal handler for SIGTSTP (Ctrl+Z)
    if hasattr(signal, 'SIGTSTP'):  # Not available on Windows
        signal.signal(signal.SIGTSTP, handle_pause_signal)

    parser = argparse.ArgumentParser(description="Run the Autonomous Agent.")
    parser.add_argument('--test', action='store_true', help="Run in test mode (no real commands execution)")
    parser.add_argument('--model', choices=['anthropic', 'deepseek'], help="Specify model directly")
    parser.add_argument('--memory-dir', help="Path to memory directory")
    parser.add_argument('--projects-dir', help="Path to projects directory")
    parser.add_argument('--config', help="Path to the configuration file")
    parser.add_argument('--headless', action='store_true', help="Run in headless mode (no interactive prompts)")
    parser.add_argument('--no-internet', action='store_true', help="Disable internet access")

    args = parser.parse_args()
    
    # Initialize configuration
    config = get_config()
    
    # Update configuration from command line arguments
    if args.config:
        # Load custom configuration file
        config_path = Path(args.config).resolve()
        if config_path.exists():
            config = ConfigManager(config_path)
        else:
            print(f"Warning: Configuration file not found at {config_path}")
    
    # Override settings from command line arguments
    if args.test:
        config.set_value("agent.test_mode", True)
    
    if args.headless:
        config.set_value("agent.headless", True)
        
    if args.no_internet:
        config.set_value("agent.allow_internet", False)
    
    if args.memory_dir:
        memory_path = Path(args.memory_dir).resolve()
        memory_path.mkdir(parents=True, exist_ok=True)
        config.set_value("paths.memory_dir", str(memory_path))
        # For backward compatibility
        os.environ["AGENT_MEMORY_DIR"] = str(memory_path)

    if args.projects_dir:
        projects_path = Path(args.projects_dir).resolve()
        projects_path.mkdir(parents=True, exist_ok=True)
        config.set_value("paths.projects_dir", str(projects_path))
        # For backward compatibility
        os.environ["AGENT_PROJECTS_DIR"] = str(projects_path)
    
    # Save updated configuration
    config.save_config()
    
    # Get test mode from config
    test_mode = config.is_test_mode()

    # Use the Config/SystemPrompts directory
    system_prompt_path = Path("Config/SystemPrompts/system_prompt.md")
    system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if not system_prompt_path.exists():
        # Create a placeholder file if missing
        with open(system_prompt_path, 'w') as f:
            f.write("# Default System Prompt\n\n")
            f.write("## System Status\n")
            f.write("**Current directory**: **{CURRENT_DIRECTORY}**\n")
            f.write("**Agent script location**: **{RUN_AGENT_PATH}**\n")
            f.write("**Current time**: **{CURRENT_TIME}**\n")
            f.write("**Hostname**: **{HOSTNAME}**\n")
            f.write("**Memory directory**: **{MEMORY_DIRECTORY}**\n")
            f.write("**Projects directory**: **{PROJECTS_DIRECTORY}**\n\n")
            f.write("This is a default system prompt. Please customize it as needed.\n")

    # Get model choice from argument, config, or interactive prompt
    if args.model:
        model = args.model
        # Update config with selected model
        config.set_value("llm.default_model", model)
        config.save_config()
    else:
        model = get_model_choice()

    # Get API key from environment
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
                print("  /pause    - Pause to add additional context to the conversation")
                print("\nExample usage: Just type '/compact' as your input to compress the conversation")
                sys.exit(0)

        if not initial_prompt.strip():
            print("Error: Empty prompt.")
            sys.exit(1)
    except (RuntimeError, IOError) as e:
        print(f"Error getting initial prompt: {str(e)}")
        sys.exit(1)

    print("\nAgent Configuration:")
    print(f"- Model: {model}")
    print(f"- System Prompt: {system_prompt_path}")
    print(f"- Initial Prompt Length: {len(initial_prompt)} characters")
    print(f"- Test Mode: {'Enabled - commands will NOT actually execute' if test_mode else 'Disabled'}")

    # Display feature information
    print("\nAvailable Features:")
    print("- User Input Requests: The agent can pause and ask for additional information")
    print("- Human Context Pause: Press Ctrl+Z to pause and add context to the conversation")
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
            test_mode=config.is_test_mode()
        )

        # Store reference to agent for signal handler
        current_agent = agent

        if agent.last_session_summary:
            print("\nLast Session Summary:")
            print("-" * 40)
            print(agent.last_session_summary)
            print("-" * 40)

        print("\nStarting multi-turn session...\n")

        # Load system prompt and prepend system status
        try:
            system_prompt = load_and_augment_system_prompt(str(system_prompt_path))
        except (RuntimeError, IOError) as e:
            print(f"Warning: Error loading system prompt: {str(e)}")
            print("Continuing with empty system prompt...")
            system_prompt = ""

        # If test mode, add note to the system prompt as well
        if test_mode:
            system_prompt = "## TEST MODE: Commands are NOT executed.\n\n" + system_prompt

        await agent.run(initial_prompt, system_prompt)

    except KeyboardInterrupt:
        print("\nShutting down agent (Ctrl+C pressed)...")
    except (RuntimeError, IOError) as e:
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
    except (RuntimeError, IOError) as e:
        print(f"\nFatal error: {str(e)}")
        sys.exit(1)
