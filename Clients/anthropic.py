import anthropic
import logging
from typing import Optional, List, Dict, Tuple, Any
from .base_client import BaseLLMClient, TokenUsage

logger = logging.getLogger(__name__)

CLAUDE_PRICING = {
    "claude-3-7-sonnet-20250219": {
        "input": 3.0 / 1_000_000,
        "input_cache_write": 3.75 / 1_000_000,
        "input_cache_read": 0.30 / 1_000_000,
        "output": 15.0 / 1_000_000,
    },
    "default": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
    }
}

class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ValueError("Anthropic API key is required")

        if not api_key.startswith("sk-"):
            logger.warning("Anthropic API key has unexpected format (should start with 'sk-')")

        try:
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info("Anthropic client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Anthropic client: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to initialize Anthropic client: {str(e)}")

        self.default_model = "claude-3-7-sonnet-20250219"

    def get_model_pricing(self, model: str) -> Dict[str, float]:
        return CLAUDE_PRICING.get(model, CLAUDE_PRICING["default"])





    def adjust_prompts(self, system_prompt: Optional[str], user_prompt: str) -> Tuple[Optional[str], str]:
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

            logger.debug(f"Sending request to Claude with {len(messages)} messages")

            model_name = model or self.default_model

            message = self.client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages
            )

            usage_data = None
            cache_hit = False
            cache_write = False

            if hasattr(message, "usage"):
                usage_data = {
                    "prompt_tokens": message.usage.input_tokens,
                    "completion_tokens": message.usage.output_tokens,
                    "total_tokens": message.usage.input_tokens + message.usage.output_tokens
                }

                if hasattr(message, "cache") and message.cache:
                    if hasattr(message.cache, "status"):
                        if message.cache.status == "hit":
                            cache_hit = True
                        elif message.cache.status == "write":
                            cache_write = True
            else:
                logger.warning("Token usage not available from API, using estimation")
                estimated_prompt_tokens = sum([len(m.get("content", "").split()) * 1.3 for m in messages])
                estimated_completion_tokens = len(message.content[0].text.split()) * 1.3

                usage_data = {
                    "prompt_tokens": int(estimated_prompt_tokens),
                    "completion_tokens": int(estimated_completion_tokens),
                    "total_tokens": int(estimated_prompt_tokens + estimated_completion_tokens)
                }

            if usage_data:
                model_pricing = self.get_model_pricing(model_name)
                costs = self.calculate_token_cost(
                    usage_data, 
                    model_pricing, 
                    cache_hit=cache_hit,
                    cache_write=cache_write
                )

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

            try:
                if hasattr(message, 'content') and isinstance(message.content, list) and len(message.content) > 0:
                    if hasattr(message.content[0], 'text'):
                        return message.content[0].text
                    elif isinstance(message.content[0], dict) and 'text' in message.content[0]:
                        return message.content[0]['text']

                elif hasattr(message, 'content') and isinstance(message.content, str):
                    return message.content

                return str(message)
            except Exception as e:
                logger.error(f"Error parsing Claude response: {e}")
                return f"Error parsing response: {e}"

            return None

        except Exception as e:
            logger.error(f"API call failed: {str(e)}", exc_info=True)
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
