import os
import logging
from typing import Dict, List, Optional, Any
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

DEEPSEEK_CONFIG = ProviderConfig(
    name="deepseek",
    api_base="https://api.deepseek.com/v1",
    api_key_env="DEEPSEEK_API_KEY",
    default_model="deepseek-chat",
    requires_import="openai",
    models={
        "deepseek-chat": ModelConfig(
            name="deepseek-chat",
            context_length=32768,
            pricing=PricingTier(input=0.07, output=1.10)
            # TODO add input cache miss at 0.027
            # TODO add discount 50% between 16:30 and 00:30 UTC
        ),
        "deepseek-reasoner": ModelConfig(
            name="deepseek-reasoner",
            context_length=32768,
            pricing=PricingTier(input=0.14, output=2.19))
            # TODO add input cache miss at 0.55
            # TODO add discount 75% between 16:30 and 00:30 UTC
    }
)

class DeepSeekClient(BaseClient):
    def __init__(self, config=DEEPSEEK_CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.api_base)

    def _call_api(self, **kwargs):
        return self.client.chat.completions.create(**kwargs)

    def _process_response(self, response):
        return response.choices[0].message.content
