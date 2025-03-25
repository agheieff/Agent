import importlib
import os
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

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
        self.client = None
        self._initialize()
        
    def _initialize(self):
        if not self.api_key:
            raise ValueError(f"API key not found in {self.config.api_key_env}")
            
        try:
            if self.config.requires_import:
                importlib.import_module(self.config.requires_import)
            self.client = self._initialize_client()
        except ImportError as e:
            raise ImportError(f"Required package not installed: {self.config.requires_import}") from e
        except Exception as e:
            raise RuntimeError(f"Client initialization failed: {str(e)}") from e

    def get_available_models(self) -> List[str]:
        return list(self.config.models.keys())

    def _get_model_config(self, model_name: str) -> ModelConfig:
        model = model_name or self.config.default_model
        if model not in self.config.models:
            raise ValueError(f"Model {model} not found in {self.config.name} config")
        return self.config.models[model]

    def _initialize_client(self):
        raise NotImplementedError("Subclasses must implement _initialize_client")

    def _call_api(self, **kwargs):
        raise NotImplementedError("Subclasses must implement _call_api")

    def _process_response(self, response):
        raise NotImplementedError("Subclasses must implement _process_response")

    def chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        raise NotImplementedError("Subclasses must implement chat_completion")
