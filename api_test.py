#!/usr/bin/env python3
import os
import sys
import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Dict, Any, Tuple, List, Type # Added Type

# Ensure project root is in path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import base classes and the central config
from Clients.base import BaseClient, Message, ProviderConfig
import config as app_config # Import the central config file
import dotenv

dotenv.load_dotenv(Path(project_root) / '.env')

def get_providers() -> Dict[str, Tuple[Type[BaseClient], ProviderConfig]]:
    """
    Gets available providers by checking config.py and finding corresponding client classes.
    Only includes providers whose API key is found in the environment.
    """
    providers = {}
    # Iterate through provider names defined in config.py
    for provider_name in app_config.get_available_provider_names():
        provider_config = app_config.get_provider_config(provider_name)

        if not provider_config:
            print(f"Warning: Config details missing for provider '{provider_name}' in config.py.")
            continue

        # Check if the API key environment variable is set
        if os.getenv(provider_config.api_key_env):
            print(f"Found API key for provider: {provider_name}")
            try:
                # Dynamically import the client module (assuming naming convention Clients.API.<provider_name>)
                module_name = f"Clients.API.{provider_name}"
                module = importlib.import_module(module_name)

                client_class = None
                # Find the client class within the imported module
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient:
                        if client_class is None:
                            client_class = obj
                        else:
                            print(f"Warning: Multiple client classes found in {module_name}, using {client_class.__name__}")
                            break # Use the first one found

                if client_class:
                    # Store the found class and the config loaded from config.py
                    providers[provider_config.name] = (client_class, provider_config)
                else:
                    print(f"Warning: Client class not found in module {module_name} for provider '{provider_name}'.")

            except ImportError:
                print(f"Warning: Could not import client module {module_name} for provider '{provider_name}'.")
            except Exception as e:
                 print(f"Error processing provider '{provider_name}': {e}")
        else:
            print(f"Skipping provider '{provider_name}': API key ({provider_config.api_key_env}) not set.")

    return providers

async def main():
    print("Starting API Conversation Test (using config.py)")
    providers_data = get_providers() # Renamed variable for clarity
    passed_count = 0
    tested_count = 0

    if not providers_data:
        print("\nWARN: No configured providers with API keys found or client classes could not be loaded.")
        print("Please check your .env file and ensure client files exist in Clients/API/ matching provider names in config.py.")
        return

    # Use items() to get both key (name) and value (tuple)
    for provider_name, (client_class, provider_config) in providers_data.items():
        print(f"\n--- Testing Provider: {provider_name} ---")
        try:
            # Instantiate the client using the class and config from get_providers
            client = client_class(config=provider_config)
            # Get model *aliases* from the config for testing
            model_aliases = app_config.get_available_model_names(provider_name)

            if not model_aliases:
                print(f"WARN: No models listed for provider '{provider_name}' in config.py.")
                continue

            print(f"  Models (Aliases): {', '.join(model_aliases)}")

            # Test each listed model alias for the provider
            for model_alias in model_aliases:
                tested_count += 1
                test_name = f"{provider_name}/{model_alias}"
                print(f"  Testing Model: {test_name}...")
                messages: List[Message] = []

                try:
                    # Test Step 1: Ask for 'A'
                    messages.append(Message("user", "Respond with ONLY the single letter 'A' in uppercase, nothing else."))
                    resp_a_raw = await client.chat_completion(messages=messages, model=model_alias) # Use alias here
                    resp_a = resp_a_raw.strip()
                    if resp_a != "A":
                         print(f"  FAIL: {test_name} - Step 1: Expected 'A', got '{resp_a}'")
                         # Don't raise, just continue to next model/provider to test others
                         continue # Skip step 2 for this model

                    # If Step 1 passed, add messages for Step 2
                    messages.append(Message("assistant", resp_a_raw)) # Add the actual response
                    messages.append(Message("user", "Now respond with ONLY with the next one, nothing else."))

                    # Test Step 2: Ask for 'B'
                    resp_b_raw = await client.chat_completion(messages=messages, model=model_alias)
                    resp_b = resp_b_raw.strip()
                    if resp_b != "B":
                        print(f"  FAIL: {test_name} - Step 2: Expected 'B', got '{resp_b}'")
                        continue # Skip to next model/provider

                    # If both steps passed
                    print(f"  PASS: {test_name}")
                    passed_count += 1

                except Exception as model_test_err:
                    print(f"  ERROR during test for {test_name}: {type(model_test_err).__name__} - {model_test_err}")
                    # Continue testing other models/providers

        except Exception as client_init_err:
             print(f"ERROR initializing client for {provider_name}: {type(client_init_err).__name__} - {client_init_err}")
             # Continue testing other providers

    print("\n" + "="*25 + " Summary " + "="*25)
    print(f"Total Providers Found with Keys: {len(providers_data)}")
    print(f"Total Model Aliases Attempted: {tested_count}")
    print(f"Models Passed Basic Test: {passed_count}")
    print("="*59)

if __name__ == "__main__":
    asyncio.run(main())
