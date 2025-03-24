#!/usr/bin/env python3
import os
import sys
import importlib
import inspect
from typing import Dict, Any

def load_clients():
    """
    Load all client classes from Clients/API directory.
    """
    clients = {}
    clients_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Clients", "API")
    
    # Get all .py files in the Clients/API directory
    for filename in os.listdir(clients_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]  # Remove .py extension
            try:
                # Import the module
                module = importlib.import_module(f"Clients.API.{module_name}")
                
                # Look for client classes
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and name.endswith('Client'):
                        clients[name] = obj
                        print(f"Loaded client class: {name}")
            except (ImportError, AttributeError) as e:
                print(f"Warning: Could not import client module {module_name}: {e}")
    
    return clients

def test_client(client_class):
    """
    Test a client class by checking its model configurations.
    """
    print(f"\nTesting {client_class.__name__}:")
    try:
        # Create instance
        instance = client_class()
        print(f"  Created instance")
        
        # Get model configs
        models = instance.get_available_models()
        print(f"  Available models: {len(models)}")
        for model in models:
            try:
                config = instance.get_model_config(model)
                print(f"  - {model}: context_length={config.context_length}, pricing={config.pricing.input}/{config.pricing.output}")
            except Exception as e:
                print(f"  - Error getting config for {model}: {e}")
        
        # Get default model
        default = instance.default_model
        print(f"  Default model: {default}")
        
    except Exception as e:
        print(f"  Error testing client: {e}")
        import traceback
        traceback.print_exc()

def main():
    """
    Main function to test client classes.
    """
    # Load all client classes
    clients = load_clients()
    
    # Test each client
    for name, client_class in clients.items():
        test_client(client_class)
    
    print("\nTest completed")

if __name__ == "__main__":
    main() 