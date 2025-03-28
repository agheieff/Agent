from typing import Optional
import logging
from .base import (
    BaseClient,
    Message,
    ModelConfig,
    PricingTier,
    ProviderConfig,
    UsageStats,
)

# Concrete client implementations
# Use try/except to allow importing even if dependencies are missing,
# but initialization will fail later if needed.
try:
    from .API.anthropic import AnthropicClient
except ImportError:
    AnthropicClient = None # type: ignore

try:
    from .API.deepseek import DeepSeekClient
except ImportError:
    DeepSeekClient = None # type: ignore

# Add other clients here...
# try:
#     from .API.openai import OpenAIClient
# except ImportError:
#     OpenAIClient = None

__all__ = [
    # Base
    "BaseClient",
    "Message",
    "ModelConfig",
    "PricingTier",
    "ProviderConfig",
    "UsageStats",

    # Clients
    "AnthropicClient",
    "DeepSeekClient",
    # "OpenAIClient",
]

# Optional: Function to get a client instance by name
def get_client(provider_name: str, **kwargs) -> Optional[BaseClient]:
    """
    Factory function to get an instance of a client by provider name.
    """
    provider_map = {
        "anthropic": AnthropicClient,
        "deepseek": DeepSeekClient,
        # "openai": OpenAIClient,
    }
    client_class = provider_map.get(provider_name.lower())
    if client_class:
        try:
            return client_class(**kwargs)
        except Exception as e:
            logging.error(f"Failed to instantiate client '{provider_name}': {e}", exc_info=True)
            return None
    else:
        logging.error(f"Unknown provider name: '{provider_name}'. Available: {list(provider_map.keys())}")
        return None
