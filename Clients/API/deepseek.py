import os
import logging
import json # Import json for pretty printing
from datetime import datetime
from typing import Dict, List, Optional, Any
# Import base classes BUT NOT the config constants anymore
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

# --- REMOVE DEEPSEEK_CONFIG Definition ---
# DEEPSEEK_CONFIG = ProviderConfig(...) # <- DELETE THIS BLOCK

class DeepSeekClient(BaseClient):
    # __init__ now relies on the config being passed correctly by the Orchestrator
    def __init__(self, config: ProviderConfig):
         # Ensure config is provided
        if not config or config.name != "deepseek":
             raise ValueError("DeepSeekClient requires a valid ProviderConfig for 'deepseek'.")
        super().__init__(config) # Pass the received config to the base class

    def _initialize_client(self):
        # ... (remains the same) ...
        try:
            import openai
        except ImportError:
            raise ImportError("OpenAI library not found. Please install it using 'pip install openai'")
        return openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.config.api_base, # Uses self.config set by base class
            timeout=self.timeout,
            max_retries=self.max_retries
        )


    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        # ... (remains the same) ...
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
        # ... (empty message check remains the same) ...
        if not formatted_messages:
            raise ValueError("Cannot make API call with empty messages list.")

        # --- DEBUG LOGGING ---
        print("\n" + "="*10 + f" DeepSeek API Call (Non-Stream) to {model_name} " + "="*10)
        try:
            print(json.dumps(formatted_messages, indent=2))
        except Exception as log_err:
            print(f"[Error logging messages: {log_err}]")
            print(formatted_messages) # Fallback
        print("="* (32 + len(model_name)) + "\n")
        # --- END DEBUG LOGGING ---

        try:
            response = await self.client.chat.completions.create(
                messages=formatted_messages,
                model=model_name, # Use actual model name passed in
                max_tokens=kwargs.get('max_tokens', 4096), # Increased default
                temperature=kwargs.get('temperature', 0.7),
                # Add other potential DeepSeek parameters if needed
            )
            return response
        except Exception as e:
            # Use specific exception types from openai library if needed
            # Example: from openai import RateLimitError, APIConnectionError, APIStatusError
            print(f"[DeepSeekClient API Error]: {type(e).__name__} - {e}") # More specific error log
            # Consider re-raising specific error types for Orchestrator handling
            raise RuntimeError(f"DeepSeek API error: {str(e)}") from e


    def _process_response(self, response):
        # ... (remains the same) ...
        if not response or not response.choices:
            return ""
        try:
            choice = response.choices[0]
            # Check standard OpenAI response structure
            if hasattr(choice, 'message') and choice.message and hasattr(choice.message, 'content'):
                return choice.message.content or ""
        except (IndexError, AttributeError) as e:
            print(f"Error processing DeepSeek response choice: {e}")
        return ""


    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int, cache_hit: bool = True) -> float:
        # This method now needs the config from self.config, which is set by the base class
        model_alias = model_name or self.config.default_model # Use alias or default alias
        model_cfg = self._get_model_config(model_alias) # Get ModelConfig using base method

        if not model_cfg:
             raise ValueError(f"Model alias '{model_alias}' not found in configuration for provider '{self.config.name}'.")

        pricing = model_cfg.pricing

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
        model_config = self._get_model_config(model) # Gets specific ModelConfig
        model_to_use = model_config.name # Uses the actual API model name
        formatted_messages = self._format_messages(messages)

        if not formatted_messages:
            print("Warning: chat_completion_stream called with no messages to send.")
            if False: yield # Ensure it's an async generator
            return

        params = {
            "messages": formatted_messages,
            "model": model_to_use,
            "max_tokens": kwargs.get('max_tokens', 4096), # Increased default
            "temperature": kwargs.get('temperature', 0.7),
            "stream": True
        }

        # --- DEBUG LOGGING ---
        print("\n" + "="*10 + f" DeepSeek API Call (Stream) to {model_to_use} " + "="*10)
        try:
            print(json.dumps(formatted_messages, indent=2))
        except Exception as log_err:
            print(f"[Error logging messages: {log_err}]")
            print(formatted_messages) # Fallback
        print("="* (28 + len(model_to_use)) + "\n")
        # --- END DEBUG LOGGING ---


        try:
            response = await self.client.chat.completions.create(**params)
            async for chunk in response:
                content_delta = None
                try:
                    # Standard OpenAI streaming chunk format
                    if chunk.choices and hasattr(chunk.choices[0], 'delta') and chunk.choices[0].delta:
                        content_delta = chunk.choices[0].delta.content
                except (IndexError, AttributeError):
                    pass # Ignore potential minor errors during chunk processing

                if content_delta:
                    yield content_delta

        except Exception as e:
            print(f"[DeepSeekClient Stream Error]: {type(e).__name__} - {e}") # More specific error log
            # Consider re-raising specific error types for Orchestrator handling
            raise RuntimeError(f"DeepSeek streaming error: {str(e)}") from e
