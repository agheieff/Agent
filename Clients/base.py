import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

@dataclass
class Message:
    role: str  # "system", "user", "assistant"
    content: str

@dataclass
class PricingTier:
    input: float  # cost per 1000 input tokens
    output: float  # cost per 1000 output tokens

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
        if self.api_key:
            self.client = self._initialize_client()
        else:
            self.client = None

    def _initialize_client(self):
        raise NotImplementedError

    def get_available_models(self):
        return list(self.config.models.keys())

    def chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        if not self.client:
            raise ValueError(f"No API key found for {self.config.name}. Set {self.config.api_key_env} environment variable.")
        
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
