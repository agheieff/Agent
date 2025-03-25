from dataclasses import dataclass
from typing import List, Dict, Optional
import os
import logging

@dataclass
class ModelConfig:
    name: str
    context_length: int
    cost_per_token: float

class ModelInterface:
    def __init__(self, provider: str, api_key: str = None):
        self.provider = provider
        self.api_key = api_key or os.getenv(f"{provider.upper()}_API_KEY")
        self.models = self._load_models()
        
    def _load_models(self) -> Dict[str, ModelConfig]:
        """Provider-specific model configurations"""
        raise NotImplementedError
        
    def generate(self, messages: List[Dict], model: str = None) -> str:
        model_config = self._get_model_config(model)
        try:
            response = self._call_api(messages, model_config)
            return self._process_response(response)
        except Exception as e:
            logging.error(f"API call failed: {e}")
            raise

    def _call_api(self, messages: List[Dict], model: ModelConfig):
        raise NotImplementedError

    def _process_response(self, response) -> str:
        raise NotImplementedError
