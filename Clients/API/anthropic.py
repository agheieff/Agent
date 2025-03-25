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
    def __init__(self, config=ANTHROPIC_CONFIG):
        self.timeout = 30.0  # seconds (use float for timeout)
        self.max_retries = 3
        super().__init__(config)
        self.client = None  # Initialize client attribute

    def _initialize_client(self):
        return anthropic.AsyncAnthropic(
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries
        )

    def _format_messages(self, messages: List[Message]) -> (List[Dict[str, str]], Optional[str]):
        formatted = []
        system = None
        
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                role = "assistant" if msg.role == "assistant" else "user"
                formatted.append({"role": role, "content": msg.content})
        
        return formatted, system

    async def _call_api(self, messages, model, **kwargs):
        formatted_msgs, system = self._format_messages(messages)
        
        try:
            response = await self.client.messages.create(
                messages=formatted_msgs,
                model=model,
                system=system,
                max_tokens=kwargs.get('max_tokens', 500),
                temperature=kwargs.get('temperature', 0.7),
            )
            return response
        except anthropic.APIConnectionError as e:
            raise ConnectionError(f"Connection error: {e}") from e
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"API error: {e.status_code} - {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error: {str(e)}") from e

    def _process_response(self, response):
        if not response.content:
            return ""
        return response.content[0].text

    async def chat_completion(self, messages: List[Message], model: str = None, **kwargs):
        model_config = self._get_model_config(model)
        response = await self._call_api(messages=messages, model=model_config.name, **kwargs)
        return self._process_response(response)
