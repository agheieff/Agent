import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from openai import OpenAI
from .base import BaseLLMClient, TokenUsage

logger = logging.getLogger(__name__)

# DeepSeek API pricing (as of March 2025) - subject to changes
DEEPSEEK_PRICING = {
    "deepseek-reasoner": {
        "input": 0.20 / 1_000_000,     # $0.20 per million input tokens
        "output": 0.80 / 1_000_000,    # $0.80 per million output tokens
    },
    "deepseek-reasoner-tools": {
        "input": 0.20 / 1_000_000,     # $0.20 per million input tokens
        "output": 0.80 / 1_000_000,    # $0.80 per million output tokens
    },
    # Default pricing for unknown models
    "default": {
        "input": 0.20 / 1_000_000,     # $0.20 per million input tokens
        "output": 0.80 / 1_000_000,    # $0.80 per million output tokens
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
                
                # Calculate costs
                costs = self.calculate_token_cost(usage_data, model_name)
                
                # Create and record token usage
                token_usage = TokenUsage(
                    prompt_tokens=usage_data["prompt_tokens"],
                    completion_tokens=usage_data["completion_tokens"],
                    total_tokens=usage_data["total_tokens"],
                    prompt_cost=costs["prompt_cost"],
                    completion_cost=costs["completion_cost"],
                    total_cost=costs["total_cost"],
                    model=model_name
                )
                
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
    
    def calculate_token_cost(self, usage: Dict[str, int], model: str) -> Dict[str, float]:
        """Calculate cost based on token usage and model"""
        # Get pricing for this model or use default if not found
        pricing = DEEPSEEK_PRICING.get(model, DEEPSEEK_PRICING["default"])
        
        prompt_cost = usage["prompt_tokens"] * pricing["input"]
        completion_cost = usage["completion_tokens"] * pricing["output"]
        total_cost = prompt_cost + completion_cost
        
        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "total_cost": total_cost
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
