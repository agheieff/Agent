import logging
import datetime
from typing import Optional, List, Dict, Tuple, Any
from openai import OpenAI
from .base_client import BaseLLMClient, TokenUsage

logger = logging.getLogger(__name__)

DEEPSEEK_PRICING = {
    "deepseek-reasoner": {
        "input": 0.14 / 1_000_000,
        "input_cache_read": 0.05 / 1_000_000,
        "input_cache_write": 0.14 / 1_000_000,
        "output": 2.19 / 1_000_000,
        "discount_hours": (16, 30, 0, 30),
        "discount_rate": 0.75,
    },
    "deepseek-reasoner-tools": {
        "input": 0.14 / 1_000_000,
        "input_cache_read": 0.05 / 1_000_000,
        "input_cache_write": 0.14 / 1_000_000,
        "output": 2.19 / 1_000_000,
        "discount_hours": (16, 30, 0, 30),
        "discount_rate": 0.75,
    },
    "default": {
        "input": 0.14 / 1_000_000,
        "output": 2.19 / 1_000_000,
    }
}

class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: str):
        super().__init__()
        if not api_key:
            raise ValueError("DeepSeek API key is required")

        if len(api_key) < 10:
            logger.warning("DeepSeek API key may be invalid (too short)")

        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            if hasattr(self.client, 'api_key'):
                logger.info("DeepSeek client initialized successfully")
        except Exception as e:
            raise ValueError(f"Failed to initialize DeepSeek client: {str(e)}")

        self.default_model = "deepseek-reasoner"

    def get_model_pricing(self, model: str) -> Dict[str, float]:
        pricing = DEEPSEEK_PRICING.get(model, DEEPSEEK_PRICING["default"])

        if "discount_hours" in pricing and "discount_rate" in pricing:
            current_time = datetime.datetime.now(datetime.timezone.utc)
            current_hour = current_time.hour
            current_minute = current_time.minute

            start_hour, start_minute, end_hour, end_minute = pricing["discount_hours"]

            current_time_mins = current_hour * 60 + current_minute
            start_time_mins = start_hour * 60 + start_minute
            end_time_mins = end_hour * 60 + end_minute

            discount_applied = False
            if end_time_mins < start_time_mins:
                if current_time_mins >= start_time_mins or current_time_mins <= end_time_mins:
                    discount_applied = True
            else:
                if start_time_mins <= current_time_mins <= end_time_mins:
                    discount_applied = True

            if discount_applied:
                discount_multiplier = 1.0 - pricing["discount_rate"]
                pricing_copy = pricing.copy()
                for key in ["input", "input_cache_read", "input_cache_write", "output"]:
                    if key in pricing_copy:
                        pricing_copy[key] = pricing_copy[key] * discount_multiplier
                return pricing_copy

        return pricing





    def adjust_prompts(self, system_prompt: Optional[str], user_prompt: str) -> Tuple[Optional[str], str]:
        if system_prompt:
            combined = system_prompt + "\n\n" + user_prompt
            return None, combined
        else:

            return None, user_prompt

    async def generate_response(self, conversation_history: List[Dict]) -> str:
        system_content = ""
        user_messages = []
        other_messages = []

        if conversation_history and conversation_history[0]["role"] == "system":
            system_content = conversation_history[0]["content"]
            conversation_history = conversation_history[1:]

        for msg in conversation_history:
            if msg["role"] == "user":
                user_messages.append(msg)
            else:
                other_messages.append(msg)

        fixed_messages = []

        if not user_messages:
            if system_content:
                fixed_messages = [{"role": "user", "content": system_content}]
            else:
                fixed_messages = [{"role": "user", "content": "Hello, please respond."}]
        else:
            if system_content and user_messages:
                first_user_msg = user_messages[0].copy()
                first_user_msg["content"] = f"{system_content}\n\n{first_user_msg['content']}"
                fixed_messages.append(first_user_msg)
                user_messages = user_messages[1:]

            last_role = "user"
            messages_to_process = []

            if fixed_messages:
                messages_to_process = other_messages + user_messages[1:]
            else:
                messages_to_process = other_messages + user_messages

            for msg in messages_to_process:
                role = msg["role"]
                if role != last_role:
                    fixed_messages.append(msg)
                    last_role = role

            if fixed_messages and fixed_messages[-1]["role"] != "user" and user_messages:
                fixed_messages.append(user_messages[-1])

        response = await self.get_response(
            prompt=None,
            system=None,
            conversation_history=fixed_messages,
            temperature=0.6,
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

        try:
            if conversation_history:
                messages = conversation_history
            else:
                messages = []
                if prompt:
                    messages.append({"role": "user", "content": prompt})

            logger.debug(f"Sending request to DeepSeek with {len(messages)} messages")

            model_name = model or ("deepseek-reasoner-tools" if tool_usage else self.default_model)

            if tool_usage:
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

            if hasattr(response, "usage"):
                usage_data = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }

                cache_hit = False
                if hasattr(response, "cached") and response.cached:
                    cache_hit = True

                model_pricing = self.get_model_pricing(model_name)
                costs = self.calculate_token_cost(usage_data, model_pricing, cache_hit=cache_hit)

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

            if response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                content = message.content
                return content

            return None

        except Exception as e:
            logger.error(f"DeepSeek API call failed: {str(e)}", exc_info=True)
            return None

    async def check_for_user_input_request(self, response: str) -> Tuple[bool, Optional[str]]:
        return False, None
