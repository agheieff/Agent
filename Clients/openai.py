from openai import OpenAI
import logging
import json
from typing import Dict, Optional, List, Any
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str, model: Optional[str] = None):
        self.requested_model = model
        super().__init__(api_key)

    def _initialize_client(self, api_key: str) -> None:
        try:
            self.client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to initialize OpenAI client: {str(e)}")

    def _register_models(self) -> None:
        self.models["gpt-4.5-preview"] = ModelInfo(
            name="GPT-4.5 Preview",
            api_name="gpt-4.5-preview",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=75.0,
            output_price=150.0,
            input_cache_read_price=37.5,
            input_cache_write_price=75.0
        )

        self.models["gpt-4o"] = ModelInfo(
            name="GPT-4o",
            api_name="gpt-4o",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=2.5,
            output_price=10.0,
            input_cache_read_price=1.25,
            input_cache_write_price=2.5
        )

        self.models["o1"] = ModelInfo(
            name="o1",
            api_name="o1",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=15.0,
            output_price=60.0,
            input_cache_read_price=7.5,
            input_cache_write_price=15.0
        )

        self.models["o3-mini"] = ModelInfo(
            name="o3-mini",
            api_name="o3-mini",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=1.1,
            output_price=4.4,
            input_cache_read_price=0.55,
            input_cache_write_price=1.1
        )

        if self.requested_model and self.requested_model in self.models:
            self.default_model = self.requested_model
        else:
            self.default_model = "o1"

    async def _make_api_call(
        self,
        messages: List[Dict],
        model_name: str,
        temperature: float,
        max_tokens: int,
        tool_usage: bool,
        thinking_config: Optional[Dict] = None
    ) -> Any:
        if not hasattr(self, 'client'):
            raise ValueError("OpenAI client not initialized")

        params = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        logger.debug(f"Sending request to OpenAI with {len(messages)} messages")
        return self.client.chat.completions.create(**params)

    def extract_response_content(self, message) -> str:
        try:
            # Get the basic response text using the common base functionality.
            response_text = super().extract_response_content(message)
            # Check for tool calls in OpenAI's structure.
            if (hasattr(message, 'choices') and message.choices and len(message.choices) > 0 and
                hasattr(message.choices[0], 'message')):
                choice = message.choices[0]
                if (hasattr(choice.message, 'tool_calls') and
                    choice.message.tool_calls and
                    len(choice.message.tool_calls) > 0):
                    tool_call = choice.message.tool_calls[0]
                    if hasattr(tool_call, 'function'):
                        function_data = {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                            "response": response_text
                        }
                        return json.dumps(function_data)
            return response_text
        except Exception as e:
            logger.error(f"Error extracting OpenAI response content: {e}")
            return f"Error parsing response: {e}"
