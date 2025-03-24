import os
import logging
from typing import Dict, Optional, Any

try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI Python package not found. Install with 'pip install openai'")

from Clients.base import BaseClient, Message, ModelConfig, PromptStyle, PricingTier

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenAIClient(BaseClient):
    """Client for OpenAI's API."""

    def __init__(self, api_key=None, api_base=None):
        """Initialize the client with API key."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("OPENAI_API_BASE")
        
        self.client = None
        if OPENAI_AVAILABLE and self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
            
        super().__init__(api_key=self.api_key, api_base=self.api_base)
    
    def _get_model_configs(self) -> Dict[str, ModelConfig]:
        """Get model configurations for all supported OpenAI models."""
        return {
            "gpt-4": ModelConfig(
                name="gpt-4",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=8192,
                pricing=PricingTier(
                    input=30.0,  # $0.03 per 1K tokens = $30 per million
                    output=60.0,  # $0.06 per 1K tokens = $60 per million
                    discount_hours=(22, 6),  # 10 PM to 6 AM discount
                    discount_percentage=0.20,  # 20% discount
                    cache_hit_discount=0.2,  # 80% discount for cache hits
                ),
            ),
            "gpt-4-turbo": ModelConfig(
                name="gpt-4-turbo-preview",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=128000,
                pricing=PricingTier(
                    input=10.0,  # $0.01 per 1K tokens = $10 per million
                    output=30.0,  # $0.03 per 1K tokens = $30 per million
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "gpt-4-1106-preview": ModelConfig(
                name="gpt-4-1106-preview",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=128000,
                pricing=PricingTier(
                    input=10.0,
                    output=30.0,
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "gpt-4-0125-preview": ModelConfig(
                name="gpt-4-0125-preview",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=128000,
                pricing=PricingTier(
                    input=10.0,
                    output=30.0,
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "gpt-4-vision-preview": ModelConfig(
                name="gpt-4-vision-preview",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=128000,
                pricing=PricingTier(
                    input=10.0,
                    output=30.0,
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "gpt-4o": ModelConfig(
                name="gpt-4o",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=128000,
                pricing=PricingTier(
                    input=5.0,  # $0.005 per 1K tokens = $5 per million
                    output=15.0,  # $0.015 per 1K tokens = $15 per million
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
        }
    
    def _get_default_model(self) -> str:
        """Get the default model for OpenAI."""
        return "gpt-4o"
    
    def _chat_completion_provider(
        self, 
        messages, 
        model, 
        temperature=0.7, 
        max_tokens=None, 
        stream=False,
        top_p=1.0, 
        tools=None, 
        tool_choice=None, 
        json_mode=False,
        response_format=None
    ):
        if not self.client:
            raise Exception("OpenAI package is required. Install with 'pip install openai'")
            
        openai_messages = []
        for msg in messages:
            if msg.role == "function":
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.function_call_id,
                })
            else:
                openai_message = {"role": msg.role, "content": msg.content}
                if msg.name:
                    openai_message["name"] = msg.name
                    
                openai_messages.append(openai_message)
                
        kwargs = {
            "model": self.get_model_config(model).name,
            "messages": openai_messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
            
        if top_p is not None:
            kwargs["top_p"] = top_p
            
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        elif response_format:
            kwargs["response_format"] = response_format
            
        if tools:
            kwargs["tools"] = tools
            
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
                
        with self.rate_limiter:
            if stream:
                return self.client.chat.completions.create(**kwargs)
            else:
                response = self.client.chat.completions.create(**kwargs)
                
                if hasattr(response, "usage"):
                    self._update_usage_stats({
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "model": model
                    })
                
                return response
    
    def chat_completion(self, messages, model=None, system_prompt=None,
                       temperature=0.7, max_tokens=None, stream=False,
                       top_p=1.0, tools=None, tool_choice=None, json_mode=False,
                       response_format=None):
        """Generate a chat completion."""
        # Use default model if none provided
        model = model or self._get_default_model()
        
        return self._chat_completion_provider(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            top_p=top_p,
            tools=tools,
            tool_choice=tool_choice,
            json_mode=json_mode,
            response_format=response_format
        ) 