import logging
import json
from typing import Optional, List, Dict, Tuple, Any
from openai import OpenAI
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: str):
        super().__init__(api_key)

    def _initialize_client(self, api_key: str) -> None:
        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            logger.info("DeepSeek client initialized successfully")
        except Exception as e:
            raise ValueError(f"Failed to initialize DeepSeek client: {str(e)}")

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
        tool_usage: bool,
        thinking_config: Optional[Dict] = None
    ) -> Any:

        if not hasattr(self, 'client'):
            raise ValueError("DeepSeek client not initialized")


        params = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }


        if tool_usage:

            params["functions"] = self._get_function_schema()
            params["function_call"] = "auto"


        logger.debug(f"Sending request to DeepSeek with {len(messages)} messages")
        return self.client.chat.completions.create(**params)

    def _get_function_schema(self) -> List[Dict[str, Any]]:

        return [{
            "name": "tool",
            "description": "A general purpose tool that can perform actions",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The tool name to call"
                    },
                    "action_input": {
                        "type": "object",
                        "description": "The parameters for the tool"
                    },
                    "thinking": {
                        "type": "string",
                        "description": "Reasoning about the tool call"
                    }
                },
                "required": ["action", "action_input"]
            }
        }]

    def extract_response_content(self, message) -> str:

        try:

            response_text = super().extract_response_content(message)


            if (hasattr(message, 'choices') and message.choices and len(message.choices) > 0 and
                hasattr(message.choices[0], 'message')):

                choice = message.choices[0]


                if (hasattr(choice.message, 'function_call') and
                    choice.message.function_call is not None):

                    function_call = choice.message.function_call

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
