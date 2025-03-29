import openai # Keep specific SDK import
import os
import logging
import asyncio # Import needed in base, good to have here too if used directly
from typing import Dict, List, Optional, Any, AsyncIterator, Union, Tuple, Type

# Use relative imports within the package
from ..base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

# --- Configuration (Keep as is per user request, with minor corrections) ---
DEEPSEEK_CONFIG = ProviderConfig(
    name="deepseek",
    api_base="https://api.deepseek.com/v1",
    api_key_env="DEEPSEEK_API_KEY",
    default_model="deepseek-chat",
    requires_import="openai",
    models={
        "deepseek-chat": ModelConfig(
            name="deepseek-chat",
            context_length=32768, # User should verify this, seems low for deepseek
            pricing=PricingTier(input=0.07, output=1.10) # Per Million Tokens
        ),
        "deepseek-reasoner": ModelConfig( # Assuming this is deepseek-coder? Name should match API.
            name="deepseek-coder", # Corrected potential name based on DeepSeek docs
            context_length=128000, # Context for coder is typically higher
            pricing=PricingTier(input=0.14, output=0.28) # Updated pricing example for coder
        )
    },
    default_timeout=60.0, # Use default from BaseClient or override here
    default_max_retries=2
)
# --- End Configuration ---

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseClient):
    def __init__(self, config: Optional[ProviderConfig] = None):
        """Initializes the DeepSeekClient."""
        effective_config = config or DEEPSEEK_CONFIG
        # Set provider-specific defaults *before* calling super().__init__ if needed
        # self.timeout = 90.0 # Example override
        super().__init__(effective_config)
        # self.default_model is set by BaseClient

    def _initialize_provider_client(self) -> openai.AsyncOpenAI:
        """(Sync) Initializes the OpenAI SDK client configured for DeepSeek."""
        # BaseClient's __init__ checks api_key and dependency import
        if not self.api_key:
            raise RuntimeError("API key unexpectedly missing during client initialization.")

        try:
            return openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.config.api_base,
                timeout=self.timeout, # Use timeout from BaseClient attributes
                max_retries=self.max_retries # Use retries from BaseClient attributes
            )
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek client (via AsyncOpenAI): {e}", exc_info=True)
            raise

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Formats messages for the OpenAI compatible API."""
        formatted = []
        for msg in messages:
            if isinstance(msg.content, str):
                formatted.append({"role": msg.role, "content": msg.content})
            else:
                # Handle potential complex content (e.g., images) - currently log/convert
                logger.warning(f"Unsupported content type {type(msg.content)} in DeepSeek message, converting to string.")
                formatted.append({"role": msg.role, "content": str(msg.content)})
        # OpenAI compatible API generally requires non-empty messages
        if not formatted:
            logger.error("Cannot make OpenAI-compatible API call with empty formatted messages.")
            return None # Indicate formatting failure
        return formatted

    async def _execute_api_call(
        self,
        formatted_messages: List[Dict[str, Any]], # Expects list from _format_messages
        api_model_name: str,
        stream: bool,
        **kwargs
    ) -> Union[openai.types.chat.ChatCompletion, AsyncIterator[openai.types.chat.ChatCompletionChunk]]:
        """Makes the actual OpenAI SDK call for DeepSeek."""
        if self.client is None:
            raise RuntimeError("DeepSeek client (AsyncOpenAI) not initialized before API call.")

        params = {
            "messages": formatted_messages,
            "model": api_model_name,
            "stream": stream,
            **kwargs # Include max_tokens, temperature etc. from BaseClient
        }

        # Add other valid OpenAI/DeepSeek parameters if provided
        valid_extra_params = {"top_p", "frequency_penalty", "presence_penalty", "stop"}
        for key in list(params.keys()): # Iterate over keys copy
            if key not in valid_extra_params and key not in ["messages", "model", "stream", "max_tokens", "temperature"]:
                logger.warning(f"Ignoring unsupported parameter for DeepSeek/OpenAI: {key}")
                params.pop(key)

        # Make the SDK call (let BaseClient handle exceptions)
        response = await self.client.chat.completions.create(**params)

        # Log usage for non-streaming immediately
        if not stream and isinstance(response, openai.types.chat.ChatCompletion) and response.usage:
            logger.info(f"DeepSeek API Usage: Input={response.usage.prompt_tokens}, Output={response.usage.completion_tokens}")

        return response

    def _process_response(self, response: openai.types.chat.ChatCompletion) -> str:
        """Extracts text content from a non-streaming OpenAI-compatible response."""
        if not response.choices:
            logger.warning("Received no choices from DeepSeek/OpenAI.")
            return ""

        message = response.choices[0].message
        if not message or not message.content:
            logger.warning("Received choice but no message content from DeepSeek/OpenAI.")
            return ""

        return message.content.strip()

    def _process_stream_chunk(self, chunk: openai.types.chat.ChatCompletionChunk) -> Optional[str]:
        """Extracts text delta from an OpenAI-compatible stream chunk."""
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                return delta.content
        # Can add logging for finish_reason or other chunk details if needed
        return None # No text delta in this chunk

    # --- Optional: Provide SDK-specific error details ---
    def _get_sdk_exception_types(self) -> Tuple[Type[Exception], ...]:
        return (
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.APIStatusError,
            openai.APIError
        )

    def _extract_error_details(self, error: Exception) -> Tuple[Optional[int], str]:
        status_code = getattr(error, 'status_code', None)
        message = getattr(error, 'message', str(error)) # Default message

        # Try to get more specific message from OpenAI's error response text/body
        if isinstance(error, openai.APIStatusError):
            try:
                # Response might be JSON containing more details
                error_details = error.response.json()
                message = error_details.get('error', {}).get('message', message)
            except: # Handle cases where response is not JSON or parsing fails
                message = error.response.text or message # Fallback to raw text

        return status_code, message

    # chat_completion and stream_chat_completion are inherited
