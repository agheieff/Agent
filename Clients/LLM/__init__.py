from typing import Optional
import logging
from .base_client import BaseLLMClient, TokenUsage
from .anthropic_client import AnthropicClient
from .deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)

def get_llm_client(model_type: str, api_key: str) -> BaseLLMClient:
    """
    Factory function to create a client for the specified LLM service.
    
    Args:
        model_type: The type of model to use (anthropic, deepseek, etc.)
        api_key: API key for the service
        
    Returns:
        An instance of BaseLLMClient for the requested service
        
    Raises:
        ValueError: If the model type is not supported or the API key is missing
    """
    model_type = model_type.lower()
    
    if not api_key:
        raise ValueError("API key is required")
        
    if model_type == "anthropic" or model_type.startswith("claude"):
        logger.info("Initializing Anthropic Claude client")
        return AnthropicClient(api_key)
        
    elif model_type == "deepseek" or model_type.startswith("deepseek"):
        logger.info("Initializing DeepSeek client")
        return DeepSeekClient(api_key)
        
    else:
        raise ValueError(f"Unsupported model type: {model_type}")