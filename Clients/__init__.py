from typing import Optional
import logging
from .base_client import BaseLLMClient, TokenUsage
from .anthropic_client import AnthropicClient
from .deepseek_client import DeepSeekClient
from .openai_client import OpenAIClient                       

logger = logging.getLogger(__name__)

def get_llm_client(model_type: str, api_key: str, model: Optional[str] = None) -> BaseLLMClient:
    model_type = model_type.lower()

    if not api_key:
        raise ValueError("API key is required")

    if model_type == "anthropic" or model_type.startswith("claude"):
        logger.info("Initializing Anthropic Claude client")
        return AnthropicClient(api_key)
    elif model_type == "deepseek" or model_type.startswith("deepseek"):
        logger.info("Initializing DeepSeek client")
        return DeepSeekClient(api_key)
    elif model_type == "openai" or model_type.startswith("openai"):
        logger.info("Initializing OpenAI client")
        return OpenAIClient(api_key, model=model)
    else:
        raise ValueError(f"Unsupported model type: {model_type}")
