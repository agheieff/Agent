import os
import logging
from typing import Dict, List, Optional, Any
# Import base classes BUT NOT the config constants anymore
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message
import anthropic

class AnthropicClient(BaseClient):
    # __init__ now relies on the config being passed correctly by the Orchestrator
    def __init__(self, config: ProviderConfig):
        # Ensure config is provided
        if not config or config.name != "anthropic":
             raise ValueError("AnthropicClient requires a valid ProviderConfig for 'anthropic'.")
        super().__init__(config) # Pass the received config to the base class

    def _initialize_client(self):
        # ... (rest of the method remains the same) ...
        return anthropic.AsyncAnthropic(
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries
        )

    def _format_messages(self, messages: List[Message]) -> Dict[str, Any]:
        # ... (remains the same) ...
        formatted = []
        system = None
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                # Anthropic uses 'user' and 'assistant'
                role = "assistant" if msg.role == "assistant" else "user"
                # Handle potential non-string content just in case
                content = str(msg.content) if msg.content is not None else ""
                formatted.append({"role": role, "content": content})
        return {"formatted_msgs": formatted, "system": system}


    async def _call_api(self, formatted_messages: Dict[str, Any], model_name: str, **kwargs):
        # ... (remains the same) ...
        actual_message_list = formatted_messages["formatted_msgs"]
        system_prompt = formatted_messages["system"]

        params = {
            "messages": actual_message_list,
            "model": model_name, # Use the actual model name resolved by base class
            "max_tokens": kwargs.get('max_tokens', 4096), # Increased default max_tokens
            "temperature": kwargs.get('temperature', 0.7),
        }
        if system_prompt is not None:
            params["system"] = system_prompt

        try:
            response = await self.client.messages.create(**params)
            return response
        except anthropic.APIConnectionError as e:
            raise ConnectionError(f"Anthropic connection error: {e}") from e
        except anthropic.RateLimitError as e:
             raise ConnectionError(f"Anthropic rate limit exceeded: {e}") from e
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Anthropic API error: {e.status_code} - {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error during Anthropic API call: {str(e)}") from e

    def _process_response(self, response):
        # ... (remains the same) ...
        # Ensure response and content list exist and are not empty
        if not response or not response.content:
            print("Warning: Received empty response content from Anthropic.")
            return ""
        # Ensure the first content block has 'text'
        if hasattr(response.content[0], 'text'):
            return response.content[0].text
        else:
            print(f"Warning: Unexpected Anthropic response block format: {response.content[0]}")
            return ""


    async def chat_completion_stream(self, messages: List[Message], model: str = None, **kwargs):
        # ... (remains the same, uses base class _get_model_config) ...
        model_config = self._get_model_config(model) # Gets specific ModelConfig
        model_to_use = model_config.name # Uses the actual API model name
        formatted_data = self._format_messages(messages)

        params = {
            "messages": formatted_data["formatted_msgs"],
            "model": model_to_use,
            "max_tokens": kwargs.get('max_tokens', 4096), # Increased default
            "temperature": kwargs.get('temperature', 0.7),
            # stream=True is handled by client.messages.stream() call
        }
        if formatted_data["system"]:
            params["system"] = formatted_data["system"]

        try:
            async with self.client.messages.stream(**params) as stream:
                async for chunk in stream:
                    if chunk.type == "content_block_delta":
                        yield chunk.delta.text
                    # Anthropic streams might have other event types, like message_start, message_delta, message_stop
                    # We only care about content deltas for now.
                    elif chunk.type == "message_stop":
                        # Optional: Log final usage stats if needed, though base class doesn't handle this yet
                        # final_message = await stream.get_final_message()
                        # print(f"Input Tokens: {final_message.usage.input_tokens}")
                        # print(f"Output Tokens: {final_message.usage.output_tokens}")
                        break
        except Exception as e:
            # Log specific stream error
            print(f"Anthropic Streaming Error: {type(e).__name__} - {e}")
            # Consider more specific error handling if needed (e.g., RateLimitError)
            raise RuntimeError(f"Anthropic streaming error: {str(e)}") from e
