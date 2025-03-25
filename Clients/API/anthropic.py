import os
import logging
from typing import Dict, List, Optional, Any
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

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
        "claude-3-5sonnet": ModelConfig(
            name="claude-3-5-sonnet-latest",
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
    }
)

class AnthropicClient(BaseClient):
    def __init__(self, config=ANTHROPIC_CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        import anthropic
        return anthropic.Anthropic(api_key=self.api_key)

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

    def _call_api(self, messages, model, **kwargs):
        formatted_msgs, system = self._format_messages(messages)
        # Supply a default max_tokens if not provided (adjust as needed)
        if 'max_tokens' not in kwargs:
            kwargs['max_tokens'] = 500
        return self.client.messages.create(
            messages=formatted_msgs,
            model=model,
            system=system,
            **kwargs
        )

    def _process_response(self, response):
        return response.content[0].text
