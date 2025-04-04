#!/usr/bin/env python3
import os
import sys
import argparse
import importlib
import inspect
import dotenv
from typing import Dict, List, Tuple, Any
import asyncio

from Core.agent_runner import AgentRunner
from Core.utils import get_multiline_input
from Prompts.main import generate_system_prompt

def load_env_variables():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_file):
        print(f"Loading environment variables from {env_file}")
        dotenv.load_dotenv(env_file)
    else:
        print("Warning: .env file not found. API keys will need to be set manually.")
        print("Create a .env file with the provider API keys:")
        print("OPENAI_API_KEY=your_key_here")
        print("ANTHROPIC_API_KEY=your_key_here")
        print("DEEPSEEK_API_KEY=your_key_here")
        print("GOOGLE_API_KEY=your_key_here (for Gemini)")

def discover_providers() -> Dict[str, Any]:
    providers = {}
    clients_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Clients", "API")

    for filename in os.listdir(clients_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"Clients.API.{module_name}")
                provider_name = module_name.lower()
                env_var_name = f"{provider_name.upper()}_API_KEY"

                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        name.endswith('Client') and 
                        name.lower().startswith(provider_name)):
                        if os.environ.get(env_var_name):
                            providers[provider_name] = obj
                        break
            except (ImportError, AttributeError) as e:
                print(f"Warning: Could not import provider module {module_name}: {e}")

    return providers

def get_available_models(provider_class: Any) -> List[str]:
    try:
        provider_instance = provider_class()
        return sorted(provider_instance.get_available_models())
    except Exception as e:
        print(f"Error getting models for provider: {e}")
        return []

def interactive_provider_selection(providers: Dict[str, Any]) -> Tuple[str, Any]:
    if not providers:
        print("Error: No valid providers found with API keys set.")
        print("Please set API keys in your .env file for at least one provider:")
        print("  ANTHROPIC_API_KEY=your_key_here")
        print("  DEEPSEEK_API_KEY=your_key_here")
        sys.exit(1)

    provider_names = sorted(providers.keys())

    print("\nAvailable providers:")
    for i, name in enumerate(provider_names, 1):
        print(f"  {i}. {name}")

    while True:
        try:
            choice = input("\nSelect a provider (number or name): ")

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(provider_names):
                    provider_name = provider_names[idx]
                    return provider_name, providers[provider_name]
                else:
                    print(f"Invalid selection. Please enter 1-{len(provider_names)}.")
            elif choice.lower() in providers:
                return choice.lower(), providers[choice.lower()]
            else:
                print(f"Provider '{choice}' not found. Please try again.")

        except (ValueError, KeyError, IndexError):
            print("Invalid selection. Please try again.")

def interactive_model_selection(provider_name: str, provider_class: Any) -> str:
    models = get_available_models(provider_class)

    if not models:
        print(f"Error: No models available for provider '{provider_name}'.")
        sys.exit(1)

    print(f"\nAvailable {provider_name} models:")
    for i, model in enumerate(models, 1):
        print(f"  {i}. {model}")

    while True:
        try:
            choice = input("\nSelect a model (number or name): ")
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    return models[idx]
                else:
                    print(f"Invalid selection. Please enter 1-{len(models)}.")
            elif choice in models:
                return choice
            else:
                print(f"Model '{choice}' not found. Please try again.")
        except (ValueError, KeyError, IndexError):
            print("Invalid selection. Please try again.")

async def main():
    load_env_variables()
    providers = discover_providers()

    parser = argparse.ArgumentParser(description="Run an AI agent with tool execution capabilities")
    parser.add_argument("--provider", "-p", type=str, default=None,
                        help="The model provider to use (e.g., openai, anthropic, gemini)")
    parser.add_argument("--model", "-m", type=str, default=None,
                        help="The model name to use")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Initial prompt to send to the agent")
    parser.add_argument("--prompt-file", type=str, default=None,
                        help="File containing the initial prompt")
    args = parser.parse_args()

    if args.provider:
        if args.provider.lower() in providers:
            provider_name = args.provider.lower()
            provider_class = providers[provider_name]
        else:
            print(f"Error: Provider '{args.provider}' not found.")
            print(f"Available providers: {', '.join(providers.keys())}")
            sys.exit(1)
    else:
        provider_name, provider_class = interactive_provider_selection(providers)

    if args.model:
        available = get_available_models(provider_class)
        if args.model in available:
            model_name = args.model
        else:
            print(f"Error: Model '{args.model}' not found for provider '{provider_name}'.")
            print(f"Available models: {', '.join(available)}")
            sys.exit(1)
    else:
        model_name = interactive_model_selection(provider_name, provider_class)

    initial_prompt = ""
    if args.prompt:
        initial_prompt = args.prompt.strip()
    elif args.prompt_file:
        try:
            with open(args.prompt_file, 'r') as f:
                initial_prompt = f.read().strip()
        except Exception as e:
            print(f"Error reading prompt file: {e}")
            sys.exit(1)
    else:
        initial_prompt = get_multiline_input("Enter your prompt (press Enter twice to submit): ")

    agent = AgentRunner(provider_name, model_name)

    await agent.run(initial_prompt)

if __name__ == "__main__":
    asyncio.run(main())
