import anthropic
import logging
import re
from typing import Optional, List, Dict, Tuple, Any
from .base_client import BaseLLMClient, TokenUsage

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
            # Initialize client with keyword arguments as required by the library
            self.client = anthropic.Anthropic(api_key=api_key)
            
            # Check if the client was properly initialized
            if not hasattr(self.client, 'api_key') and not hasattr(self.client, 'completions'):
                # Try the older API format
                try:
                    import anthropic.AI_PROMPT as AI_PROMPT
                    logger.info("Detected older Anthropic API version, using compatible initialization")
                    self.client = anthropic.Client(api_key=api_key)
                    self.using_old_api = True
                except (ImportError, AttributeError) as e:
                    logger.warning(f"Failed to initialize using old API: {e}")
                    self.using_old_api = False
            else:
                self.using_old_api = False
                
            logger.info(f"Anthropic client initialized successfully (using_old_api={self.using_old_api})")
        except Exception as e:
            logger.error(f"Error initializing Anthropic client: {str(e)}", exc_info=True)
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
            
            # Use the appropriate API based on the client and library version
            if not self.using_old_api and hasattr(self.client, 'messages'):
                # New version of Anthropic library with messages
                try:
                    message = self.client.messages.create(
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system="",    # We'll rely on the 'messages' structure
                        messages=messages
                    )
                except Exception as e:
                    # If messages API fails, try completions API as fallback
                    logger.warning(f"Messages API failed: {e}, trying completions API as fallback")
                    self.using_old_api = True
                
            # If using old API or messages API failed
            if self.using_old_api or not hasattr(self.client, 'messages'):
                # Extract system prompt and user message from conversation history
                system_prompt = ""
                if system:
                    system_prompt = system
                else:
                    # Extract system prompt from conversation history if present
                    for msg in messages:
                        if msg.get("role") == "system":
                            system_prompt = msg.get("content", "")
                            break
                
                # Convert the conversation to the older format with Human/Assistant tags
                # Find the most recent user message
                human_prompt = ""
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        human_prompt = msg.get("content", "")
                        break
                
                # Format prompt for Claude using older API
                if hasattr(anthropic, 'AI_PROMPT') and hasattr(anthropic, 'HUMAN_PROMPT'):
                    # Use constants from anthropic library
                    prompt = f"{anthropic.HUMAN_PROMPT} {human_prompt}{anthropic.AI_PROMPT}"
                else:
                    # Use hardcoded prompts
                    prompt = f"\n\nHuman: {human_prompt}\n\nAssistant:"
                
                # Try to use the completions API
                if hasattr(self.client, 'completions'):
                    # New API with completions
                    message = self.client.completions.create(
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        prompt=prompt
                    )
                else:
                    # Older Client API
                    message = self.client.completion(
                        prompt=prompt,
                        model=model_name,
                        max_tokens_to_sample=max_tokens,
                        temperature=temperature
                    )
            
            # Track token usage based on API version
            usage_data = None
            cache_hit = False
            cache_write = False
            
            if hasattr(message, "usage"):
                # New API with message.usage
                usage_data = {
                    "prompt_tokens": message.usage.input_tokens,
                    "completion_tokens": message.usage.output_tokens,
                    "total_tokens": message.usage.input_tokens + message.usage.output_tokens
                }
                
                # Check for cache information
                if hasattr(message, "cache") and message.cache:
                    if hasattr(message.cache, "status"):
                        if message.cache.status == "hit":
                            cache_hit = True
                            logger.info(f"Cache hit detected for {model_name}")
                        elif message.cache.status == "write":
                            cache_write = True
                            logger.info(f"Cache write detected for {model_name}")
            elif hasattr(message, "usage"):
                # Old API with message.usage
                usage_data = {
                    "prompt_tokens": message.usage.prompt_tokens,
                    "completion_tokens": message.usage.completion_tokens,
                    "total_tokens": message.usage.prompt_tokens + message.usage.completion_tokens
                }
            else:
                # Estimate if not available
                logger.warning("Token usage not available from API, using estimation")
                if prompt:
                    estimated_prompt_tokens = len(prompt.split()) * 1.3
                else:
                    estimated_prompt_tokens = sum([len(m.get("content", "").split()) * 1.3 for m in messages])
                
                if hasattr(message, "completion"):
                    estimated_completion_tokens = len(message.completion.split()) * 1.3
                elif hasattr(message, "content") and isinstance(message.content, str):
                    estimated_completion_tokens = len(message.content.split()) * 1.3
                else:
                    estimated_completion_tokens = 100  # Default fallback
                
                usage_data = {
                    "prompt_tokens": int(estimated_prompt_tokens),
                    "completion_tokens": int(estimated_completion_tokens),
                    "total_tokens": int(estimated_prompt_tokens + estimated_completion_tokens)
                }
            
            # If we have usage data, calculate costs and record
            if usage_data:
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
            
            # Parse response content based on API and message version
            try:
                # New API with messages content array
                if hasattr(message, 'content') and isinstance(message.content, list) and len(message.content) > 0:
                    if hasattr(message.content[0], 'text'):
                        return message.content[0].text
                    elif isinstance(message.content[0], dict) and 'text' in message.content[0]:
                        return message.content[0]['text']
                    
                # New API with string content
                elif hasattr(message, 'content') and isinstance(message.content, str):
                    return message.content
                    
                # New API with completions
                elif hasattr(message, 'completion'):
                    return message.completion
                    
                # Old API client.completion() response
                elif isinstance(message, dict) and 'completion' in message:
                    return message['completion']
                    
                # Old API direct text response
                elif isinstance(message, str):
                    return message
                    
                # Try various attribute access patterns as a last resort
                for attr in ['text', 'content', 'completion', 'message', 'response']:
                    if hasattr(message, attr):
                        attr_value = getattr(message, attr)
                        if isinstance(attr_value, str) and attr_value:
                            return attr_value
                            
                # If we got here, we couldn't parse the response
                logger.warning(f"Could not parse Claude response format: {type(message)}")
                if isinstance(message, dict):
                    logger.debug(f"Available keys: {message.keys()}")
                elif hasattr(message, '__dict__'):
                    logger.debug(f"Available attributes: {dir(message)}")
                    
                # Return string representation as last resort
                return str(message)
            except Exception as e:
                logger.error(f"Error parsing Claude response: {e}")
                return f"Error parsing response: {e}"
            
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
            
    async def generate_response(self, conversation_history: List[Dict]) -> str:
        """
        Generate a response from the model using the conversation history.
        This is a wrapper around get_response to match the interface expected by the agent.
        
        Args:
            conversation_history: List of message dictionaries with role and content keys
            
        Returns:
            String response from the model or error message
        """
        try:
            # Extract system message if present
            system = ""
            for msg in conversation_history:
                if msg.get("role") == "system":
                    system = msg.get("content", "")
                    break
            
            # Call get_response with the conversation history
            response = await self.get_response(
                prompt=None,
                system=None,  # We'll use the one in conversation_history
                conversation_history=conversation_history,
                temperature=0.5,
                max_tokens=4096
            )
            
            if response is None:
                return "I encountered an error generating a response. Please try again."
                
            return response
        except Exception as e:
            logger.error(f"Error in generate_response: {str(e)}")
            return f"I encountered an error generating a response: {str(e)}"
    
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