import os
import logging
from typing import Dict, List, Optional, Any
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

ANTHROPIC_CONFIG = ProviderConfig(
    name="anthropic",
    api_base="https://api.anthropic.com",
    api_key_env="ANTHROPIC_API_KEY",
    default_model="claude-3-haiku",
    requires_import="anthropic",
    models={
        "claude-3-haiku": ModelConfig(
            name="claude-3-haiku-20240307",
            context_length=200000,
            pricing=PricingTier(input=0.25, output=1.25)
        ),
        "claude-3-sonnet": ModelConfig(
            name="claude-3-sonnet-20240229",
            context_length=200000,
            pricing=PricingTier(input=3.0, output=15.0)
        ),
    }
)

class AnthropicClient(BaseClient):
    def __init__(self, config=ANTHROPIC_CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        import anthropic
        return anthropic.Anthropic(api_key=self.api_key)

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
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
        return self.client.messages.create(
            messages=formatted_msgs,
            model=model,
            system=system,
            **kwargs
        )

    def _process_response(self, response):
        return response.content[0].text
