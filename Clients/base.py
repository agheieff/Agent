import importlib
import os
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
    input_cache_miss: float = 0.0  # additional cost per 1,000,000 tokens for cache miss (if applicable)
    output_cache_miss: float = 0.0  # additional cost per 1,000,000 tokens for cache miss (if applicable)
    discount_hours: Optional[tuple] = None  # tuple (start_hour, end_hour) in UTC for discount hours
    discount_rate: float = 0.0  # discount rate as a decimal (e.g., 0.50 for 50% discount)

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

    def get_available_models(self):
        return list(self.config.models.keys())

    def chat_completion(self, messages: List[Message], model: str = None, max_retries=3, **kwargs):
        for attempt in range(max_retries):
            try:
                return self._chat_completion(messages, model, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        
        model_config = self._get_model_config(model)
        response = self._call_api(messages=messages, model=model_config.name, **kwargs)
        return self._process_response(response)

    def _get_model_config(self, model_name: str) -> ModelConfig:
        model = model_name or self.config.default_model
        if model not in self.config.models:
            raise ValueError(f"Model {model} not found in {self.config.name} config")
        return self.config.models[model]

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _call_api(self, **kwargs):
        raise NotImplementedError

    def _process_response(self, response):
        raise NotImplementedError
