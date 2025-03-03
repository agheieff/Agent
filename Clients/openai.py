import openai
import logging
from typing import Optional, List, Dict, Tuple, Any
from .base_client import BaseLLMClient, TokenUsage

logger = logging.getLogger(__name__)

# Pricing per million tokens
OPENAI_PRICING = {
    "gpt-4.5-preview": {
         "input": 75.00 / 1_000_000,
         "input_cache_read": 37.50 / 1_000_000,
         "input_cache_write": 37.50 / 1_000_000,
         "output": 150.00 / 1_000_000,
    },
    "gpt-4o": {
         "input": 2.50 / 1_000_000,
         "input_cache_read": 1.25 / 1_000_000,
         "input_cache_write": 1.25 / 1_000_000,
         "output": 10.00 / 1_000_000,
    },
    "o1": {
         "input": 15.00 / 1_000_000,
         "input_cache_read": 7.50 / 1_000_000,
         "input_cache_write": 7.50 / 1_000_000,
         "output": 60.00 / 1_000_000,
    },
    "o3-mini": {
         "input": 1.10 / 1_000_000,
         "input_cache_read": 0.55 / 1_000_000,
         "input_cache_write": 0.55 / 1_000_000,
         "output": 4.40 / 1_000_000,
    },
    "default": {
         "input": 2.50 / 1_000_000,
         "input_cache_read": 1.25 / 1_000_000,
         "input_cache_write": 1.25 / 1_000_000,
         "output": 10.00 / 1_000_000,
    }
}

class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str, model: Optional[str] = None):
        super().__init__()
        if not api_key:
            raise ValueError("OpenAI API key is required")
        openai.api_key = api_key
        # Default model: "o1" if not specified
        self.default_model = model or "o1"

    def get_model_pricing(self, model: str) -> Dict[str, float]:
        return OPENAI_PRICING.get(model, OPENAI_PRICING["default"])

    def adjust_prompts(self, system_prompt: Optional[str], user_prompt: str) -> Tuple[Optional[str], str]:
        # For OpenAI Chat models, we keep system and user messages separate.
        return (system_prompt, user_prompt)

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
        try:
            if conversation_history:
                messages = conversation_history
            else:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                if prompt:
                    messages.append({"role": "user", "content": prompt})
            logger.debug(f"Sending request to OpenAI with {len(messages)} messages")

            model_name = model or self.default_model

            response = openai.ChatCompletion.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            usage_data = None
            if response and hasattr(response, "usage"):
                usage_data = {
                    "prompt_tokens": response.usage.get("prompt_tokens", 0),
                    "completion_tokens": response.usage.get("completion_tokens", 0),
                    "total_tokens": response.usage.get("total_tokens", 0)
                }
                model_pricing = self.get_model_pricing(model_name)
                costs = self.calculate_token_cost(usage_data, model_pricing)
                token_usage = TokenUsage(
                    prompt_tokens=usage_data["prompt_tokens"],
                    completion_tokens=usage_data["completion_tokens"],
                    total_tokens=usage_data["total_tokens"],
                    prompt_cost=costs["prompt_cost"],
                    completion_cost=costs["completion_cost"],
                    total_cost=costs["total_cost"],
                    model=model_name,
                    cache_hit=False
                )
                self.add_usage(token_usage)

            if response and response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                content = message.get("content", "")
                return content
            return None

        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}", exc_info=True)
            return None

    async def generate_response(self, conversation_history: List[Dict]) -> str:
        try:
            response = await self.get_response(
                prompt=None,
                system=None,
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
        return False, None
