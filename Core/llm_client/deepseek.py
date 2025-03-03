import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from openai import OpenAI
from .base import BaseLLMClient, TokenUsage

logger = logging.getLogger(__name__)

# DeepSeek API pricing (as of March 2025) - subject to changes
DEEPSEEK_PRICING = {
    "deepseek-reasoner": {
        "input": 0.14 / 1_000_000,     # $0.14 per million input tokens
        "input_cache_hit": 0.05 / 1_000_000,  # $0.05 per million tokens for cache hits
        "input_cache_miss": 0.14 / 1_000_000,  # $0.14 per million tokens for cache misses
        "output": 2.19 / 1_000_000,    # $2.19 per million output tokens
        "discount_hours": (16, 30, 0, 30),  # 75% discount between 16:30 and 00:30 UTC
        "discount_rate": 0.75,  # 75% discount during specified hours
    },
    "deepseek-reasoner-tools": {
        "input": 0.14 / 1_000_000,     # $0.14 per million input tokens 
        "input_cache_hit": 0.05 / 1_000_000,  # $0.05 per million tokens for cache hits
        "input_cache_miss": 0.14 / 1_000_000,  # $0.14 per million tokens for cache misses
        "output": 2.19 / 1_000_000,    # $2.19 per million output tokens
        "discount_hours": (16, 30, 0, 30),  # 75% discount between 16:30 and 00:30 UTC
        "discount_rate": 0.75,  # 75% discount during specified hours
    },
    # Default pricing for unknown models
    "default": {
        "input": 0.14 / 1_000_000,     # $0.14 per million input tokens
        "output": 2.19 / 1_000_000,    # $2.19 per million output tokens
    }
}

class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ValueError("DeepSeek API key is required")
            
        # Validate API key format
        if len(api_key) < 10:  # Simple length check
            logger.warning("DeepSeek API key may be invalid (too short)")
            
        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            # Minimal check that the client was initialized
            if hasattr(self.client, 'api_key'):
                logger.info("DeepSeek client initialized successfully")
        except Exception as e:
            raise ValueError(f"Failed to initialize DeepSeek client: {str(e)}")
            
        self.default_model = "deepseek-reasoner"
        
    async def generate_response(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Generate a response from the DeepSeek model using the provided conversation history.
        
        Args:
            conversation_history: List of conversation messages with role and content.
                                  Example: [{"role": "system", "content": "..."}, ...]
                                  
        Returns:
            The generated response text
        """
        # Extract system prompt if present
        system_prompt = None
        if conversation_history and conversation_history[0]["role"] == "system":
            system_prompt = conversation_history[0]["content"]
        
        # Get the user's last message as prompt
        prompt = None
        for msg in reversed(conversation_history):
            if msg["role"] == "user":
                prompt = msg["content"]
                break
                
        # DeepSeek models require alternating user and assistant messages
        # Fix the conversation history to ensure this pattern
        fixed_messages = []
        
        # Always include system message first if it exists
        if conversation_history and conversation_history[0]["role"] == "system":
            fixed_messages.append(conversation_history[0])
            conversation_history = conversation_history[1:]
            
        # Ensure messages alternate properly with stricter validation
        last_role = None
        for msg in conversation_history:
            role = msg["role"]
            
            # System messages can only appear at the start
            if role == "system" and fixed_messages:
                logger.warning(f"Skipping system message that's not at the start")
                continue
                
            # Skip consecutive messages with the same role
            if role == last_role:
                logger.warning(f"Skipping consecutive {role} message to maintain proper alternation")
                continue
                
            # Enforce strict alternation between user and assistant
            if last_role == "user" and role != "assistant":
                logger.warning(f"Expected assistant message after user, got {role}. Skipping.")
                continue
                
            if last_role == "assistant" and role != "user":
                logger.warning(f"Expected user message after assistant, got {role}. Skipping.")
                continue
                
            # If this is the first non-system message, it must be from the user
            if last_role is None and fixed_messages and role != "user":
                logger.warning(f"First message after system must be from user, got {role}. Skipping.")
                continue
                
            fixed_messages.append(msg)
            last_role = role
            
        # Ensure the last message is from the user
        if fixed_messages and fixed_messages[-1]["role"] != "user":
            logger.warning("Last message must be from user - removing trailing assistant message")
            fixed_messages = fixed_messages[:-1]
            
        # If we still have no messages, use the prompt directly
        if not fixed_messages or (len(fixed_messages) == 1 and fixed_messages[0]["role"] == "system"):
            if system_prompt:
                fixed_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt or "Hello, please respond."}
                ]
            else:
                fixed_messages = [
                    {"role": "user", "content": prompt or "Hello, please respond."}
                ]
                
        logger.info(f"Using {len(fixed_messages)} fixed messages for DeepSeek request")
        # Log message structure for debugging
        roles_sequence = [msg["role"] for msg in fixed_messages]
        logger.info(f"Message roles sequence: {roles_sequence}")
        
        # Get the response using the fixed conversation history
        response = await self.get_response(
            prompt=None,  # We're using conversation_history instead
            system=None,  # We're using conversation_history instead
            conversation_history=fixed_messages,
            temperature=0.7,
            max_tokens=4000
        )
        
        if response is None:
            return "I apologize, but I'm having trouble generating a response right now. Please try again."
            
        return response
        
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
        we do NOT forcibly insert system or user from prompt/system.
        That helps avoid repeated or "successive" user/system messages.
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

            logger.debug(f"Sending request to DeepSeek-Reasoner with {len(messages)} messages")
            
            # Use specified model or default based on tool usage
            model_name = model or ("deepseek-reasoner-tools" if tool_usage else self.default_model)
            
            if tool_usage:
                # Approach for function calling or tool usage
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    functions=[{
                        "name": "my_tool",
                        "description": "Example tool usage placeholder",
                        "parameters": {}
                    }],
                    function_call="auto"
                )
            else:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            
            # Track token usage if available
            if hasattr(response, "usage"):
                usage_data = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                
                # Check if this was a cache hit (if the API provides this info)
                cache_hit = False
                if hasattr(response, "cached") and response.cached:
                    cache_hit = True
                    logger.debug(f"Cache hit detected for request to {model_name}")
                
                # Calculate costs with cache awareness
                costs = self.calculate_token_cost(usage_data, model_name, cache_hit=cache_hit)
                
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
                
                # Log if discount was applied
                if "discount_applied" in costs and costs["discount_applied"]:
                    logger.info(f"Applied time-based discount to {model_name} request")
                
                self.add_usage(token_usage)
            
            if response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                # Some models might separate a 'reasoning_content'
                # For now we assume it might exist:
                reasoning_content = getattr(message, 'reasoning_content', None)
                content = message.content
                
                # Log reasoning chain for debugging if present
                if reasoning_content:
                    logger.debug(f"Reasoning Chain:\n{reasoning_content}")
                
                return content
                
            logger.warning("Received empty response from DeepSeek-Reasoner")
            return None
                    
        except Exception as e:
            logger.error(f"DeepSeek-Reasoner API call failed: {str(e)}", exc_info=True)
            return None
    
    def calculate_token_cost(self, usage: Dict[str, int], model: str, cache_hit: bool = False) -> Dict[str, float]:
        """
        Calculate cost based on token usage, model, and time of day.
        
        Args:
            usage: Dictionary with prompt_tokens, completion_tokens, and total_tokens
            model: The model name used for the request
            cache_hit: Whether there was a cache hit for this request
        
        Returns:
            Dictionary with prompt_cost, completion_cost, and total_cost
        """
        import datetime
        import time
        
        # Get pricing for this model or use default if not found
        pricing = DEEPSEEK_PRICING.get(model, DEEPSEEK_PRICING["default"])
        
        # Determine if we're in discount hours
        discount_applied = False
        discount_multiplier = 1.0
        
        if "discount_hours" in pricing and "discount_rate" in pricing:
            # Get current UTC time
            current_time = datetime.datetime.now(datetime.timezone.utc)
            current_hour = current_time.hour
            current_minute = current_time.minute
            
            # Unpack the discount hours tuple (start_hour, start_minute, end_hour, end_minute)
            start_hour, start_minute, end_hour, end_minute = pricing["discount_hours"]
            
            # Convert to minutes for easier comparison
            current_time_mins = current_hour * 60 + current_minute
            start_time_mins = start_hour * 60 + start_minute
            end_time_mins = end_hour * 60 + end_minute
            
            # Handle the case where discount period crosses midnight
            if end_time_mins < start_time_mins:
                # If current time is after start OR before end, we're in the discount period
                if current_time_mins >= start_time_mins or current_time_mins <= end_time_mins:
                    discount_applied = True
                    discount_multiplier = 1.0 - pricing["discount_rate"]
            else:
                # Normal case: if current time is between start and end
                if start_time_mins <= current_time_mins <= end_time_mins:
                    discount_applied = True
                    discount_multiplier = 1.0 - pricing["discount_rate"]
        
        # Calculate costs with appropriate pricing
        if cache_hit and "input_cache_hit" in pricing:
            prompt_cost = usage["prompt_tokens"] * pricing["input_cache_hit"] * discount_multiplier
        elif not cache_hit and "input_cache_miss" in pricing:
            prompt_cost = usage["prompt_tokens"] * pricing["input_cache_miss"] * discount_multiplier
        else:
            prompt_cost = usage["prompt_tokens"] * pricing["input"] * discount_multiplier
            
        completion_cost = usage["completion_tokens"] * pricing["output"] * discount_multiplier
        total_cost = prompt_cost + completion_cost
        
        # Add logging for cost calculation
        if discount_applied:
            logger.debug(f"Applied {pricing['discount_rate']*100}% discount to {model} pricing (discount hours active)")
        
        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "total_cost": total_cost,
            "discount_applied": discount_applied
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
