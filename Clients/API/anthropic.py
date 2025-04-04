import os
import logging
from typing import Dict, List, Optional, Any
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message
import anthropic

ANTHROPIC_CONFIG = ProviderConfig(
    name="anthropic",
    api_base="https://api.anthropic.com",
    api_key_env="ANTHROPIC_API_KEY",
    default_model="claude-3-7-sonnet",
    requires_import="anthropic",
    models={
        "claude-3-7-sonnet": ModelConfig(
            name="claude-3-7-sonnet-latest",
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
        "claude-3-5-sonnet": ModelConfig(
            name="claude-3-5-sonnet-latest",
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
    }
)

class AnthropicClient(BaseClient):
    def __init__(self, config=None):
        config = config or ANTHROPIC_CONFIG
        super().__init__(config)

    def _initialize_client(self):
        return anthropic.AsyncAnthropic(
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries
        )

    def _format_messages(self, messages: List[Message]) -> Dict[str, Any]:
        formatted = []
        system = None
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                role = "assistant" if msg.role == "assistant" else "user"
                formatted.append({"role": role, "content": msg.content})
        return {"formatted_msgs": formatted, "system": system}

    async def _call_api(self, formatted_messages: Dict[str, Any], model_name: str, **kwargs):
            actual_message_list = formatted_messages["formatted_msgs"]
            system_prompt = formatted_messages["system"]

            params = {
                "messages": actual_message_list,
                "model": model_name,
                "max_tokens": kwargs.get('max_tokens', 500),
                "temperature": kwargs.get('temperature', 0.7),
            }
            if system_prompt is not None:
                params["system"] = system_prompt

            try:
                response = await self.client.messages.create(**params)
                return response
            except anthropic.APIConnectionError as e:
                raise ConnectionError(f"Connection error: {e}") from e
            except anthropic.APIStatusError as e:
                raise RuntimeError(f"API error: {e.status_code} - {e.message}") from e
            except Exception as e:
                raise RuntimeError(f"Unexpected error during Anthropic API call: {str(e)}") from e

    def _process_response(self, response):
        if not response.content:
            return ""
        return response.content[0].text
