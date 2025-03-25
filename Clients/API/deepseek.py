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
    def __init__(self, config=DEEPSEEK_CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        # Dummy implementation of the DeepSeek client.
        class DummyDeepSeekClient:
            def __init__(self, api_key, base_url):
                self.api_key = api_key
                self.base_url = base_url

            class Chat:
                @staticmethod
                def completions_create(**kwargs):
                    # Dummy response structure
                    class Choice:
                        message = type("Message", (), {"content": "Dummy deepseek response"})
                    class Response:
                        choices = [Choice()]
                    return Response()

            @property
            def chat(self):
                return self.Chat()
        return DummyDeepSeekClient(api_key=self.api_key, base_url=self.config.api_base)

    def _call_api(self, **kwargs):
        return self.client.chat.completions_create(**kwargs)

    def _process_response(self, response):
        return response.choices[0].message.content

    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int, cache_hit: bool = True) -> float:
        """
        Calculate the cost of a request based on token counts and model pricing.

        Args:
            model_name (str): The model being used.
            input_tokens (int): Number of input tokens.
            output_tokens (int): Number of output tokens.
            cache_hit (bool): If True, no additional cost for cache miss is applied.

        Returns:
            float: Total cost for the request.
        """
        # Get the model configuration
        if model_name not in self.config.models:
            raise ValueError(f"Model '{model_name}' not found in configuration.")
        pricing = self.config.models[model_name].pricing

        # Calculate base cost per million tokens.
        input_cost = (input_tokens / 1_000_000) * (pricing.input + (0 if cache_hit else pricing.input_cache_miss))
        output_cost = (output_tokens / 1_000_000) * pricing.output
        total_cost = input_cost + output_cost

        # Determine if discount applies (based on UTC time).
        now = datetime.utcnow()
        current_hour = now.hour + now.minute / 60.0
        start, end = pricing.discount_hours

        # Handle discount period that may cross midnight.
        if start < end:
            discount_applicable = start <= current_hour < end
        else:
            discount_applicable = current_hour >= start or current_hour < end

        if discount_applicable:
            total_cost *= (1 - pricing.discount_rate)

        return total_cost
