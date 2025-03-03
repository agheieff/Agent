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

from Config import config, Config
from Core.agent import AutonomousAgent

INITIAL_PROMPT_HISTORY_FILE = '~/.agent_prompt_history'
CONTEXT_HISTORY_FILE = '~/.agent_context_history'

def get_available_model_providers() -> Dict[str, Dict[str, List[str]]]:
    provider_config = {
        "anthropic": {
            "env_prefix": "ANTHROPIC",
            "models": ["claude-3-7-sonnet"]
        },
        "deepseek": {
            "env_prefix": "DEEPSEEK",
            "models": ["deepseek-reasoner", "deepseek-chat"]
        },
    }

    available_providers = {}
    for provider, config in provider_config.items():
        api_key = os.getenv(f"{config['env_prefix']}_API_KEY")
        if api_key:
            available_providers[provider] = config

    return available_providers

def get_model_choice() -> Dict[str, str]:
    config = get_config()
    available_providers = get_available_model_providers()

    if not available_providers:
        print("\n No API keys found for any supported model providers.")
        print("Please set at least one of the following environment variables:")
        print("  - ANTHROPIC_API_KEY for Claude models")
        print("  - DEEPSEEK_API_KEY for DeepSeek models")
        print("\nYou can add these to your .env file or environment variables.")
        sys.exit(1)

    default_provider = config.get_value("llm.default_provider", next(iter(available_providers.keys())))
    default_model = config.get_value("llm.default_model", available_providers.get(default_provider, {"models": [""]})["models"][0])

    if config.is_headless() or len(available_providers) == 1:
        provider = default_provider
        provider_models = available_providers[provider]["models"]
        model = default_model if default_model in provider_models else provider_models[0]
        print(f"\nUsing {provider.title()} model: {model}")
        return {"provider": provider, "model": model}

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


    provider_models = available_providers[selected_provider]["models"]
    default_model_for_provider = default_model if default_model in provider_models else provider_models[0]

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
    try:
        import readline

        history_file = os.path.expanduser(INITIAL_PROMPT_HISTORY_FILE)
        try:
            readline.read_history_file(history_file)
            readline.set_history_length(1000)
        except FileNotFoundError:
            pass

        import atexit
        atexit.register(readline.write_history_file, history_file)
    except (ImportError, ModuleNotFoundError):
        pass

    print("\nEnter your prompt (press Enter on a blank line to finish):")
    lines = []
    while True:
        try:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines)

def load_and_augment_system_prompt(path: str, last_session_summary: str = None) -> str:
    try:
        with open(path, 'r') as f:
            prompt_text = f.read()
    except FileNotFoundError:
        print(f"Warning: System prompt file not found at {path}")
        if input("Continue with empty system prompt? [y/N] ").lower() != 'y':
            sys.exit(1)
        return ""

    config = get_config()

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = socket.gethostname()
    current_directory = os.getcwd()
    run_agent_path = str(Path(__file__).resolve())

    memory_directory = str(config.get_memory_path())
    projects_directory = str(config.get_projects_path())

    prompt_text = prompt_text.replace("{CURRENT_DIRECTORY}", current_directory)
    prompt_text = prompt_text.replace("{RUN_AGENT_PATH}", run_agent_path)
    prompt_text = prompt_text.replace("{CURRENT_TIME}", current_time)
    prompt_text = prompt_text.replace("{HOSTNAME}", hostname)
    prompt_text = prompt_text.replace("{MEMORY_DIRECTORY}", memory_directory)
    prompt_text = prompt_text.replace("{PROJECTS_DIRECTORY}", projects_directory)

    config_summary = config.get_config_summary()
    prompt_text += f"\n\n## Agent Configuration\n{config_summary}\n"

    security_settings = ""
    security_settings += f"\n### Security Restrictions\n"
    security_settings += f"- Restricted directories: {', '.join(config.get_value('security.restricted_dirs', []))}\n"
    security_settings += f"- Blocked commands: {', '.join(config.get_value('security.blocked_commands', []))}\n"
    security_settings += f"- Maximum allowed file size: {config.get_value('security.max_file_size', 0) // (1024 * 1024)} MB\n"
    security_settings += f"- Internet access: {'Allowed' if config.get_value('agent.allow_internet', False) else 'Disabled'}\n"

    prompt_text += security_settings

    if last_session_summary and last_session_summary.strip():
        prompt_text += f"\n\n## Previous Session Summary\n{last_session_summary}\n"

    return prompt_text

current_agent = None
paused_for_context = False

def handle_pause_signal(signum, frame):
    global current_agent, paused_for_context
    if current_agent and not paused_for_context:
        paused_for_context = True
        asyncio.create_task(pause_for_context_input())

async def pause_for_context_input():
    global current_agent, paused_for_context

    print("\n" + "=" * 60)
    print("AGENT PAUSED FOR ADDITIONAL CONTEXT")
    print("-" * 60)

    try:
        import readline

        history_file = os.path.expanduser(CONTEXT_HISTORY_FILE)
        try:
            readline.read_history_file(history_file)
            readline.set_history_length(1000)
        except FileNotFoundError:
            pass

        import atexit
        if not hasattr(pause_for_context_input, "_readline_initialized"):
            atexit.register(readline.write_history_file, history_file)
            pause_for_context_input._readline_initialized = True
    except (ImportError, ModuleNotFoundError):
        pass

    lines = []
    while True:
        try:
            line = input("[Message] > ")
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break

    additional_context = "\n".join(lines)

    if additional_context.strip():
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

    if hasattr(signal, 'SIGTSTP'):
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

    mode_group = parser.add_argument_group('Operation Mode Options')
    mode_group.add_argument('--non-autonomous', action='store_true',
                        help="Disable autonomous mode - ask for user input after each step")
    mode_group.add_argument('--autonomous', action='store_true',
                        help="Enable autonomous mode (default) - run without asking for input between steps")

    verbosity_group = parser.add_argument_group('Verbosity Options')
    verbosity_group.add_argument('--verbose', '-v', action='count', default=0, 
                         help="Increase output verbosity (can use multiple times, e.g. -vv)")
    verbosity_group.add_argument('--quiet', '-q', action='store_true', 
                         help="Minimize output verbosity")

    args = parser.parse_args()

    config = get_config()

    if args.config:
        config_path = Path(args.config).resolve()
        if config_path.exists():
            config = ConfigManager(config_path)
        else:
            print(f"Warning: Configuration file not found at {config_path}")

    if args.test:
        config.set_value("agent.test_mode", True)

    if args.headless:
        config.set_value("agent.headless", True)

    if args.no_internet:
        config.set_value("agent.allow_internet", False)

    if args.non_autonomous:
        config.set_value("agent.autonomous_mode", False)
        print(f"Non-autonomous mode enabled (will ask for input after each step)")
    elif args.autonomous:
        config.set_value("agent.autonomous_mode", True)
        print(f"Autonomous mode enabled (default)")
    else:
        config.set_value("agent.autonomous_mode", True)

    if args.verbose > 0:
        config.set_value("output.verbose_output", True)
        config.set_value("output.verbose_level", min(args.verbose, 3))
        print(f"Verbose output enabled (level {min(args.verbose, 3)})")
    elif args.quiet:
        config.set_value("output.verbose_output", False)
        config.set_value("output.verbose_level", 0)

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
        os.environ["AGENT_MEMORY_DIR"] = str(memory_path)

    if args.projects_dir:
        projects_path = Path(args.projects_dir).resolve()
        projects_path.mkdir(parents=True, exist_ok=True)
        config.set_value("paths.projects_dir", str(projects_path))
        os.environ["AGENT_PROJECTS_DIR"] = str(projects_path)

    config.save_config()

    test_mode = config.is_test_mode()

    system_prompt_path = Path(__file__).parent / "Config" / "SystemPrompts" / "system_prompt.md"
    system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    if not system_prompt_path.exists():
        with open(system_prompt_path, 'w') as f:
            f.write("# Default System Prompt\n\n")
            f.write("## System Status\n")
            f.write("**Current directory**: **{CURRENT_DIRECTORY}**\n")
            f.write("**Agent script location**: **{RUN_AGENT_PATH}**\n")
            f.write("**Current time**: **{CURRENT_TIME}**\n")
            f.write("**Hostname**: **{HOSTNAME}**\n")
            f.write("**Memory directory**: **{MEMORY_DIRECTORY}**\n")
            f.write("**Projects directory**: **{PROJECTS_DIRECTORY}**\n\n")
    available_providers = get_available_model_providers()

    if not available_providers:
        print(f"Error: No API keys found for any providers.")
        print("Please set either ANTHROPIC_API_KEY or DEEPSEEK_API_KEY in your environment.")
        sys.exit(1)

    if args.provider or args.model:
        if args.provider:
            provider = args.provider.lower()
            if provider not in available_providers:
                print(f"Warning: No API key found for provider '{provider}'.")
                if available_providers:
                    fallback_provider = next(iter(available_providers.keys()))
                    print(f"Falling back to available provider: {fallback_provider}")
                    provider = fallback_provider
                else:
                    print(f"Please set {provider.upper()}_API_KEY in your environment.")
                    sys.exit(1)

            if args.model:
                model = args.model
                if model not in available_providers[provider]["models"]:
                    print(f"Warning: Model '{model}' is not in the standard models for {provider}.")
                    print(f"Using it anyway, but it might not work as expected.")
            else:
                model = available_providers[provider]["models"][0]
        else:
            model = args.model
            provider_found = False

            for provider_name, config in available_providers.items():
                if model in config["models"]:
                    provider = provider_name
                    provider_found = True
                    break

            if not provider_found:
                provider = next(iter(available_providers.keys()))
                print(f"Warning: Could not determine provider for model '{model}'.")
                print(f"Using provider '{provider}', but it might not work as expected.")

        model_choice = {"provider": provider, "model": model}

        config.set_value("llm.default_provider", provider)
        config.set_value("llm.default_model", model)
        config.save_config()
    else:
        model_choice = get_model_choice()

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

        if initial_prompt.strip().startswith('/'):
            cmd = initial_prompt.strip().lower()
            if cmd == '/help':
                print("\nAvailable Slash Commands:")
                print("  /help     - Show this help message")
                print("  /compact  - Compact conversation history to save context space")
                print("  /pause    - Pause to add additional context to the conversation")
                print("  /auto     - Toggle autonomous mode on/off")
                print("\nKeyboard Shortcuts:")
                print("  Ctrl+Z    - Pause to add context (equivalent to /pause)")
                print("  Ctrl+C    - Exit the agent")
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
    print(f"- Autonomous Mode: {'Enabled - will operate without asking for user input' if config.get_value('agent.autonomous_mode', True) else 'Disabled - will ask for input after each step'}")
    print(f"- Atom of Thoughts: {'Enabled' if config.get_value('aot.enabled', False) or config.get_value('agent.enable_aot', False) else 'Disabled'}")

    agent = None
    try:
        print("\nInitializing agent...")
        agent = AutonomousAgent(
            api_key=api_key,
            model=model,
            provider=provider,
            test_mode=config.is_test_mode(),
            config=config.to_dict()
        )

        current_agent = agent

        last_session_summary = agent.last_session_summary

        print("\nStarting multi-turn session...\n")

        try:
            system_prompt = load_and_augment_system_prompt(
                str(system_prompt_path),
                last_session_summary=last_session_summary
            )
        except (RuntimeError, IOError) as e:
            print(f"Warning: Error loading system prompt: {str(e)}")
            print("Continuing with empty system prompt...")
            system_prompt = ""

        if test_mode:
            system_prompt = "## TEST MODE: Commands are NOT executed.\n\n" + system_prompt

        await agent.run(initial_prompt, system_prompt)

    except KeyboardInterrupt:
        print("\nShutting down agent (Ctrl+C pressed)...")
    except (RuntimeError, IOError) as e:
        print(f"\nError running agent: {str(e)}")
        if agent:
            try:
                agent.memory_manager.create_backup(force=True)
                print("Emergency state backup created.")
            except Exception as backup_error:
                print(f"Failed to create emergency backup: {str(backup_error)}")
        raise
    finally:
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
