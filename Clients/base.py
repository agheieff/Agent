# --- File: /Clients/base.py ---

import importlib
import os
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
import httpx # Add httpx import

@dataclass
class Message:
    role: str  # "system", "user", "assistant"
    content: str

@dataclass
class PricingTier:
    input: float  # cost per 1,000,000 input tokens
    output: float  # cost per 1,000,000 output tokens
    input_cache_miss: float = 0.0  # additional cost per 1,000,000 tokens for cache miss
    output_cache_miss: float = 0.0  # additional cost per 1,000,000 tokens for cache miss
    discount_hours: Optional[tuple] = None  # tuple (start_hour, end_hour) in UTC for discount hours
    discount_rate: float = 0.0  # discount rate as a decimal

@dataclass
class ModelConfig:
    name: str
    context_length: int
    pricing: PricingTier

@dataclass
class ProviderConfig:
    name: str
    api_base: str
    api_key_env: str
    models: Dict[str, ModelConfig]
    default_model: str
    requires_import: Optional[str] = None

@dataclass
class UsageStats:
    input_tokens: int
    output_tokens: int
    cost: float

class BaseClient:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        self.client = None # For the primary API (e.g., Anthropic, OpenAI)
        self.http_client: Optional[httpx.AsyncClient] = None # For general HTTP requests (e.g., to MCP)
        self._initialize()

    def _initialize(self):
        if not self.api_key:
            raise ValueError(f"API key not found in {self.config.api_key_env}")

        try:
            if self.config.requires_import:
                importlib.import_module(self.config.requires_import)
            self.client = self._initialize_client()
            # Initialize a shared httpx client if needed by subclasses
            self.http_client = httpx.AsyncClient(timeout=30.0) # Default timeout for HTTP requests

        except ImportError as e:
            raise ImportError(f"Required package not installed: {self.config.requires_import}") from e
        except Exception as e:
            # Clean up http_client if initialization failed after creating it
            if self.http_client:
                # Need an async context to properly close, difficult here.
                # Rely on garbage collection or ensure subclasses handle closure.
                pass
            raise RuntimeError(f"Client initialization failed: {str(e)}") from e

    async def close(self):
        """Clean up resources, like the HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        # Subclasses might need to close their specific clients too
        if hasattr(self.client, 'aclose'):
             await self.client.aclose()
        elif hasattr(self.client, 'close'):
             self.client.close()


    def get_available_models(self) -> List[str]:
        return list(self.config.models.keys())

    def _get_model_config(self, model_name: str) -> ModelConfig:
        model = model_name or self.config.default_model
        if model not in self.config.models:
            raise ValueError(f"Model {model} not found in {self.config.name} config")
        return self.config.models[model]

    def _initialize_client(self):
        """Initializes the primary API client (e.g., Anthropic SDK)."""
        raise NotImplementedError("Subclasses must implement _initialize_client")

    # Removed _call_api and _process_response abstract methods as they are
    # often implementation details rather than a strict public interface.
    # Subclasses can define their own helper methods.

    async def chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        """Gets a standard chat completion."""
        raise NotImplementedError("Subclasses must implement chat_completion")

    async def stream_chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        """Gets a streaming chat completion."""
        raise NotImplementedError("Subclasses must implement stream_chat_completion")
