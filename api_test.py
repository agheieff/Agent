#!/usr/bin/env python3
"""
API Test Script

This script tests the connections to all supported API providers.
It verifies that each provider can be initialized and a simple request can be made.
"""

import os
import sys
import importlib
import importlib.util
import logging
from pathlib import Path
from typing import List, Dict, Any

# Add the current directory to path to ensure imports work
sys.path.insert(0, os.path.abspath('.'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define Message class directly rather than importing (for testing purposes)
class Message:
    def __init__(self, role, content, name=None, function_call_id=None):
        self.role = role
        self.content = content
        self.name = name
        self.function_call_id = function_call_id

def discover_providers() -> List[str]:
    """
    Discover available provider modules in the Clients/API directory.
    
    Returns:
        List of provider module names (without the .py extension)
    """
    providers = []
    api_dir = Path("Clients/API")
    
    if not api_dir.exists() or not api_dir.is_dir():
        logger.error(f"API directory not found: {api_dir}")
        return []
    
    for file_path in api_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        
        provider_name = file_path.stem
        providers.append(provider_name)
    
    return providers

def import_provider_client(provider_name: str):
    """
    Import a provider client class dynamically.
    
    Args:
        provider_name: Name of the provider module
        
    Returns:
        Client class for the provider
    """
    try:
        # First, check if we can import the Clients package
        try:
            import Clients
            module = importlib.import_module(f"Clients.API.{provider_name}")
        except ImportError:
            # Try a direct import approach
            sys.path.append(os.path.join(os.path.dirname(__file__), 'Clients'))
            sys.path.append(os.path.join(os.path.dirname(__file__), 'Clients/API'))
            
            # Try to import the module directly
            spec = importlib.util.find_spec(f"{provider_name}")
            if spec is None:
                logger.error(f"Could not find module {provider_name}")
                return None
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        
        # Look for Client class in the module
        for attr_name in dir(module):
            if attr_name.endswith("Client") and attr_name != "BaseClient":
                return getattr(module, attr_name)
        
        logger.error(f"No client class found in module {provider_name}")
        return None
    except Exception as e:
        logger.error(f"Error importing provider {provider_name}: {str(e)}")
        return None

def test_provider(provider_name: str) -> Dict[str, Any]:
    """
    Test a specific provider by initializing the client and making a simple request.
    
    Args:
        provider_name: Name of the provider
        
    Returns:
        Dictionary with test results
    """
    results = {
        "provider": provider_name,
        "initialized": False,
        "has_api_key": False,
        "available_models": [],
        "default_model": None,
        "test_response": None,
        "error": None
    }
    
    logger.info(f"Testing provider: {provider_name}")
    
    # Import the client class
    client_class = import_provider_client(provider_name)
    if not client_class:
        results["error"] = f"Failed to import client for {provider_name}"
        return results
    
    # Initialize the client
    try:
        client = client_class()
        results["initialized"] = True
        
        # Check if API key is available
        if getattr(client, "api_key", None):
            results["has_api_key"] = True
            
            # Get available models
            try:
                models = client.get_available_models()
                results["available_models"] = models
                results["default_model"] = client.default_model
                
                # Make a simple request
                if models:
                    model = client.default_model
                    messages = [Message(role="user", content="Say hello in one sentence.")]
                    
                    try:
                        response = client.chat_completion(messages=messages, model=model)
                        if hasattr(response, "choices") and len(response.choices) > 0:
                            if hasattr(response.choices[0], "message"):
                                results["test_response"] = response.choices[0].message.content
                            else:
                                results["test_response"] = str(response.choices[0])
                        else:
                            results["test_response"] = str(response)
                    except Exception as e:
                        results["error"] = f"API request error: {str(e)}"
            except Exception as e:
                results["error"] = f"Error getting models: {str(e)}"
        else:
            results["error"] = "No API key available"
    except Exception as e:
        results["error"] = f"Initialization error: {str(e)}"
    
    return results

def run_tests():
    """Run tests for all available providers"""
    providers = discover_providers()
    
    if not providers:
        logger.error("No providers found")
        return
    
    logger.info(f"Found providers: {', '.join(providers)}")
    
    results = []
    for provider in providers:
        result = test_provider(provider)
        results.append(result)
        
        # Print results
        logger.info(f"Results for {provider}:")
        logger.info(f"  Initialized: {result['initialized']}")
        logger.info(f"  Has API key: {result['has_api_key']}")
        
        if result["available_models"]:
            logger.info(f"  Available models: {', '.join(result['available_models'])}")
            logger.info(f"  Default model: {result['default_model']}")
        
        if result["test_response"]:
            logger.info(f"  Test response: {result['test_response']}")
        
        if result["error"]:
            logger.error(f"  Error: {result['error']}")
        
        logger.info("---")
    
    # Summary
    successful = sum(1 for r in results if r["test_response"] and not r["error"])
    logger.info(f"Test summary: {successful}/{len(results)} providers passed")

if __name__ == "__main__":
    run_tests() 