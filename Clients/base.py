from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
import logging
import time
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PromptStyle(Enum):
    """Defines how system prompts should be handled for different models"""
    SYSTEM_MESSAGE = "system_message"  # Model accepts a separate system message
    PREPEND_TO_USER = "prepend_to_user"  # System message is prepended to the first user message
    USER_PREFIX = "user_prefix"  # System message is prepended to the user prompt


@dataclass
class Message:
    """Represents a message in a conversation"""
    role: str  # "system", "user", "assistant"
    content: str
    name: Optional[str] = None
    function_call_id: Optional[str] = None


@dataclass
class PricingTier:
    """Pricing information for a model"""
    input: float  # Cost per million tokens for input
    output: float  # Cost per million tokens for output
    discount_hours: Optional[Tuple[int, int]] = None  # (start_hour, end_hour) for discount period
    discount_percentage: float = 0.0  # Discount percentage (0.0-1.0)
    cache_hit_discount: float = 1.0  # Multiplier for cache hits (1.0 = no discount, 0.0 = free)


@dataclass
class ModelConfig:
    name: str
    prompt_style: PromptStyle
    context_length: int
    pricing: PricingTier


@dataclass
class UsageStats:
    """Track token usage and costs"""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    cache_hit: bool = False


class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self.last_call_time = 0

    def __enter__(self):
        """Context manager entry - apply rate limiting"""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            logger.debug(f"Rate limit: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - update last call time"""
        self.last_call_time = time.time()


class BaseClient:
    """Base class for LLM API clients."""
    
    def __init__(self, api_key=None, api_base=None):
        """Initialize the client."""
        self.api_key = api_key
        self.api_base = api_base
        
        # Model configurations - populated by _get_model_configs()
        self.models = {}
        
        # Load model configurations
        model_configs = self._get_model_configs()
        for model_id, config in model_configs.items():
            self.models[model_id] = config
            
        # Set default model
        self.default_model = self._get_default_model()
        
        # Set up rate limiting
        self.rate_limiter = RateLimiter()
        
        # Initialize usage tracking
        self.usage_stats = []
        
    def _get_model_configs(self) -> Dict[str, ModelConfig]:
        """
        Get model configurations. 
        This must be implemented by subclasses to define their available models.
        """
        raise NotImplementedError("Subclasses must implement _get_model_configs")
    
    def _get_default_model(self) -> str:
        """Get the default model for this provider."""
        # Default implementation, can be overridden by subclasses
        models = list(self._get_model_configs().keys())
        return models[0] if models else None
        
    def get_available_models(self) -> List[str]:
        """
        Return a list of all available models for this provider.
        
        Returns:
            List of model names
        """
        return list(self.models.keys())
    
    def get_model_config(self, model_name: str) -> ModelConfig:
        """
        Get configuration for a specific model
        
        Args:
            model_name: The name of the model
            
        Returns:
            ModelConfig object
        """
        model_name = model_name or self.default_model
        
        if model_name not in self.models:
            available_models = ", ".join(self.models.keys()) if self.models else "none"
            raise ValueError(f"Unknown model: {model_name}. Available models: {available_models}")
            
        return self.models[model_name]
    
    def _handle_system_prompt(self, messages: List[Message], system_prompt: Optional[str], model: str) -> List[Message]:
        """
        Handle system prompt based on model's requirements.
        
        Args:
            messages: List of messages
            system_prompt: System prompt text
            model: Model name
            
        Returns:
            Processed messages with system prompt applied according to model requirements
        """
        if not system_prompt:
            return messages.copy()
            
        model_config = self.get_model_config(model)
        
        # Make a copy to avoid modifying the original
        result = messages.copy()
        
        # For models that support system messages directly
        if model_config.prompt_style == PromptStyle.SYSTEM_MESSAGE:
            # Check if there's already a system message
            has_system_message = any(msg.role == "system" for msg in result)
            
            if not has_system_message:
                # Insert system message at the beginning
                result.insert(0, Message(role="system", content=system_prompt))
                
        # For models that expect system message prepended to user prompt
        elif model_config.prompt_style == PromptStyle.PREPEND_TO_USER:
            # Find the first user message
            for i, msg in enumerate(result):
                if msg.role == "user":
                    # Prepend system prompt to user message
                    result[i] = Message(
                        role="user",
                        content=f"{system_prompt}\n\n{msg.content}",
                        name=msg.name
                    )
                    break
                    
        # For models that use prefixes like Claude 2
        elif model_config.prompt_style == PromptStyle.USER_PREFIX:
            # Handle in the specific client implementation
            pass
            
        return result
    
    def _update_usage_stats(self, usage_data: Dict[str, Any], cache_hit: bool = False):
        """
        Update usage statistics.
        
        Args:
            usage_data: Dict with prompt_tokens, completion_tokens, and model
            cache_hit: Whether this was a cache hit
        """
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        model = usage_data.get("model", self.default_model)
        
        # Calculate cost
        cost = self.calculate_cost(model, prompt_tokens, completion_tokens, cache_hit=cache_hit)
        
        # Record usage
        usage = UsageStats(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            input_cost=cost["input_cost"],
            output_cost=cost["output_cost"],
            total_cost=cost["total_cost"],
            timestamp=datetime.now(),
            cache_hit=cache_hit
        )
        
        self.usage_stats.append(usage)
        
        return usage

    def chat_completion(self, messages, model=None, system_prompt=None, temperature=0.7, 
                       max_tokens=None, stream=False):
        """
        Generate a chat completion.
        
        Args:
            messages: List of Message objects
            model: Model name to use (or default if None)
            system_prompt: System prompt to prepend (if applicable)
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            
        Returns:
            Model response
        """
        model = model or self.default_model
        
        processed_messages = self._handle_system_prompt(messages, system_prompt, model)
        
        return self._chat_completion_provider(
            processed_messages, 
            model, 
            temperature, 
            max_tokens, 
            stream
        )
    
    @abstractmethod
    def _chat_completion_provider(self, messages, model, temperature, max_tokens, stream):
        """
        Provider-specific implementation for chat completion.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _chat_completion_provider")
    
    def calculate_cost(
        self, 
        model_name: str, 
        prompt_tokens: int, 
        completion_tokens: int,
        timestamp: Optional[datetime] = None,
        cache_hit: bool = False
    ) -> Dict[str, float]:
        """Calculate the cost of a request based on token usage"""
        timestamp = timestamp or datetime.now()
        current_hour = timestamp.hour
        
        if model_name not in self.models:
            logger.warning(f"No pricing information available for model {model_name}")
            return {
                "input_cost": 0.0,
                "output_cost": 0.0, 
                "total_cost": 0.0
            }
        
        pricing = self.models[model_name].pricing
        
        # Apply cache hit discount if applicable
        input_multiplier = pricing.cache_hit_discount if cache_hit else 1.0
        output_multiplier = pricing.cache_hit_discount if cache_hit else 1.0
        
        # Apply time-based discount if applicable
        if pricing.discount_hours and pricing.discount_percentage > 0:
            start_hour, end_hour = pricing.discount_hours
            if start_hour <= current_hour < end_hour:
                discount = 1.0 - pricing.discount_percentage
                input_multiplier *= discount
                output_multiplier *= discount
        
        # Calculate costs based on price per million tokens
        input_cost = (prompt_tokens / 1_000_000) * pricing.input * input_multiplier
        output_cost = (completion_tokens / 1_000_000) * pricing.output * output_multiplier
        total_cost = input_cost + output_cost
        
        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost
        }

    def handle_rate_limits(self):
        """Handle rate limiting before making API calls"""
        self.rate_limiter.wait_if_needed() 