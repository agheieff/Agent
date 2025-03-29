import os
import logging
import uuid
from typing import Dict, List, Optional, Any, AsyncIterator, Union, Tuple, Type

# Removed httpx import as MCP calls are moved

import anthropic # Keep specific SDK import

# Use relative imports for components within the same package
from ..base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

logger = logging.getLogger(__name__)

# --- Configuration ---
# User requested not to change this section, keeping it as is.
ANTHROPIC_CONFIG = ProviderConfig(
    name="anthropic",
    api_base="[https://api.anthropic.com](https://api.anthropic.com)",
    api_key_env="ANTHROPIC_API_KEY",
    default_model="claude-3-7-sonnet", # Original default
    requires_import="anthropic",
    models={
        "claude-3-7-sonnet": ModelConfig(
            name="claude-3-7-sonnet-latest", # Potential invalid API name - User should verify
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
        "claude-3-5-sonnet": ModelConfig(
            name="claude-3-5-sonnet-latest", # Potential invalid API name - User should verify
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
        # Add other models as needed, ensuring correct API names and pricing
        # "claude-3-opus": ModelConfig(...)
        # "claude-3-haiku": ModelConfig(...)
    }
)
# --- End Configuration ---


class AnthropicClient(BaseClient):
    def __init__(self, config: ProviderConfig = None):
        """Initializes the AnthropicClient."""
        effective_config = config or ANTHROPIC_CONFIG
        # Set client-specific defaults *before* calling super().__init__
        self.timeout = 120.0 # Increased timeout specific to Anthropic (example)
        self.max_retries = 2
        # Call BaseClient's __init__ to handle common setup (API key, SDK check)
        super().__init__(effective_config)
        # BaseClient handles setting self.default_model

    def _initialize_provider_client(self) -> anthropic.AsyncAnthropic:
        """(Sync) Initializes the Anthropic SDK client."""
        # BaseClient's __init__ checks api_key and dependency import
        if not self.api_key: # Should not happen if BaseClient init worked
            # Keep RuntimeError
            raise RuntimeError("API key unexpectedly missing during client initialization.")

        try:
            # Use timeout/retries set in __init__
            return anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        except Exception as e:
            # Keep error log and raise
            logger.error(f"Failed to initialize Anthropic AsyncClient: {e}", exc_info=True)
            raise # Re-raise for BaseClient._ensure_client_initialized to handle

    def _format_messages(self, messages: List[Message]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Formats messages for Anthropic API, separating the system prompt.
        Handles potential multi-part content and merges consecutive roles.
        Returns: Tuple of (formatted_messages_list, system_prompt_string_or_None)
        """
        formatted = []
        system_prompt = None
        non_system_messages = []

        # 1. Extract system prompt(s) and non-system messages
        for msg in messages:
            if msg.role == "system":
                if isinstance(msg.content, str):
                    if system_prompt is None:
                        system_prompt = msg.content
                    else:
                        system_prompt += "\n" + msg.content
                        # Keep warning for multiple system messages
                        logger.warning("Multiple system messages found. Concatenating them.")
                else:
                    # Keep warning for non-string system content
                    logger.warning(f"System message content is not a string: {type(msg.content)}. Skipping.")
            elif msg.role in ["user", "assistant"]:
                non_system_messages.append(msg)
            else:
                # Keep warning for unsupported roles
                logger.warning(f"Unsupported message role '{msg.role}'. Skipping message.")

        # 2. Format and merge user/assistant messages
        last_role = None
        for msg in non_system_messages:
            if isinstance(msg.content, str):
                content_list = [{"type": "text", "text": msg.content}]
            # Placeholder for complex content (already formatted list)
            # elif isinstance(msg.content, list):
            #     content_list = msg.content
            else:
                # Keep warning for unsupported content types
                logger.warning(f"Unsupported message content type: {type(msg.content)}. Treating as empty text.")
                content_list = [{"type": "text", "text": ""}]

            # Merge consecutive messages of the same role
            if formatted and formatted[-1]["role"] == msg.role:
                if isinstance(formatted[-1]["content"], list):
                    formatted[-1]["content"].extend(content_list)
                    logger.debug(f"Merging consecutive '{msg.role}' message content.")
                else:
                    # Keep warning if merging fails unexpectedly
                    logger.warning("Cannot merge content: Previous message content is not a list. Appending new block.")
                    formatted.append({"role": msg.role, "content": content_list})
            else:
                formatted.append({"role": msg.role, "content": content_list})
            last_role = msg.role

        # Validation: Anthropic requires non-empty messages and specific turn order
        if not formatted and system_prompt:
            # Keep error log and return None for failure
            logger.error("Anthropic requires at least one user/assistant message when a system prompt is provided.")
            return None # Indicate formatting failure
        if not formatted and not system_prompt:
            # Keep error log and return None for failure
            logger.error("Cannot make Anthropic API call with no messages or system prompt.")
            return None # Indicate formatting failure
        # SDK handles first message role validation

        return formatted, system_prompt

    async def _execute_api_call(
        self,
        formatted_messages: Tuple[List[Dict[str, Any]], Optional[str]], # Expects tuple from _format_messages
        api_model_name: str,
        stream: bool,
        **kwargs
    ) -> Union[anthropic.types.Message, AsyncIterator[anthropic.types.MessageStreamEvent]]:
        """Makes the actual Anthropic SDK call."""
        if self.client is None: # Should have been ensured by BaseClient
            # Keep runtime error
            raise RuntimeError("Anthropic client not initialized before API call.")

        messages_list, system_prompt = formatted_messages

        # Prepare final parameters for the SDK
        params = {
            "messages": messages_list,
            "model": api_model_name,
            "stream": stream,
            **kwargs # Include max_tokens, temperature etc. from BaseClient
        }
        if system_prompt:
            params["system"] = system_prompt

        # Add other valid Anthropic parameters if they were passed through kwargs
        valid_anthropic_params = {"top_p", "top_k", "stop_sequences"}
        # Filter out unsupported params passed via kwargs
        keys_to_remove = []
        for key in kwargs:
             if key not in valid_anthropic_params and key not in ["max_tokens", "temperature"]:
                 keys_to_remove.append(key)

        if keys_to_remove:
            # Keep warning for ignored parameters
            logger.warning(f"Ignoring unsupported parameters for Anthropic: {keys_to_remove}")
            for key in keys_to_remove:
                params.pop(key, None) # Remove from final params

        # Make the SDK call (let BaseClient handle exceptions)
        response = await self.client.messages.create(**params)

        # Log usage for non-streaming immediately
        # Keep INFO log for usage stats
        if not stream and isinstance(response, anthropic.types.Message) and response.usage:
            logger.info(f"Anthropic API Usage: Input={response.usage.input_tokens}, Output={response.usage.output_tokens}")

        return response

    def _process_response(self, response: anthropic.types.Message) -> str:
        """Extracts text content from a non-streaming Anthropic response."""
        if not response.content:
            # Keep warning for empty content
            logger.warning("Received empty content list from Anthropic.")
            return ""

        full_text = ""
        for block in response.content:
            if block.type == "text":
                full_text += block.text
            else:
                logger.debug(f"Ignoring non-text content block of type: {block.type}")

        if not full_text and response.stop_reason:
            # Keep warning if no text but stop reason exists
            logger.warning(f"Received no text content, but got stop reason: {response.stop_reason}")

        return full_text.strip()

    def _process_stream_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> Optional[str]:
        """Extracts text delta from an Anthropic stream chunk."""
        if chunk.type == "content_block_delta" and chunk.delta.type == "text_delta":
            return chunk.delta.text
        elif chunk.type == "message_start":
            logger.debug(f"Stream started (Input Tokens: {chunk.message.usage.input_tokens})")
        elif chunk.type == "message_delta":
            if chunk.usage.output_tokens > 0: # Log usage as it updates
                logger.debug(f"Stream delta usage update: Output={chunk.usage.output_tokens}")
        elif chunk.type == "message_stop":
            logger.debug("Stream finished.")
            # BaseClient handles the overall completion logging
        # Ignore other event types (ping, content_block_start/stop)
        return None # No text delta for these events

    # --- Optional: Provide SDK-specific error details ---
    def _get_sdk_exception_types(self) -> Tuple[Type[Exception], ...]:
        # Keep this as is
        return (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.APIStatusError,
            anthropic.APIError # Catch broader SDK errors
        )

    def _extract_error_details(self, error: Exception) -> Tuple[Optional[int], str]:
        # Keep this as is
        status_code = getattr(error, 'status_code', None)
        message = getattr(error, 'message', str(error)) # Default message

        # Try to get more specific message from Anthropic's error body
        if isinstance(error, anthropic.APIStatusError):
            error_body = getattr(error, 'body', None)
            if isinstance(error_body, dict) and 'error' in error_body:
                message = error_body.get('error', {}).get('message', message)

        return status_code, message

    # chat_completion and stream_chat_completion are now inherited from BaseClient
