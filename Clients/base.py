import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

@dataclass
class Message:
    role: str  # "system", "user", "assistant"
    content: str

@dataclass
class ModelConfig:
    name: str
    context_length: int
    pricing: Dict[str, float]  # input/output costs per token

@dataclass
class ProviderConfig:
    name: str
    api_base: str
    api_key_env: str
    models: Dict[str, ModelConfig]
    default_model: str

class BaseClient:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        self.client = self._initialize_client() if self.api_key else None

    def _initialize_client(self):
        raise NotImplementedError

    def chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        model_config = self._get_model_config(model)
        formatted = self._format_messages(messages)
        response = self._call_api(messages=formatted, model=model_config.name, **kwargs)
        return self._process_response(response)

    def _get_model_config(self, model_name: str) -> ModelConfig:
        return self.config.models.get(model_name or self.config.default_model)

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _call_api(self, **kwargs):
        raise NotImplementedError

    def _process_response(self, response):
        raise NotImplementedError
