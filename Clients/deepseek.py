import logging
import json
from typing import Optional, List, Dict, Any
from openai import OpenAI
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: str):
        # DeepSeek does not use a separate system prompt – so set use_system_prompt to False.
        super().__init__(api_key, use_system_prompt=False)

    def _initialize_client(self, api_key: str) -> None:
        try:
            self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            logger.info("DeepSeek client initialized successfully")
        except Exception as e:
            raise ValueError(f"Failed to initialize DeepSeek client: {e}")

    def _register_models(self) -> None:
        self.models["deepseek-reasoner"] = ModelInfo(
            name="DeepSeek Reasoner",
            api_name="deepseek-reasoner",
            supports_reasoning=False,
            prefers_separate_system_prompt=False,
            context_window=128000,
            input_price=0.14,
            output_price=2.19,
            input_cache_read_price=0.05,
            input_cache_write_price=0.14,
            discount_hours=(16, 30, 0, 30),
            discount_rate=0.75
        )
        self.default_model = "deepseek-reasoner"

    async def _make_api_call(
        self,
        messages: List[Dict],
        model_name: str,
        temperature: float,
        max_tokens: int,
        tool_usage: bool
    ) -> Any:
        if not hasattr(self, 'client'):
            raise ValueError("DeepSeek client not initialized")
        # With use_system_prompt=False (set in __init__), any system prompt is expected
        # to have already been merged into the first user message.
        params = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        logger.debug(f"Sending request to DeepSeek with {len(messages)} messages")
        return self.client.chat.completions.create(**params)

    def extract_response_content(self, message) -> str:
        try:
            response_text = super().extract_response_content(message)
            if hasattr(message, 'choices') and message.choices:
                choice = message.choices[0]
                function_call = getattr(choice.message, 'function_call', None)
                if function_call:
                    function_data = {
                        "action": function_call.name,
                        "action_input": json.loads(function_call.arguments),
                        "response": response_text
                    }
                    return json.dumps(function_data)
            return response_text
        except Exception as e:
            logger.error(f"Error extracting DeepSeek response content: {e}")
            return f"Error parsing response: {e}"
