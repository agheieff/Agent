from typing import Optional
import logging
from .base import BaseLLMClient
from .anthropic import AnthropicClient
from .deepseek import DeepSeekClient
from .openai import OpenAIClient

logger = logging.getLogger(__name__)

def get_llm_client(model_type: str, api_key: str, model: Optional[str] = None) -> BaseLLMClient:
    m = model_type.lower()
    if not api_key:
        raise ValueError("API key is required")
    if m == "anthropic" or m.startswith("claude"):
        logger.info("Initializing Anthropic Claude client")
        return AnthropicClient(api_key)
    elif m == "deepseek" or m.startswith("deepseek"):
        logger.info("Initializing DeepSeek client")
        return DeepSeekClient(api_key)
    elif m == "openai" or m.startswith("openai"):
        logger.info("Initializing OpenAI client")
        return OpenAIClient(api_key, model=model)
    raise ValueError(f"Unsupported model type: {model_type}")
