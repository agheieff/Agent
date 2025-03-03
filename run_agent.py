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
from typing import Dict, List

from Config import get_config, ConfigManager
from Core.agent import AutonomousAgent

def get_available_model_providers() -> Dict[str, Dict[str, List[str]]]:
    """Get available model providers and their models based on available API keys."""
    # Define mapping of provider names to environment variable prefixes and available models
    provider_config = {
        "anthropic": {
            "env_prefix": "ANTHROPIC",
            "models": ["claude-3-7-sonnet"]
        },
        "deepseek": {
            "env_prefix": "DEEPSEEK",
            "models": ["deepseek-reasoner", "deepseek-reasoner-tools", "deepseek-chat"]
        },
        # Add more providers as needed
    }
    
    available_providers = {}
    for provider, config in provider_config.items():
        api_key = os.getenv(f"{config['env_prefix']}_API_KEY")
        if api_key:
            available_providers[provider] = config
    
    return available_providers

def get_model_choice() -> Dict[str, str]:
    """
    Get model choice interactively from available models.
    Returns a dict with 'provider' and 'model' keys.
    """
    config = get_config()
    available_providers = get_available_model_providers()
    
    # No API keys available
    if not available_providers:
        print("\n❌ No API keys found for any supported model providers.")
        print("Please set at least one of the following environment variables:")
        print("  - ANTHROPIC_API_KEY for Claude models")
        print("  - DEEPSEEK_API_KEY for DeepSeek models")
        print("\nYou can add these to your .env file or environment variables.")
        sys.exit(1)
    
    # Get default provider and model from config
    default_provider = config.get_value("llm.default_provider", next(iter(available_providers.keys())))
    default_model = config.get_value("llm.default_model", available_providers.get(default_provider, {"models": [""]})["models"][0])
    
    # If headless mode is enabled or only one provider is available, use the default
    if config.is_headless() or len(available_providers) == 1:
        provider = default_provider
        provider_models = available_providers[provider]["models"]
        model = default_model if default_model in provider_models else provider_models[0]
        print(f"\nUsing {provider.title()} model: {model}")
        return {"provider": provider, "model": model}
    
    # Step 1: Choose provider
    selected_provider = None
    while not selected_provider:
        print("\nAvailable model providers:")
        providers = list(available_providers.keys())
        for i, provider in enumerate(providers, 1):
            if provider == default_provider:
                print(f"{i}. {provider.title()} [default]")
            else:
                print(f"{i}. {provider.title()}")
            
        try:
            choice = input(f"\nChoose a provider (1-{len(providers)}), or press Enter for default: ").strip()
            if not choice:
                selected_provider = default_provider
            else:
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(providers):
                        selected_provider = providers[index]
                    else:
                        print(f"Invalid choice. Please enter a number between 1 and {len(providers)}.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        except EOFError:
            sys.exit(0)
    
    # Step 2: Choose model from the selected provider
    provider_models = available_providers[selected_provider]["models"]
    default_model_for_provider = default_model if default_model in provider_models else provider_models[0]
    
    # If only one model or in headless mode, use the default
    if len(provider_models) == 1 or config.is_headless():
        return {"provider": selected_provider, "model": provider_models[0]}
    
    selected_model = None
    while not selected_model:
        print(f"\nAvailable {selected_provider.title()} models:")
        for i, model in enumerate(provider_models, 1):
            if model == default_model_for_provider:
                print(f"{i}. {model} [default]")
            else:
                print(f"{i}. {model}")
            
        try:
            choice = input(f"\nChoose a model (1-{len(provider_models)}), or press Enter for default: ").strip()
            if not choice:
                selected_model = default_model_for_provider
            else:
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(provider_models):
                        selected_model = provider_models[index]
                    else:
                        print(f"Invalid choice. Please enter a number between 1 and {len(provider_models)}.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        except EOFError:
            sys.exit(0)
    
    return {"provider": selected_provider, "model": selected_model}

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
    parser.add_argument('--provider', choices=['anthropic', 'deepseek'], help="Specify model provider directly")
    parser.add_argument('--model', help="Specify model name directly (e.g., claude-3-sonnet, deepseek-reasoner)")
    parser.add_argument('--memory-dir', help="Path to memory directory")
    parser.add_argument('--projects-dir', help="Path to projects directory")
    parser.add_argument('--config', help="Path to the configuration file")
    parser.add_argument('--headless', action='store_true', help="Run in headless mode (no interactive prompts)")
    parser.add_argument('--no-internet', action='store_true', help="Disable internet access")
    parser.add_argument('--aot', action='store_true', help="Enable Atom of Thoughts reasoning")
    parser.add_argument('--aot-config', type=str, help="Path to Atom of Thoughts configuration file")

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
        
    # Add AoT configuration
    if args.aot:
        config.set_value("aot.enabled", True)
        config.set_value("agent.enable_aot", True)
        if args.aot_config:
            with open(args.aot_config, 'r') as f:
                aot_config = yaml.safe_load(f)
                for key, value in aot_config.items():
                    config.set_value(f"aot.{key}", value)
    
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

    # Use the Config/SystemPrompts directory with a standard absolute path
    system_prompt_path = Path(__file__).parent / "Config" / "SystemPrompts" / "system_prompt.md"
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
    available_providers = get_available_model_providers()
    
    if not available_providers:
        print(f"Error: No API keys found for any providers.")
        print("Please set either ANTHROPIC_API_KEY or DEEPSEEK_API_KEY in your environment.")
        sys.exit(1)
    
    if args.provider or args.model:
        # If provider is specified via CLI
        if args.provider:
            provider = args.provider.lower()
            # Check if the specified provider has an API key
            if provider not in available_providers:
                print(f"Error: No API key found for provider '{provider}'.")
                print(f"Please set {provider.upper()}_API_KEY in your environment.")
                sys.exit(1)
            
            # If model is also specified, check that it's valid for the provider
            if args.model:
                model = args.model
                if model not in available_providers[provider]["models"]:
                    print(f"Warning: Model '{model}' is not in the standard models for {provider}.")
                    print(f"Using it anyway, but it might not work as expected.")
            else:
                # If only provider specified, use default model for that provider
                model = available_providers[provider]["models"][0]
        else:
            # If only model is specified, try to find a matching provider
            model = args.model
            provider_found = False
            
            for provider_name, config in available_providers.items():
                if model in config["models"]:
                    provider = provider_name
                    provider_found = True
                    break
            
            if not provider_found:
                # If no matching provider, use the first available provider
                provider = next(iter(available_providers.keys()))
                print(f"Warning: Could not determine provider for model '{model}'.")
                print(f"Using provider '{provider}', but it might not work as expected.")
        
        model_choice = {"provider": provider, "model": model}
        
        # Update config with selected model and provider
        config.set_value("llm.default_provider", provider)
        config.set_value("llm.default_model", model)
        config.save_config()
    else:
        # Interactive model selection
        model_choice = get_model_choice()

    # Get API key from environment based on selected provider
    provider = model_choice["provider"]
    model = model_choice["model"]
    env_prefix = {"anthropic": "ANTHROPIC", "deepseek": "DEEPSEEK"}.get(provider, provider.upper())
    api_key = os.getenv(f"{env_prefix}_API_KEY")
    
    if not api_key:
        print(f"Error: {env_prefix}_API_KEY not found in environment.")
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
    print(f"- Provider: {provider.title()}")
    print(f"- Model: {model}")
    print(f"- System Prompt: {system_prompt_path}")
    if provider == "deepseek":
        print(f"  (Note: For DeepSeek models, system prompt is combined with the user prompt)")
    print(f"- Initial Prompt Length: {len(initial_prompt)} characters")
    print(f"- Test Mode: {'Enabled - commands will NOT actually execute' if test_mode else 'Disabled'}")
    print(f"- Atom of Thoughts: {'Enabled' if config.get_value('aot.enabled', False) else 'Disabled'}")

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
            provider=provider,
            test_mode=config.is_test_mode(),
            config=config.get_all()
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
