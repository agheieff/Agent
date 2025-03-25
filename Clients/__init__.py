"""
LLM API Clients package.

This package provides a unified interface for interacting with various
LLM APIs, including OpenAI, Anthropic, Google, and DeepSeek.
"""

# Import base classes
from Clients.base import (
    BaseClient,
    Message,
    ModelConfig,
    PricingTier,
    ProviderConfig,
    UsageStats
)

# Import clients
try:
    from Clients.API.openai import OpenAIClient
except ImportError:
    OpenAIClient = None

try:
    from Clients.API.anthropic import AnthropicClient
except ImportError:
    AnthropicClient = None

try:
    from Clients.API.gemini import GeminiClient
except ImportError:
    GeminiClient = None

try:
    from Clients.API.deepseek import DeepSeekClient
except ImportError:
    DeepSeekClient = None

__all__ = [
    # Base classes
    "BaseClient",
    "Message",
    "ModelConfig",
    "PricingTier",
    "ProviderConfig",
    "UsageStats",
    
    # Client implementations
    "OpenAIClient",
    "AnthropicClient",
    "GeminiClient",
    "DeepSeekClient",
]
