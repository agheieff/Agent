#!/usr/bin/env python3
import os
import sys
import argparse
import importlib
import inspect
import dotenv
from typing import Dict, List, Tuple, Optional, Any
from Core.agent_runner import AgentRunner
from Core.utils import get_multiline_input

def load_env_variables():
    """
    Load environment variables from .env file if it exists.
    """
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
    """
    Discover available providers by scanning the Clients/API directory.
    Only returns providers that have API keys set in the environment.
    
    Returns:
        Dict mapping provider names to their client classes
    """
    providers = {}
    clients_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Clients", "API")
    
    # Get all .py files in the Clients/API directory
    for filename in os.listdir(clients_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]  # Remove .py extension
            try:
                # Import the module
                module = importlib.import_module(f"Clients.API.{module_name}")
                
                # Look for client classes that inherit from BaseClient
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        name.endswith('Client')):
                        
                        provider_name = module_name.lower()
                        
                        # Check if there's an API key for this provider
                        env_var_name = f"{provider_name.upper()}_API_KEY"
                        if os.environ.get(env_var_name):
                            providers[provider_name] = obj
                        break
            except (ImportError, AttributeError) as e:
                print(f"Warning: Could not import provider module {module_name}: {e}")
    
    return providers

def get_available_models(provider_class: Any) -> List[str]:
    """
    Get available models for a provider.
    
    Args:
        provider_class: The provider client class
    
    Returns:
        List of model names
    """
    try:
        # Create a temporary instance of the provider class
        provider_instance = provider_class()
        # Return sorted list of model names
        return sorted(provider_instance.get_available_models())
    except Exception as e:
        print(f"Error getting models for provider: {e}")
        return []

def interactive_provider_selection(providers: Dict[str, Any]) -> Tuple[str, Any]:
    """
    Interactively select a provider from the available options.
    
    Args:
        providers: Dict mapping provider names to their client classes
    
    Returns:
        Tuple of (provider_name, provider_class)
    """
    if not providers:
        print("Error: No valid providers found with API keys set.")
        print("Please set API keys in your .env file for at least one provider:")
        print("  OPENAI_API_KEY=your_key_here")
        print("  ANTHROPIC_API_KEY=your_key_here")
        print("  DEEPSEEK_API_KEY=your_key_here")
        print("  GOOGLE_API_KEY=your_key_here (for Gemini)")
        sys.exit(1)
    
    provider_names = sorted(providers.keys())
    
    print("\nAvailable providers:")
    for i, name in enumerate(provider_names, 1):
        print(f"  {i}. {name}")
    
    while True:
        try:
            choice = input("\nSelect a provider (number or name): ")
            
            # Check if input is a number
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(provider_names):
                    provider_name = provider_names[idx]
                    return provider_name, providers[provider_name]
                else:
                    print(f"Invalid selection. Please enter 1-{len(provider_names)}.")
            # Check if input is a provider name
            elif choice.lower() in providers:
                return choice.lower(), providers[choice.lower()]
            else:
                print(f"Provider '{choice}' not found. Please try again.")
        
        except (ValueError, KeyError, IndexError):
            print("Invalid selection. Please try again.")

def interactive_model_selection(provider_name: str, provider_class: Any) -> str:
    """
    Interactively select a model from the available options for a provider.
    
    Args:
        provider_name: Name of the selected provider
        provider_class: The provider client class
    
    Returns:
        Selected model name
    """
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
            
            # Check if input is a number
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    return models[idx]
                else:
                    print(f"Invalid selection. Please enter 1-{len(models)}.")
            # Check if input is a model name
            elif choice in models:
                return choice
            else:
                print(f"Model '{choice}' not found. Please try again.")
        
        except (ValueError, KeyError, IndexError):
            print("Invalid selection. Please try again.")

def main():
    """
    Main function to run the agent with command-line arguments or interactive selection.
    """
    # Load environment variables from .env file
    load_env_variables()
    
    # Discover available providers
    try:
        providers = discover_providers()
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run an AI agent with tool execution capabilities")
    
    # Model arguments
    parser.add_argument("--provider", "-p", type=str, default=None,
                        help="The model provider to use (e.g., openai, anthropic, gemini)")
    parser.add_argument("--model", "-m", type=str, default=None,
                        help="The model name to use")
    
    # Input arguments
    parser.add_argument("--prompt", type=str, default=None,
                        help="Initial prompt to send to the agent")
    parser.add_argument("--prompt-file", type=str, default=None,
                        help="File containing the initial prompt")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Process provider
    provider_name = args.provider
    if not provider_name:
        provider_name, provider_class = interactive_provider_selection(providers)
    elif provider_name.lower() in providers:
        provider_name = provider_name.lower()
        provider_class = providers[provider_name]
    else:
        print(f"Error: Provider '{provider_name}' not found.")
        print(f"Available providers: {', '.join(providers.keys())}")
        sys.exit(1)
    
    # Process model selection
    try:
        # Get available models for this provider
        available_models = get_available_models(provider_class)
        
        # If no model specified, let the user select one
        if not args.model:
            print(f"\nAvailable {provider_name} models:")
            for i, model in enumerate(available_models, start=1):
                print(f"  {i}. {model}")
            print()
            
            # Get model selection from user
            choice = input("Select a model (number or name): ")
            
            # Handle selection by number
            if choice.isdigit() and 1 <= int(choice) <= len(available_models):
                model_name = available_models[int(choice) - 1]
            # Handle selection by name 
            elif choice in available_models:
                model_name = choice
            else:
                print(f"Error: Invalid model selection: '{choice}'")
                sys.exit(1)
        else:
            # Use the specified model
            model_name = args.model
            # Validate it
            if model_name not in available_models:
                print(f"Error: Model '{model_name}' not found for provider '{provider_name}'.")
                print(f"Available models: {', '.join(available_models)}")
                sys.exit(1)
        
    except Exception as e:
        print(f"Error: Failed to get models for provider '{provider_name}': {str(e)}")
        sys.exit(1)
    
    # Get the initial prompt
    initial_prompt = args.prompt
    
    if args.prompt_file:
        try:
            with open(args.prompt_file, 'r') as file:
                initial_prompt = file.read().strip()
        except Exception as e:
            sys.exit(f"Error reading prompt file: {str(e)}")
    
    if not initial_prompt:
        print("\nEnter your initial prompt for the agent (press Enter twice to submit):")
        initial_prompt = get_multiline_input("> ")
    
    # Create and run the agent
    try:
        print(f"\nStarting agent with provider: {provider_name}, model: {model_name}")
        agent = AgentRunner(provider_name, model_name)
        agent.run(initial_prompt)
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
    except Exception as e:
        print(f"Error running agent: {str(e)}")

if __name__ == "__main__":
    main() 