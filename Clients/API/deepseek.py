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
        ),
        "deepseek-reasoner": ModelConfig(
            name="deepseek-reasoner",
            context_length=32768,
            pricing=PricingTier(input=0.14, output=2.19)
        )
    }
)

class DeepSeekClient(BaseClient):
    def __init__(self, config: Optional[ProviderConfig] = None):
        config = config or DEEPSEEK_CONFIG
        super().__init__(config)
        self.default_model = config.default_model

    def _initialize_client(self):
        import openai
        return openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.config.api_base,
            timeout=30.0
        )

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def _call_api(self, messages, model, **kwargs):
        formatted_msgs = self._format_messages(messages)
        
        try:
            response = await self.client.chat.completions.create(
                messages=formatted_msgs,
                model=model,
                max_tokens=kwargs.get('max_tokens', 1024),
                temperature=kwargs.get('temperature', 0.7),
            )
            return response
        except Exception as e:
            raise RuntimeError(f"API error: {str(e)}") from e

    def _process_response(self, response):
        if not response.choices:
            return ""
        return response.choices[0].message.content

    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs):
        model_name = model or self.default_model
        model_config = self._get_model_config(model_name)
        response = await self._call_api(messages=messages, model=model_config.name, **kwargs)
        return self._process_response(response)
