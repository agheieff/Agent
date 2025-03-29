import openai
import os
import logging
from typing import Dict, List, Optional, Any, AsyncIterator, Union # Added AsyncIterator, Union

# Use relative imports within the package
from ..base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

# --- Configuration (Keep as is per user request) ---
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
    },
    default_timeout=30.0,
    default_max_retries=2
)
# --- End Configuration ---

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseClient):
    def __init__(self, config: Optional[ProviderConfig] = None):
        """Initializes the DeepSeekClient."""
        effective_config = config or DEEPSEEK_CONFIG
        # Set provider-specific defaults *before* calling super().__init__ if needed
        # self.timeout = effective_config.default_timeout
        # self.max_retries = effective_config.default_max_retries
        super().__init__(effective_config)
        # self.default_model is set by BaseClient using effective_config

    def _initialize_provider_client(self) -> Any:
        """Initializes and returns the OpenAI SDK client configured for DeepSeek."""
        # api_key check is done in BaseClient's __init__
        if not self.api_key: # Should not happen if BaseClient init worked
             raise RuntimeError("API key not set during BaseClient initialization.")

        try:
            # Import openai here, as it's a required dependency checked by BaseClient
            import openai
            # Use timeout/retries from BaseClient attributes (which use config defaults)
            async_client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.config.api_base,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
            logger.info("DeepSeek client (via AsyncOpenAI) initialized successfully.")
            return async_client
        except ImportError: # Should be caught by BaseClient, but defensive check
             logger.error("OpenAI package not installed, which is required for DeepSeek client.")
             raise # Re-raise for BaseClient to handle if it missed it
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek client: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize DeepSeek client: {e}") from e


    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Formats messages for the OpenAI compatible API."""
        formatted = []
        for msg in messages:
            if isinstance(msg.content, str):
                formatted.append({"role": msg.role, "content": msg.content})
            else:
                 # Handle potential complex content if needed later (e.g., images)
                 # For now, log a warning and skip or represent as string
                 logger.warning(f"Unsupported content type {type(msg.content)} in DeepSeek message, converting to string.")
                 formatted.append({"role": msg.role, "content": str(msg.content)})
        return formatted

    async def _call_api(self,
                        messages: List[Message],
                        model_key: str,
                        stream: bool = False,
                        **kwargs) -> Union[openai.types.chat.ChatCompletion, AsyncIterator[openai.types.chat.ChatCompletionChunk]]:
        """Internal method to make the actual API call using the OpenAI client."""
        if not self.client:
            raise RuntimeError("DeepSeek client (AsyncOpenAI) is not initialized.")

        model_config = self.get_model_config(model_key)
        api_model_name = model_config.name
        logger.debug(f"Using API model name: '{api_model_name}' for config key '{model_key}'")

        formatted_msgs = self._format_messages(messages)
        if not formatted_msgs:
             raise ValueError("Cannot make API call with empty formatted messages.")

        # Prepare parameters
        params = {
            "messages": formatted_msgs,
            "model": api_model_name,
            "max_tokens": kwargs.get('max_tokens', 4096), # Default or from kwargs
            "temperature": kwargs.get('temperature', 0.7), # Default or from kwargs
            "stream": stream,
        }
        # Add other valid OpenAI/DeepSeek parameters if provided
        valid_extra_params = {"top_p", "frequency_penalty", "presence_penalty", "stop"}
        for key, value in kwargs.items():
             if key in valid_extra_params:
                  params[key] = value

        logger.debug(f"Calling DeepSeek API (model: {api_model_name}, stream: {stream}) with params "
                     f"(excluding messages): {{k: v for k, v in params.items() if k != 'messages'}}")

        try:
            # Make the API call using the initialized OpenAI client
            response = await self.client.chat.completions.create(**params)
            if not stream and hasattr(response, 'usage') and response.usage:
                 logger.info(f"DeepSeek API Usage: Input={response.usage.prompt_tokens}, Output={response.usage.completion_tokens}")
            return response
        # Use more specific exceptions from the openai library if possible
        except openai.APIConnectionError as e:
             logger.error(f"DeepSeek API Connection Error: {e}", exc_info=True)
             raise ConnectionError(f"Connection error contacting DeepSeek API: {e}") from e
        except openai.RateLimitError as e:
             logger.error(f"DeepSeek Rate Limit Error: {e}", exc_info=True)
             raise RuntimeError(f"DeepSeek API rate limit exceeded: {e}") from e
        except openai.APIStatusError as e:
             logger.error(f"DeepSeek API Status Error: {e.status_code} - {e.response.text}", exc_info=False)
             # Check for model errors
             err_msg_lower = str(e).lower()
             if "model" in err_msg_lower or e.status_code in [400, 404]:
                  logger.error(f"Potential invalid model name used: '{api_model_name}'. Verify config.")
             raise RuntimeError(f"DeepSeek API error: {e.status_code} - {e.message}") from e
        except openai.APIError as e:
             logger.error(f"Generic DeepSeek API Error: {e}", exc_info=True)
             raise RuntimeError(f"Generic DeepSeek API error: {e}") from e
        except Exception as e: # Catch any other unexpected errors
             logger.error(f"Unexpected error during DeepSeek API call: {e}", exc_info=True)
             raise RuntimeError(f"Unexpected error during API call: {str(e)}") from e

    def _process_response(self, response: openai.types.chat.ChatCompletion) -> str:
        """Extracts text content from a non-streaming response."""
        if not response.choices:
            logger.warning("Received no choices from DeepSeek.")
            return ""
        # Assuming the first choice is the one we want
        message = response.choices[0].message
        if not message or not message.content:
            logger.warning("Received choice but no message content from DeepSeek.")
            return ""
        return message.content.strip()

    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        """Gets a standard chat completion."""
        effective_model_key = model or self.default_model
        response = await self._call_api(messages=messages, model_key=effective_model_key, stream=False, **kwargs)

        if isinstance(response, openai.types.chat.ChatCompletion):
            return self._process_response(response)
        else:
            # This case should not happen if stream=False
            logger.error(f"Internal Error: Unexpected response type for non-streaming call: {type(response)}")
            raise RuntimeError("Internal error: Unexpected response type received from _call_api")

    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """Streams chat completions, yielding text chunks."""
        effective_model_key = model or self.default_model
        stream = None # Define stream variable

        try:
            stream = await self._call_api(messages=messages, model_key=effective_model_key, stream=True, **kwargs)

            if not hasattr(stream, '__aiter__'):
                 logger.error(f"Internal Error: _call_api did not return an async iterator for streaming. Got: {type(stream)}")
                 raise RuntimeError("Internal error: Failed to obtain stream iterator.")

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
                # Add handling for other stream events if needed (e.g., usage in finish_reason)
        # --- Exception Handling for Streaming (Copy relevant parts from _call_api) ---
        except openai.APIConnectionError as e:
            logger.error(f"Connection error during streaming: {e}", exc_info=True)
            raise ConnectionError(f"Connection error during streaming: {e}") from e
        except openai.APIStatusError as e:
            logger.error(f"API status error during streaming: {e.status_code} - {e.response.text}", exc_info=False)
            # Check for model errors
            err_msg_lower = str(e).lower()
            api_model_name = self.get_model_config(effective_model_key).name # Get name for logging
            if "model" in err_msg_lower or e.status_code in [400, 404]:
                 logger.error(f"Potential invalid model name used in stream: '{api_model_name}'. Check config key '{effective_model_key}'.")
            raise RuntimeError(f"API error during streaming: {e.status_code} - {e.message}") from e
        except openai.APIError as e:
            logger.error(f"Generic DeepSeek API error during streaming: {e}", exc_info=True)
            raise RuntimeError(f"Generic API error during streaming: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected streaming error: {str(e)}") from e
        # --- End Streaming Exception Handling ---
        finally:
            # Ensure the stream context is closed if it has an aclose method
            # Note: openai's AsyncStream might not need explicit closing like httpx's,
            # but checking doesn't hurt. Check openai SDK docs for specifics.
            if stream and hasattr(stream, 'aclose'):
                 try:
                     # Runtime check for coroutine status before awaiting
                     close_method = getattr(stream, 'aclose')
                     if asyncio.iscoroutinefunction(close_method) or asyncio.iscoroutine(close_method):
                          await close_method()
                          logger.debug("DeepSeek stream context closed.")
                     else: # If it's not a coroutine (unlikely for aclose), just call if callable
                          if callable(close_method):
                            close_method() # type: ignore
                            logger.debug("DeepSeek stream context closed (sync).")

                 except Exception as close_err:
                     logger.error(f"Error closing DeepSeek stream context: {close_err}", exc_info=True)
