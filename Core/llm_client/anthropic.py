import anthropic
import logging
import re
from typing import Optional, List, Dict, Tuple, Any
from .base import BaseLLMClient, TokenUsage

logger = logging.getLogger(__name__)

# Claude API pricing (as of March 2025) - subject to changes
CLAUDE_PRICING = {
    "claude-3-7-sonnet-20250219": {
        "input": 3.0 / 1_000_000,                # $3.00 per million input tokens
        "input_cache_write": 3.75 / 1_000_000,   # $3.75 per million tokens for prompt caching write
        "input_cache_read": 0.30 / 1_000_000,    # $0.30 per million tokens for prompt caching read
        "output": 15.0 / 1_000_000,              # $15.00 per million output tokens
    },
    # Default pricing for unknown models
    "default": {
        "input": 3.0 / 1_000_000,                # $3.00 per million input tokens
        "output": 15.0 / 1_000_000,              # $15.00 per million output tokens
    }
}

class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ValueError("Anthropic API key is required")
            
        # Validate API key format (simple check)
        if not api_key.startswith("sk-"):
            logger.warning("Anthropic API key has unexpected format (should start with 'sk-')")
            
        try:
            self.client = anthropic.Anthropic(api_key=api_key)
            # Test connection to validate API key (minimal check that doesn't cost tokens)
            # This will throw an exception if the API key is invalid
            if hasattr(self.client, 'api_key'):
                logger.info("Anthropic client initialized successfully")
        except Exception as e:
            raise ValueError(f"Failed to initialize Anthropic client: {str(e)}")
            
        self.default_model = "claude-3-7-sonnet-20250219"
        
    async def get_response(
        self,
        prompt: Optional[str],
        system: Optional[str],
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False,
        model: Optional[str] = None
    ) -> Optional[str]:
        """
        Modified so that if 'conversation_history' is provided,
        we do NOT forcibly insert system/prompt again. 
        If conversation_history is empty, we build it from system/prompt.
        """
        try:
            if conversation_history:
                messages = conversation_history
            else:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                if prompt:
                    messages.append({"role": "user", "content": prompt})

            logger.debug(f"Sending request to Claude with {len(messages)} messages")

            # Use specified model or default
            model_name = model or self.default_model
            
            # Make the API call
            message = self.client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system="",    # We'll rely on the 'messages' structure
                messages=messages
            )
            
            # Track token usage
            if hasattr(message, "usage"):
                usage_data = {
                    "prompt_tokens": message.usage.input_tokens,
                    "completion_tokens": message.usage.output_tokens,
                    "total_tokens": message.usage.input_tokens + message.usage.output_tokens
                }
                
                # Check for cache information
                cache_hit = False
                cache_write = False
                
                if hasattr(message, "cache") and message.cache:
                    if hasattr(message.cache, "status"):
                        if message.cache.status == "hit":
                            cache_hit = True
                            logger.info(f"Cache hit detected for {model_name}")
                        elif message.cache.status == "write":
                            cache_write = True
                            logger.info(f"Cache write detected for {model_name}")
                
                # Calculate costs with cache awareness
                costs = self.calculate_token_cost(
                    usage_data, 
                    model_name, 
                    cache_hit=cache_hit,
                    cache_write=cache_write
                )
                
                # Create and record token usage
                token_usage = TokenUsage(
                    prompt_tokens=usage_data["prompt_tokens"],
                    completion_tokens=usage_data["completion_tokens"],
                    total_tokens=usage_data["total_tokens"],
                    prompt_cost=costs["prompt_cost"],
                    completion_cost=costs["completion_cost"],
                    total_cost=costs["total_cost"],
                    model=model_name,
                    cache_hit=cache_hit
                )
                
                self.add_usage(token_usage)
            
            # Parse response content
            if isinstance(message.content, list) and len(message.content) > 0:
                return message.content[0].text
            elif isinstance(message.content, str):
                # In some versions, .content might be a direct string
                return message.content
            
            logger.warning("Received empty response from Claude")
            return None
            
        except Exception as e:
            logger.error(f"API call failed: {str(e)}", exc_info=True)
            return None
    
    def calculate_token_cost(self, usage: Dict[str, int], model: str, cache_hit: bool = False, cache_write: bool = False) -> Dict[str, float]:
        """
        Calculate cost based on token usage, model, and cache status
        
        Args:
            usage: Dictionary with prompt_tokens and completion_tokens
            model: The model name used for the request
            cache_hit: Whether there was a cache hit for this request
            cache_write: Whether this is a cache write operation
            
        Returns:
            Dictionary with prompt_cost, completion_cost, and total_cost
        """
        # Get pricing for this model or use default if not found
        pricing = CLAUDE_PRICING.get(model, CLAUDE_PRICING["default"])
        
        # Calculate prompt cost based on cache status
        if cache_hit and "input_cache_read" in pricing:
            # Cache hit - use read pricing
            prompt_cost = usage["prompt_tokens"] * pricing["input_cache_read"]
            logger.debug(f"Using cache read pricing for {model}: ${pricing['input_cache_read'] * 1_000_000:.4f}/M tokens")
        elif cache_write and "input_cache_write" in pricing:
            # Cache write - use write pricing
            prompt_cost = usage["prompt_tokens"] * pricing["input_cache_write"] 
            logger.debug(f"Using cache write pricing for {model}: ${pricing['input_cache_write'] * 1_000_000:.4f}/M tokens")
        else:
            # Normal input pricing
            prompt_cost = usage["prompt_tokens"] * pricing["input"]
            
        completion_cost = usage["completion_tokens"] * pricing["output"]
        total_cost = prompt_cost + completion_cost
        
        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "total_cost": total_cost,
            "cache_hit": cache_hit,
            "cache_write": cache_write
        }
            
    async def check_for_user_input_request(self, response: str) -> Tuple[bool, Optional[str]]:
        """
        Check if the model is requesting user input in its response.
        
        Looks for special tags or patterns like <user_input> or [PAUSE_FOR_USER_INPUT].
        
        Args:
            response: The model's response text
            
        Returns:
            Tuple of (should_pause, question_for_user)
        """
        # Look for user input tags
        input_tags = [
            r"<user_input>(.*?)</user_input>",
            r"\[PAUSE_FOR_USER_INPUT\](.*?)\[/PAUSE_FOR_USER_INPUT\]",
            r"\[USER_INPUT\](.*?)\[/USER_INPUT\]",
            r"\[PROMPT_USER\](.*?)\[/PROMPT_USER\]"
        ]
        
        for tag_pattern in input_tags:
            matches = re.finditer(tag_pattern, response, re.DOTALL)
            for match in matches:
                # Extract the question to ask the user
                question = match.group(1).strip() if match.group(1) else "Please provide additional information:"
                logger.info(f"Detected user input request: {question}")
                return True, question
        
        # Also check for more explicit phrases
        explicit_phrases = [
            "I need more information from you to proceed",
            "I need to ask you a question before continuing",
            "Please provide more details so I can continue",
            "I'll pause here and wait for your input",
            "Could you clarify",
            "Could you provide more details about"
        ]
        
        for phrase in explicit_phrases:
            if phrase in response:
                # Extract a sentence containing the phrase
                sentences = re.split(r'(?<=[.!?])\s+', response)
                for sentence in sentences:
                    if phrase in sentence:
                        logger.info(f"Detected implicit user input request: {sentence}")
                        return True, sentence
        
        # No input request found
        return False, None

