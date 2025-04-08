import os
import logging
import json # Import json for pretty printing
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
                input=0.07, # Prices per 1M tokens as of 2024-Q3 (example)
                output=1.10,
                input_cache_miss=0.27,
                discount_hours=(16.5, 0.5), # UTC 16:30 to 00:30
                discount_rate=0.50
            )
        ),
        "deepseek-coder": ModelConfig( # Example - Check current DeepSeek models
            name="deepseek-coder",
            context_length=32768, # Example context length
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
        try:
            import openai
        except ImportError:
            raise ImportError("OpenAI library not found. Please install it using 'pip install openai'")
        return openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.config.api_base,
            timeout=self.timeout,
            max_retries=self.max_retries
        )


    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        formatted = []
        for msg in messages:
            content_str = str(msg.content) if msg.content is not None else ""
            # Keep system messages even if content is empty/whitespace
            # Keep user/assistant messages only if content is non-empty/non-whitespace
            if msg.role == 'system' or content_str.strip():
                 formatted.append({"role": msg.role, "content": content_str})
            elif msg.role != 'system':
                 # Only log if skipping non-system, non-empty message (should be rare)
                 if content_str:
                     print(f"[DeepSeekClient._format_messages] Skipping message with only whitespace: Role={msg.role}")


        return formatted


    async def _call_api(self, formatted_messages: List[Dict[str, str]], model_name: str, **kwargs):
        if not formatted_messages:
            raise ValueError("Cannot make API call with empty messages list.")

        # --- DEBUG LOGGING ---
        print("\n" + "="*10 + f" DeepSeek API Call (Non-Stream) to {model_name} " + "="*10)
        try:
            # Use json.dumps for pretty printing the list of dictionaries
            print(json.dumps(formatted_messages, indent=2))
        except Exception as log_err:
            print(f"[Error logging messages: {log_err}]")
            print(formatted_messages) # Fallback to raw print
        print("="* (32 + len(model_name)) + "\n")
        # --- END DEBUG LOGGING ---

        try:
            response = await self.client.chat.completions.create(
                messages=formatted_messages,
                model=model_name,
                max_tokens=kwargs.get('max_tokens', 1024),
                temperature=kwargs.get('temperature', 0.7),
            )
            return response
        except Exception as e:
            print(f"[DeepSeekClient API Error]: {type(e).__name__} - {e}") # More specific error log
            raise RuntimeError(f"API error: {str(e)}") from e


    def _process_response(self, response):
        if not response or not response.choices:
            return ""
        try:
            choice = response.choices[0]
            if hasattr(choice, 'message') and choice.message:
                return choice.message.content or ""
        except (IndexError, AttributeError) as e:
            print(f"Error processing DeepSeek response choice: {e}")
        return ""


    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int, cache_hit: bool = True) -> float:
        model_to_check = model_name or self.config.default_model
        if model_to_check not in self.config.models:
            raise ValueError(f"Model '{model_to_check}' not found in configuration.")
        pricing = self.config.models[model_to_check].pricing

        input_cost = (input_tokens / 1_000_000) * (pricing.input + (0 if cache_hit else pricing.input_cache_miss))
        output_cost = (output_tokens / 1_000_000) * pricing.output
        total_cost = input_cost + output_cost

        if pricing.discount_hours and isinstance(pricing.discount_hours, tuple) and len(pricing.discount_hours) == 2:
            now = datetime.utcnow()
            current_hour = now.hour + now.minute / 60.0
            start, end = pricing.discount_hours

            discount_applicable = False
            if start < end:
                discount_applicable = start <= current_hour < end
            else: # Overnight case
                discount_applicable = current_hour >= start or current_hour < end

            if discount_applicable:
                total_cost *= (1 - pricing.discount_rate)

        return total_cost


    async def chat_completion_stream(self, messages: List[Message], model: str = None, **kwargs):
        model_config = self._get_model_config(model)
        model_to_use = model_config.name
        formatted_messages = self._format_messages(messages)

        if not formatted_messages:
            print("Warning: chat_completion_stream called with no messages to send.")
            if False: yield # Ensure it's an async generator
            return

        params = {
            "messages": formatted_messages,
            "model": model_to_use,
            "max_tokens": kwargs.get('max_tokens', 1024),
            "temperature": kwargs.get('temperature', 0.7),
            "stream": True
        }

        # --- DEBUG LOGGING ---
        print("\n" + "="*10 + f" DeepSeek API Call (Stream) to {model_to_use} " + "="*10)
        try:
            # Use json.dumps for pretty printing the list of dictionaries
            print(json.dumps(formatted_messages, indent=2))
        except Exception as log_err:
            print(f"[Error logging messages: {log_err}]")
            print(formatted_messages) # Fallback to raw print
        print("="* (28 + len(model_to_use)) + "\n")
        # --- END DEBUG LOGGING ---


        try:
            response = await self.client.chat.completions.create(**params)
            async for chunk in response:
                content_delta = None
                try:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        if hasattr(choice, 'delta') and choice.delta:
                            content_delta = choice.delta.content
                except (IndexError, AttributeError):
                    pass # Ignore potential minor errors during chunk processing

                if content_delta:
                    yield content_delta

        except Exception as e:
            print(f"[DeepSeekClient Stream Error]: {type(e).__name__} - {e}") # More specific error log
            raise RuntimeError(f"Streaming error: {str(e)}") from e
