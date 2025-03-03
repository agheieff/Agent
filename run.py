"""Main entry point for the autonomous agent."""

import asyncio
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import socket
import signal
import time
import yaml
from typing import Dict, List, Optional

from Config import config, Config
from Core.agent import AutonomousAgent

# We import the system prompt generator from Prompts/main
from Prompts.main import generate_system_prompt

INITIAL_PROMPT_HISTORY_FILE = '~/.agent_prompt_history'
CONTEXT_HISTORY_FILE = '~/.agent_context_history'

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
        # We assume there's some method to add user context. If not, we skip it.
        # In original code, might be agent.add_human_context(...) or agent.local_conversation_history
        if hasattr(current_agent, 'local_conversation_history'):
            current_agent.local_conversation_history.append({"role": "user", "content": additional_context})
        print("Context added. Conversation will continue.")
    else:
        print("No additional context provided. Continuing without changes.")

    paused_for_context = False

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

def get_available_model_providers() -> Dict[str, Dict[str, List[str]]]:
    provider_config = {
        "anthropic": {
            "env_prefix": "ANTHROPIC",
            "models": ["claude-3-7-sonnet"]
        },
        "deepseek": {
            "env_prefix": "DEEPSEEK",
            "models": ["deepseek-reasoner", "deepseek-reasoner-tools"]
        },
    }
    available_providers = {}
    for prov, info in provider_config.items():
        api_key = os.getenv(f"{info['env_prefix']}_API_KEY", "")
        if api_key.strip():
            available_providers[prov] = info
    return available_providers

def get_model_choice(available_providers: Dict[str, Dict[str, List[str]]]) -> Dict[str, str]:
    if not available_providers:
        print("No valid providers found. Please set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY.")
        sys.exit(1)
    if len(available_providers) == 1:
        # Single provider
        only_provider = list(available_providers.keys())[0]
        only_model = available_providers[only_provider]["models"][0]
        print(f"\nUsing single available provider: {only_provider}, model: {only_model}")
        return {"provider": only_provider, "model": only_model}
    else:
        # If multiple providers, pick one from user input:
        providers = list(available_providers.keys())
        for i, p in enumerate(providers, start=1):
            print(f"{i}. {p} (models: {available_providers[p]['models']})")
        choice = input("Choose a provider (number): ")
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(providers):
                raise ValueError
            chosen_provider = providers[idx]
        except:
            chosen_provider = providers[0]
            print(f"Invalid choice. Using default: {chosen_provider}")

        # If that provider has multiple models
        provider_models = available_providers[chosen_provider]["models"]
        if len(provider_models) == 1:
            return {"provider": chosen_provider, "model": provider_models[0]}
        else:
            for i, m in enumerate(provider_models, start=1):
                print(f"{i}. {m}")
            model_choice = input("Choose a model: ")
            try:
                midx = int(model_choice) - 1
                if midx < 0 or midx >= len(provider_models):
                    raise ValueError
                chosen_model = provider_models[midx]
            except:
                chosen_model = provider_models[0]
                print(f"Invalid choice. Using default: {chosen_model}")
            return {"provider": chosen_provider, "model": chosen_model}

async def main():
    global current_agent
    load_dotenv()

    if hasattr(signal, 'SIGTSTP'):
        signal.signal(signal.SIGTSTP, handle_pause_signal)

    parser = argparse.ArgumentParser(description="Run the Autonomous Agent.")
    parser.add_argument('--test', action='store_true', help="Run in test mode (no real commands execution)")
    parser.add_argument('--provider', choices=['anthropic', 'deepseek'], help="Specify model provider directly")
    parser.add_argument('--model', help="Specify model name directly (e.g. claude-3-7-sonnet, deepseek-reasoner)")
    parser.add_argument('--headless', action='store_true', help="Run in headless mode (no interactive prompts)")
    parser.add_argument('--no-internet', action='store_true', help="Disable internet access")
    parser.add_argument('--non-autonomous', action='store_true', help="Disable autonomous mode")
    parser.add_argument('--autonomous', action='store_true', help="Enable autonomous mode")
    args = parser.parse_args()

    # Update config
    if args.test:
        config.set("agent.test_mode", True)
    if args.headless:
        config.set("agent.headless", True)
    if args.no_internet:
        config.set("agent.allow_internet", False)
    if args.non_autonomous:
        config.set("agent.autonomous_mode", False)
    elif args.autonomous:
        config.set("agent.autonomous_mode", True)

    # We now select provider / model
    available_providers = get_available_model_providers()
    if args.provider:
        # If user sets provider explicitly
        if args.provider not in available_providers:
            print(f"Provider {args.provider} not found or no API key set. Exiting.")
            sys.exit(1)
        provider = args.provider
        if args.model:
            model = args.model
        else:
            model = available_providers[provider]["models"][0]
    else:
        if not available_providers:
            print("No providers found. Please set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY.")
            sys.exit(1)
        if args.model:
            # We have a model but no provider, guess
            guess_provider = None
            for p in available_providers:
                if args.model in available_providers[p]["models"]:
                    guess_provider = p
                    break
            if guess_provider is None:
                # fallback
                guess_provider = list(available_providers.keys())[0]
            provider = guess_provider
            model = args.model
        else:
            # fully interactive choice
            chosen = get_model_choice(available_providers)
            provider = chosen["provider"]
            model = chosen["model"]

    # Retrieve API key
    env_prefix = {"anthropic": "ANTHROPIC", "deepseek": "DEEPSEEK"}.get(provider, provider.upper())
    api_key = os.getenv(f"{env_prefix}_API_KEY", "")
    if not api_key:
        print(f"No API key for {provider} found in environment under {env_prefix}_API_KEY. Exiting.")
        sys.exit(1)

    # Prompt user for initial prompt
    if config.get("agent.headless", False):
        # For headless, maybe take from an argument or skip
        initial_prompt = "Headless mode, no user input provided."
    else:
        initial_prompt = get_initial_prompt()
        if not initial_prompt.strip():
            print("Empty prompt. Exiting.")
            sys.exit(0)

    print(f"\nUsing provider: {provider}, model: {model}")
    if config.get("agent.test_mode", False):
        print("TEST MODE is enabled. Commands are not actually executed.")

    # Generate a system prompt from Prompts/main.py
    full_system_prompt = generate_system_prompt()

    # If anthropic => system prompt is in role=system, user prompt is initial_prompt
    # If deepseek => combine them all as user prompt, system prompt is None
    system_prompt = None
    user_prompt = initial_prompt
    if provider == "anthropic":
        system_prompt = full_system_prompt
        # user_prompt remains as the typed-in user message
    else:
        # e.g. deepseek
        system_prompt = None
        user_prompt = full_system_prompt + "\n\n" + initial_prompt

    # Initialize agent
    agent = AutonomousAgent(
        memory_manager=None,
        session_manager=None,
        api_key=api_key,
        model=model,
        provider=provider,
        test_mode=config.get("agent.test_mode", False),
        config=config.to_dict()
    )
    current_agent = agent

    # Start the agent
    try:
        await agent.run(initial_prompt=user_prompt, system_prompt=system_prompt)
    except KeyboardInterrupt:
        print("\nExiting (KeyboardInterrupt).")
    finally:
        # Summaries or usage info
        if agent and hasattr(agent, 'llm') and getattr(agent.llm, 'usage_history', None):
            print("\n=== API USAGE SUMMARY ===")
            print(f"Total API Calls: {len(agent.llm.usage_history)}")
            print(f"Total Tokens: {agent.llm.total_tokens:,}")
            print(f"  - Input Tokens: {agent.llm.total_prompt_tokens:,}")
            print(f"  - Output Tokens: {agent.llm.total_completion_tokens:,}")
            print(f"Total Cost: ${agent.llm.total_cost:.6f}")
            print("=========================")

        print("\nAgent session ended.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
        sys.exit(0)
    except (RuntimeError, IOError) as e:
        print(f"\nFatal error: {str(e)}")
        sys.exit(1)
