import os
import glob
import json

def get_available_providers(clients_dir='Clients'):
    """
    Scan the Clients/ directory for provider client modules.
    Assumes that each provider is implemented in its own .py file
    (excluding __init__.py), and the file name (lowercase) is the provider name.
    """
    available_providers = set()
    pattern = os.path.join(clients_dir, '*.py')
    for filepath in glob.glob(pattern):
        filename = os.path.basename(filepath)
        if filename == '__init__.py':
            continue
        # Assume provider name is the file name without .py
        provider_name = filename.replace('.py', '').lower()
        available_providers.add(provider_name)
    return available_providers

def get_available_api_keys():
    """
    Look up known API key environment variables and return a dict
    mapping provider names to their API key.
    """
    # Mapping of provider name to expected environment variable name.
    env_keys = {
        'openai': 'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'deepseek': 'DEEPSEEK_API_KEY'
    }
    keys = {}
    for provider, env_var in env_keys.items():
        api_key = os.getenv(env_var)
        if api_key:
            keys[provider] = api_key
    return keys

def get_active_providers(clients_dir='Clients'):
    """
    Returns a dict of providers that are implemented (in Clients/) and
    have a corresponding API key configured in the environment.
    """
    available_providers = get_available_providers(clients_dir)
    available_keys = get_available_api_keys()
    active = {}
    for provider in available_providers:
        if provider in available_keys:
            active[provider] = available_keys[provider]
    return active

if __name__ == '__main__':
    active_providers = get_active_providers()
    print("Active providers (both implemented and configured):")
    print(json.dumps(active_providers, indent=4))
