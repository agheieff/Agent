import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PromptStyle(Enum):
    SYSTEM_MESSAGE = "system_message"
    PREPEND_TO_USER = "prepend_to_user"
    USER_PREFIX = "user_prefix"

@dataclass
class Message:
    role: str  # "system", "user", "assistant"
    content: str
    name: Optional[str] = None
    function_call_id: Optional[str] = None

@dataclass
class PricingTier:
    input: float  # Cost per million tokens for input
    output: float  # Cost per million tokens for output
    discount_hours: Optional[Tuple[int, int]] = None
    discount_percentage: float = 0.0

@dataclass
class ModelConfig:
    name: str
    prompt_style: PromptStyle = PromptStyle.SYSTEM_MESSAGE
    context_length: int
    pricing: PricingTier

@dataclass
class ProviderConfig:
    name: str
    api_base: str
    api_key_env: str
    default_model: str
    models: Dict[str, ModelConfig]
    default_temperature: float = 0.7
    default_max_tokens: int = 4000
    requires_import: str = None
    response_format: str = None

class RateLimiter:
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self.last_call_time = 0

    def __enter__(self):
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.last_call_time = time.time()

class BaseClient:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        self.api_base = config.api_base
        self.client = None
        self.rate_limiter = RateLimiter()
        
        if self.api_key and config.requires_import:
            try:
                self.client = self._initialize_client()
            except ImportError:
                logging.warning(f"Required package not found: {config.requires_import}")

    def _initialize_client(self):
        raise NotImplementedError("Subclasses must implement this method")

    def get_available_models(self) -> List[str]:
        return list(self.config.models.keys())

    def get_model_config(self, model_name: str) -> ModelConfig:
        model_name = model_name or self.config.default_model
        if model_name not in self.config.models:
            raise ValueError(f"Unknown model: {model_name}")
        return self.config.models[model_name]

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        """Convert messages to provider-specific format"""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _get_api_params(self, **kwargs) -> Dict[str, Any]:
        """Get default API parameters with overrides"""
        params = {
            "temperature": self.config.default_temperature,
            "max_tokens": self.config.default_max_tokens,
        }
        params.update(kwargs)
        return params

    def chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        model_config = self.get_model_config(model)
        
        with self.rate_limiter:
            try:
                response = self._call_api(
                    messages=self._format_messages(messages),
                    model=model_config.name,
                    **self._get_api_params(**kwargs)
                )
                return self._process_response(response)
            except Exception as e:
                logger.error(f"API call failed: {str(e)}")
                raise

    def _call_api(self, **kwargs):
        raise NotImplementedError("Subclasses must implement this method")

    def _process_response(self, response):
        """Process raw API response into standard format"""
        return response
