import os
from typing import Dict, List, Optional, Any
import logging

try:
    import anthropic
    from anthropic import Anthropic, AI_PROMPT, HUMAN_PROMPT
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("Anthropic Python package not found. Install with 'pip install anthropic'")

from Clients.base import BaseClient, Message, ModelConfig, PromptStyle, PricingTier

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnthropicClient(BaseClient):
    """Client for Anthropic's Claude API."""

    def __init__(self, api_key=None, api_base=None):
        """Initialize the client with API key."""
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.api_base = api_base
        
        # Initialize client before parent initialization
        self.client = None
        if ANTHROPIC_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        
        super().__init__(api_key=self.api_key, api_base=self.api_base)
        
    def _get_model_configs(self) -> Dict[str, ModelConfig]:
        """Get model configurations for all supported Anthropic models."""
        return {
            "claude-3-7-sonnet": ModelConfig(
                name="claude-3-7-sonnet-20250219",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=200000,
                pricing=PricingTier(
                    input=3.0,  # $0.003 per 1K tokens = $3 per million
                    output=15.0, # $0.015 per 1K tokens = $15 per million
                    discount_hours=(22, 6),  # 10 PM to 6 AM discount
                    discount_percentage=0.20,  # 20% discount
                    cache_hit_discount=0.2,  # 80% discount for cache hits
                ),
            ),
            "claude-3-5-sonnet": ModelConfig(
                name="claude-3-5-sonnet-20241022",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=200000,
                pricing=PricingTier(
                    input=3.0,
                    output=15.0,
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "claude-3-5-haiku": ModelConfig(
                name="claude-3-5-haiku-20241022",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=200000,
                pricing=PricingTier(
                    input=0.8,  # $0.0008 per 1K tokens = $0.8 per million
                    output=4.0,  # $0.004 per 1K tokens = $4 per million
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "claude-3-opus": ModelConfig(
                name="claude-3-opus-20240229",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=200000,
                pricing=PricingTier(
                    input=15.0,  # $0.015 per 1K tokens = $15 per million
                    output=75.0,  # $0.075 per 1K tokens = $75 per million
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "claude-3-sonnet": ModelConfig(
                name="claude-3-sonnet-20240229",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=200000,
                pricing=PricingTier(
                    input=3.0,
                    output=15.0,
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "claude-3-haiku": ModelConfig(
                name="claude-3-haiku-20240307",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=200000,
                pricing=PricingTier(
                    input=0.25,  # $0.00025 per 1K tokens = $0.25 per million
                    output=1.25,  # $0.00125 per 1K tokens = $1.25 per million
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "claude-2.1": ModelConfig(
                name="claude-2.1",
                prompt_style=PromptStyle.USER_PREFIX,
                context_length=200000,
                pricing=PricingTier(
                    input=8.0,  # $0.008 per 1K tokens = $8 per million
                    output=24.0,  # $0.024 per 1K tokens = $24 per million
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            ),
            "claude-2": ModelConfig(
                name="claude-2",
                prompt_style=PromptStyle.USER_PREFIX,
                context_length=100000,
                pricing=PricingTier(
                    input=8.0,
                    output=24.0,
                    discount_hours=(22, 6),
                    discount_percentage=0.20,
                    cache_hit_discount=0.2,
                ),
            )
        }
    
    def _get_default_model(self) -> str:
        """Get the default model for Anthropic."""
        return "claude-3-5-sonnet"
    
    def _chat_completion_provider(self, messages, model, temperature=0.7, max_tokens=None, stream=False):
        """Generate a chat completion."""
        if not self.client:
            raise Exception("Anthropic package is required. Install with 'pip install anthropic'")
            
        model_config = self.get_model_config(model)
            
        system = None
        anthropic_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                role = "assistant" if msg.role == "assistant" else "user"
                anthropic_messages.append({"role": role, "content": msg.content})
            
        kwargs = {
            "model": model_config.name,
            "messages": anthropic_messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if system:
            kwargs["system"] = system
        
        if max_tokens is None:
            # Anthropic requires max_tokens to be set
            kwargs["max_tokens"] = 4000
        else:
            kwargs["max_tokens"] = max_tokens
                
        with self.rate_limiter:
            if stream:
                return self.client.messages.create(**kwargs)
            else:
                response = self.client.messages.create(**kwargs)
                
                self._update_usage_stats({
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "model": model
                })
                
                return response
    
    def _format_claude_prompt(self, messages: List[Message], system_prompt: Optional[str] = None) -> str:
        """Format messages into Claude's expected prompt format for Claude 2 models"""
        formatted_prompt = ""
        
        if system_prompt:
            formatted_prompt += f"{system_prompt}\n\n"
        
        for i, msg in enumerate(messages):
            content = msg.content or ""
            
            if msg.role == "user":
                if i > 0 and messages[i-1].role == "user":
                    formatted_prompt += f"\n\n{content}"
                else:
                    formatted_prompt += f"{HUMAN_PROMPT} {content}"
            elif msg.role == "assistant":
                formatted_prompt += f"{AI_PROMPT} {content}"
        
        if messages and messages[-1].role == "user":
            formatted_prompt += AI_PROMPT
            
        return formatted_prompt 