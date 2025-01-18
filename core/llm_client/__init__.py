from .base import BaseLLMClient
from .anthropic import AnthropicClient
from .deepseek import DeepSeekClient

def get_llm_client(provider: str, api_key: str) -> BaseLLMClient:
    """Factory function to get appropriate LLM client"""
    clients = {
        "anthropic": AnthropicClient,
        "deepseek": DeepSeekClient
    }
    
    client_class = clients.get(provider.lower())
    if not client_class:
        raise ValueError(f"Unknown LLM provider: {provider}")
    
    return client_class(api_key)
