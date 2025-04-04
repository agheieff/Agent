import os
import logging
from datetime import datetime
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
            pricing=PricingTier(
                input=0.07,
                output=1.10,
                input_cache_miss=0.27,
                discount_hours=(16.5, 0.5),
                discount_rate=0.50
            )
        ),
        "deepseek-reasoner": ModelConfig(
            name="deepseek-reasoner",
            context_length=32768,
            pricing=PricingTier(
                input=0.14,
                output=2.19,
                input_cache_miss=0.55,
                discount_hours=(16.5, 0.5),
                discount_rate=0.75
            )
        )
    }
)

class DeepSeekClient(BaseClient):
    def __init__(self, config: ProviderConfig = None):
        config = config or DEEPSEEK_CONFIG
        super().__init__(config)

    def _initialize_client(self):
        import openai
        return openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.config.api_base,
            timeout=self.timeout,
            max_retries=self.max_retries
        )

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def _call_api(self, formatted_messages: List[Dict[str, str]], model_name: str, **kwargs):
        try:
            response = await self.client.chat.completions.create(
                messages=formatted_messages,
                model=model_name,
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

    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int, cache_hit: bool = True) -> float:
        """
        Calculate the cost of a request based on token counts and model pricing.
        """
        if model_name not in self.config.models:
            raise ValueError(f"Model '{model_name}' not found in configuration.")
        pricing = self.config.models[model_name].pricing

        input_cost = (input_tokens / 1_000_000) * (pricing.input + (0 if cache_hit else pricing.input_cache_miss))
        output_cost = (output_tokens / 1_000_000) * pricing.output
        total_cost = input_cost + output_cost

        now = datetime.utcnow()
        current_hour = now.hour + now.minute / 60.0
        start, end = pricing.discount_hours

        if start < end:
            discount_applicable = start <= current_hour < end
        else:
            discount_applicable = current_hour >= start or current_hour < end

        if discount_applicable:
            total_cost *= (1 - pricing.discount_rate)

        return total_cost
