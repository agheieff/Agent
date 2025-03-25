import os
import logging
from typing import Dict, List, Optional, Any
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

OPENAI_CONFIG = ProviderConfig(
    name="openai",
    api_base="https://api.openai.com/v1",
    api_key_env="OPENAI_API_KEY",
    default_model="gpt-4o",
    requires_import="openai",
    models={
        "gpt-4o": ModelConfig(
            name="gpt-4o",
            context_length=128000,
            pricing=PricingTier(input=5.0, output=15.0)
        ),
        "gpt-4-turbo": ModelConfig(
            name="gpt-4-turbo-preview",
            context_length=128000,
            pricing=PricingTier(input=10.0, output=30.0)
        ),
    }
)

class OpenAIClient(BaseClient):
    def __init__(self, config=OPENAI_CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.api_base)

    def _call_api(self, **kwargs):
        return self.client.chat.completions.create(**kwargs)

    def _process_response(self, response):
        return response.choices[0].message.content
