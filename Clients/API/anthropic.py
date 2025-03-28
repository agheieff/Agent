import os
import logging
import uuid # For generating unique request IDs (if needed elsewhere, not for MCP now)
from typing import Dict, List, Optional, Any, AsyncIterator, Union, Tuple

# Removed httpx import as MCP calls are moved

import anthropic

# Use relative imports for components within the same package
from ..base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

# --- Removed MCP related imports and fallback logic ---
# MCP imports are no longer needed here

logger = logging.getLogger(__name__)


# --- Configuration ---
# User requested not to change this section, keeping it as is.
# NOTE: User should verify model names like "claude-3-7-sonnet-latest" are valid API IDs.
ANTHROPIC_CONFIG = ProviderConfig(
    name="anthropic",
    api_base="https://api.anthropic.com",
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
        # Note: These keys/names might need adjustment to match valid Anthropic API model IDs
        # e.g., "claude-3-5-sonnet-20240620"
    }
)
# --- End Configuration ---


class AnthropicClient(BaseClient):
    def __init__(self, config: ProviderConfig = None):
        """
        Initializes the AnthropicClient.

        Args:
            config: Provider configuration. Defaults to ANTHROPIC_CONFIG.
        """
        # Assign config, potentially overriding base class defaults for timeout/retries
        effective_config = config or ANTHROPIC_CONFIG

        # --- Set client-specific defaults *before* calling super().__init__ ---
        self.timeout = 60.0  # Increased timeout specific to Anthropic
        self.max_retries = 2 # Reduced default retries specific to Anthropic
        # --- End specific defaults ---

        # Call BaseClient's __init__ to handle common setup (API key, SDK check)
        super().__init__(effective_config)

        # Note: self.default_model is set by BaseClient using the effective_config


    def _initialize_provider_client(self) -> anthropic.AsyncAnthropic:
        """Initializes the Anthropic SDK client."""
        # api_key check is done in BaseClient's __init__
        if not self.api_key: # Should not happen if BaseClient init worked
             raise RuntimeError("API key not set during BaseClient initialization.")

        try:
            # Use timeout/retries potentially set in __init__ before super() call
            async_anthropic_client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
            logger.info("Anthropic AsyncClient initialized successfully.")
            return async_anthropic_client
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic AsyncClient: {e}", exc_info=True)
            raise # Re-raise for BaseClient to handle

    def _format_messages(self, messages: List[Message]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Formats a list of Message objects into the structure Anthropic API expects.
        Separates the system prompt. Handles potential multi-part content and merges consecutive roles.
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
                        # Concatenate multiple system messages (Anthropic supports one)
                        system_prompt += "\n" + msg.content
                        logger.warning("Multiple system messages found. Concatenating them.")
                else:
                    logger.warning(f"System message content is not a string: {type(msg.content)}. Skipping.")
            elif msg.role in ["user", "assistant"]:
                non_system_messages.append(msg)
            else:
                logger.warning(f"Unsupported message role '{msg.role}'. Skipping message.")

        # 2. Format and merge user/assistant messages
        last_role = None
        for msg in non_system_messages:
            if isinstance(msg.content, str):
                # Handle simple text content
                content_list = [{"type": "text", "text": msg.content}]
            # Example placeholder for handling pre-formatted complex content (e.g., images)
            # elif isinstance(msg.content, list):
            #     content_list = msg.content # Assume content is already a valid list of blocks
            else:
                logger.warning(f"Unsupported message content type: {type(msg.content)}. Treating as empty text.")
                content_list = [{"type": "text", "text": ""}]

            # Merge with previous message if same role
            if formatted and formatted[-1]["role"] == msg.role:
                 # Ensure previous content is a list before extending
                 if isinstance(formatted[-1]["content"], list):
                     formatted[-1]["content"].extend(content_list)
                     logger.debug(f"Merging consecutive '{msg.role}' message content.")
                 else:
                     # This case shouldn't happen with current logic, but safeguard anyway
                     logger.warning(f"Cannot merge content: Previous message content is not a list. Appending new message block.")
                     formatted.append({"role": msg.role, "content": content_list})
            else:
                # Start a new message block
                formatted.append({"role": msg.role, "content": content_list})
            last_role = msg.role

        # 3. Validation: Anthropic requires the first message to be 'user' if history is not empty
        if formatted and formatted[0]['role'] != 'user':
            logger.error("Anthropic API Error: First message in history must be from the 'user' role.")
            # Raise an error to prevent an invalid API call
            raise ValueError("Conversation history for Anthropic must start with a 'user' message.")
            # Alternative: logger.warning("First message is not 'user'. This will likely cause an API error.")

        return formatted, system_prompt


    async def _call_api(self, messages: List[Message], model_key: str, stream: bool = False, **kwargs) -> Union[anthropic.types.Message, AsyncIterator[anthropic.types.MessageStreamEvent]]:
        """
        Internal method to make the actual Anthropic API call.

        Args:
            messages: List of Message objects (including potential system message).
            model_key: The key for the model in the ProviderConfig (e.g., "claude-3-7-sonnet").
            stream: Whether to stream the response.
            **kwargs: Additional parameters for the Anthropic API (e.g., max_tokens, temperature).

        Returns:
            The API response object (Message or MessageStreamEvent iterator).

        Raises:
            RuntimeError: If client not initialized or on API errors.
            ValueError: If formatting fails or arguments are invalid.
            ConnectionError: On network issues contacting the API.
        """
        if not self.client:
            raise RuntimeError("Anthropic client is not initialized.")

        # Use the config key (e.g., "claude-3-7-sonnet") to find the ModelConfig
        model_config = self.get_model_config(model_key) # Use BaseClient's method
        # Get the specific name to send to the API (e.g., "claude-3-7-sonnet-latest")
        api_model_name = model_config.name
        logger.debug(f"Using API model name: '{api_model_name}' for config key '{model_key}'")

        # Format messages, separating system prompt
        formatted_msgs, system_prompt = self._format_messages(messages)

        if not formatted_msgs and not system_prompt:
            raise ValueError("Cannot make API call with no messages and no system prompt.")
        # Anthropic requires at least one message if system prompt is used alone
        elif system_prompt and not formatted_msgs:
             logger.error("Anthropic requires at least one user/assistant message when a system prompt is provided.")
             raise ValueError("Cannot call Anthropic API with only a system prompt.")


        # --- Prepare API Parameters ---
        params = {
            "messages": formatted_msgs,
            "model": api_model_name, # Use the name from ModelConfig
            "max_tokens": kwargs.get('max_tokens', 4096), # Default max_tokens
            "temperature": kwargs.get('temperature', 0.7), # Default temperature
            "stream": stream,
        }
        if system_prompt:
            params["system"] = system_prompt
            logger.debug(f"Using system prompt: '{system_prompt[:100]}...'")

        # Add other valid Anthropic parameters if provided in kwargs
        valid_anthropic_params = {"top_p", "top_k", "stop_sequences"}
        for key, value in kwargs.items():
            if key in valid_anthropic_params:
                params[key] = value
        # --- End Parameter Preparation ---

        logger.debug(f"Calling Anthropic API (model: {api_model_name}, stream: {stream}) with params "
                     f"(excluding messages/system): {{k: v for k, v in params.items() if k not in ['messages', 'system']}}")

        try:
            # Make the API call
            if stream:
                # Type hint indicates AsyncAnthropic is expected here
                response_stream = await self.client.messages.create(**params)
                return response_stream
            else:
                response = await self.client.messages.create(**params)
                if response.usage:
                    logger.info(f"Anthropic API Usage: Input={response.usage.input_tokens}, Output={response.usage.output_tokens}")
                return response
        except anthropic.APIConnectionError as e:
            logger.error(f"Anthropic API Connection Error: {e}", exc_info=True)
            raise ConnectionError(f"Connection error contacting Anthropic API: {e}") from e
        except anthropic.RateLimitError as e:
            logger.error(f"Anthropic Rate Limit Error: {e}", exc_info=True)
            # Use getattr for safety in accessing potential attributes
            raise RuntimeError(f"Anthropic API rate limit exceeded: {getattr(e, 'message', str(e))}") from e
        except anthropic.APIStatusError as e:
            # Extract more detailed error message if available
            error_message = getattr(e, 'message', str(e))
            error_body = getattr(e, 'body', None)
            if isinstance(error_body, dict) and 'error' in error_body:
                 # Anthropic often returns JSON like {'error': {'type': '...', 'message': '...'}}
                 error_message = error_body.get('error', {}).get('message', error_message)

            logger.error(f"Anthropic API Status Error: {e.status_code} - {error_message}", exc_info=False) # exc_info=False to avoid redundant traceback

            # Check specifically for potential model-related errors
            err_msg_lower = error_message.lower()
            if "model" in err_msg_lower or "not found" in err_msg_lower or e.status_code in [400, 404]:
                logger.error(f"Potential invalid model name used: '{api_model_name}'. Verify this is a valid, available model ID for your API key and matches the 'name' field in config for key '{model_key}'.")

            # Chain the exception for better debugging
            raise RuntimeError(f"Anthropic API error: {e.status_code} - {error_message}") from e
        except anthropic.APIError as e: # Catch broader API errors
            logger.error(f"Generic Anthropic API Error: {e}", exc_info=True)
            raise RuntimeError(f"Generic Anthropic API error: {getattr(e, 'message', str(e))}") from e
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error during Anthropic API call: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error during API call: {str(e)}") from e

    def _process_response(self, response: anthropic.types.Message) -> str:
        """Extracts the text content from a standard (non-streaming) API response."""
        if not response.content:
            logger.warning("Received empty content list from Anthropic.")
            return ""

        full_text = ""
        for block in response.content:
            if block.type == "text":
                full_text += block.text
            else:
                # Handle or log other content block types if necessary (e.g., tool_calls)
                logger.warning(f"Ignoring non-text content block of type: {block.type}")

        if not full_text and response.stop_reason:
             logger.warning(f"Received no text content, but got stop reason: {response.stop_reason}")
             # Optionally return stop reason or other metadata if no text
             # return f"[No text content, stop reason: {response.stop_reason}]"

        return full_text.strip()


    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        """Gets a standard chat completion from Anthropic."""
        effective_model_key = model or self.default_model
        # Call internal API method, passing the model *key*
        response = await self._call_api(messages=messages, model_key=effective_model_key, stream=False, **kwargs)

        # Process the response object
        if isinstance(response, anthropic.types.Message):
            return self._process_response(response)
        else:
            # This case should not happen if stream=False
            logger.error(f"Internal Error: Unexpected response type for non-streaming call: {type(response)}")
            raise RuntimeError("Internal error: Unexpected response type received from _call_api")


    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """Streams chat completions from Anthropic, yielding text chunks."""
        effective_model_key = model or self.default_model
        stream = None

        try:
            # Call internal API method for streaming
            stream = await self._call_api(messages=messages, model_key=effective_model_key, stream=True, **kwargs)

            if not hasattr(stream, '__aiter__'):
                # This indicates an issue with _call_api or the SDK response
                logger.error(f"Internal Error: _call_api did not return an async iterator for streaming. Got: {type(stream)}")
                raise RuntimeError("Internal error: Failed to obtain stream iterator.")

            # Iterate through the stream events
            async for event in stream:
                if event.type == "content_block_delta":
                    # Check if the delta is text
                    if event.delta.type == "text_delta":
                        yield event.delta.text
                elif event.type == "message_start":
                    # Log stream initiation, potentially including metadata
                    logger.debug(f"Stream started for model: {event.message.model} (Usage Input: {event.message.usage.input_tokens})")
                elif event.type == "message_delta":
                     # Contains changes to message metadata (e.g., stop_reason, usage)
                     if event.usage.output_tokens > 0: # Log usage as it updates
                         logger.debug(f"Stream delta usage update: Output={event.usage.output_tokens}")
                elif event.type == "message_stop":
                    # Log stream completion
                    logger.debug("Stream finished.")
                    # Get final message details (including usage) after stream ends
                    # final_message = await stream.get_final_message() # Available in recent SDK versions
                    # if final_message and final_message.usage:
                    #      logger.info(f"Stream Final Usage: Input={final_message.usage.input_tokens}, Output={final_message.usage.output_tokens}")
                    break # Exit the loop cleanly on message_stop
                # Ignore other event types for simplicity (e.g., content_block_start/stop, ping)

        # --- Exception Handling for Streaming ---
        # Duplicating relevant parts from _call_api error handling, adapted for stream context
        except anthropic.APIConnectionError as e:
            logger.error(f"Connection error during streaming: {e}", exc_info=True)
            raise ConnectionError(f"Connection error during streaming: {e}") from e
        except anthropic.APIStatusError as e:
             error_message = getattr(e, 'message', str(e))
             error_body = getattr(e, 'body', None)
             if isinstance(error_body, dict) and 'error' in error_body:
                 error_message = error_body.get('error', {}).get('message', error_message)
             logger.error(f"API status error during streaming: {e.status_code} - {error_message}", exc_info=False)
             err_msg_lower = error_message.lower()
             if "model" in err_msg_lower or e.status_code in [400, 404]:
                 api_model_name = self.get_model_config(effective_model_key).name
                 logger.error(f"Potential invalid model name used in stream: '{api_model_name}'. Check config key '{effective_model_key}'.")
             raise RuntimeError(f"API error during streaming: {e.status_code} - {error_message}") from e
        except anthropic.APIError as e:
            logger.error(f"Generic Anthropic API error during streaming: {e}", exc_info=True)
            raise RuntimeError(f"Generic API error during streaming: {getattr(e, 'message', str(e))}") from e
        except Exception as e:
            logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected streaming error: {str(e)}") from e
        # --- End Streaming Exception Handling ---
        finally:
            # Ensure the stream context is closed if it exists and has an aclose method
            if stream and hasattr(stream, 'aclose'):
                try:
                    await stream.aclose()
                    logger.debug("Anthropic stream context closed.")
                except Exception as close_err:
                    logger.error(f"Error closing Anthropic stream context: {close_err}", exc_info=True)

    # --- execute_mcp_operation removed ---
    # This method is now handled by AgentRunner
