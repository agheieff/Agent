import importlib
import os
import logging
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, AsyncIterator, Union, Type, Tuple
import httpx # Keep for potential non-SDK HTTP needs, though not used in core flow now

logger = logging.getLogger(__name__)

@dataclass
class Message:
    role: str  # "system", "user", "assistant"
    content: Union[str, List[Dict[str, Any]]] # Allow complex content (e.g., images)

@dataclass
class PricingTier:
    input: float  # cost per 1,000,000 input tokens
    output: float # cost per 1,000,000 output tokens
    input_cache_miss: float = 0.0
    output_cache_miss: float = 0.0
    discount_hours: Optional[tuple] = None
    discount_rate: float = 0.0

@dataclass
class ModelConfig:
    name: str # API-specific model identifier (e.g., "claude-3-5-sonnet-20240620")
    context_length: int
    pricing: PricingTier

@dataclass
class ProviderConfig:
    name: str # Internal provider name (e.g., "anthropic")
    api_base: str
    api_key_env: str
    models: Dict[str, ModelConfig] # Key is internal name (e.g., "claude-3-5-sonnet"), value is config
    default_model: str # Internal default model key
    requires_import: Optional[str] = None
    default_timeout: float = 60.0 # Increased default timeout
    default_max_retries: int = 2

@dataclass
class UsageStats:
    input_tokens: int
    output_tokens: int
    cost: Optional[float] = None # Cost calculation might be provider-specific


class BaseClient:
    """
    Abstract base class for LLM API clients.
    Handles common logic: API key loading, dependency checks, client initialization,
    model selection, API call workflow, and common error handling.
    """
    def __init__(self, config: ProviderConfig):
        """Initializes the BaseClient."""
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        # Allow subclasses to set timeout/retries before super() or _initialize()
        self.timeout = getattr(self, 'timeout', config.default_timeout)
        self.max_retries = getattr(self, 'max_retries', config.default_max_retries)
        self.default_model = config.default_model # Internal key for the default model
        self.client: Any = None # Lazily initialized provider SDK client

        # Perform essential checks immediately
        self._check_api_key()
        self._check_dependencies()
        logger.info(f"{self.config.name} client configured. SDK client will be initialized on first call.")

    def _check_api_key(self):
        """Checks if the API key is present."""
        if not self.api_key:
            raise ValueError(f"API key not found in environment variable {self.config.api_key_env} for provider {self.config.name}")

    def _check_dependencies(self):
        """Checks for required Python package dependencies."""
        if self.config.requires_import:
            try:
                importlib.import_module(self.config.requires_import)
                logger.debug(f"Successfully imported required package '{self.config.requires_import}' for {self.config.name}.")
            except ImportError as e:
                raise ImportError(f"Required package '{self.config.requires_import}' not installed for {self.config.name} client.") from e

    async def _ensure_client_initialized(self):
        """Initializes the provider-specific client if not already done."""
        if self.client is None:
            logger.debug(f"Initializing provider client for {self.config.name}...")
            try:
                # Subclass implements the actual SDK client creation
                self.client = await asyncio.to_thread(self._initialize_provider_client)
                if self.client is None:
                    raise RuntimeError(f"_initialize_provider_client for {self.config.name} returned None.")
                logger.info(f"{self.config.name} provider client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize {self.config.name} provider client: {e}", exc_info=True)
                raise RuntimeError(f"{self.config.name} client initialization failed: {str(e)}") from e

    # --- Methods for Subclasses to Implement ---

    def _initialize_provider_client(self) -> Any:
        """
        (Synchronous) Initializes and returns the specific provider's SDK client
        (e.g., anthropic.Anthropic(), openai.OpenAI()).
        Must be implemented by subclasses. Should raise exceptions on failure.
        Called via asyncio.to_thread by _ensure_client_initialized.
        """
        raise NotImplementedError("Subclasses must implement _initialize_provider_client")

    def _format_messages(self, messages: List[Message]) -> Any:
        """
        Formats a list of Message objects into the structure expected by the specific provider's API.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _format_messages")

    async def _execute_api_call(
        self,
        formatted_messages: Any,
        api_model_name: str,
        stream: bool,
        **kwargs
    ) -> Union[Any, AsyncIterator[Any]]:
        """
        Executes the actual API call using the provider's SDK.
        Must be implemented by subclasses.
        Should return the raw SDK response object for non-streaming calls,
        or an async iterator of raw SDK chunk objects for streaming calls.
        Error handling for SDK exceptions should be done within this method
        only if it needs very specific handling; otherwise, let exceptions
        propagate to the base class handler.
        """
        raise NotImplementedError("Subclasses must implement _execute_api_call")

    def _process_response(self, response: Any) -> str:
        """
        Extracts the complete text content from a non-streaming SDK response object.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _process_response")

    def _process_stream_chunk(self, chunk: Any) -> Optional[str]:
        """
        Extracts the text delta from a streaming SDK chunk object.
        Return None if the chunk does not contain a text delta.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _process_stream_chunk")

    # --- Optional Methods for Subclasses to Override for Better Error Handling ---

    def _get_sdk_exception_types(self) -> Tuple[Type[Exception], ...]:
        """
        Returns a tuple of provider-specific SDK exception classes to catch.
        Example: return (anthropic.APIConnectionError, anthropic.RateLimitError, ...)
        """
        return () # Default: No specific types

    def _extract_error_details(self, error: Exception) -> Tuple[Optional[int], str]:
        """
        Extracts the status code (if available) and a detailed message from an SDK error.
        Returns: (status_code, message_string)
        """
        # Basic fallback
        status_code = getattr(error, 'status_code', None)
        message = getattr(error, 'message', str(error))
        return status_code, message

    # --- Public Methods ---

    async def close(self):
        """Clean up resources, like the provider's SDK client if needed."""
        if self.client:
            try:
                logger.debug(f"Attempting to close provider client for {self.config.name}...")
                if hasattr(self.client, 'aclose') and callable(self.client.aclose):
                    if asyncio.iscoroutinefunction(self.client.aclose) or asyncio.iscoroutine(self.client.aclose()):
                        await self.client.aclose()
                    else:
                        self.client.aclose() # type: ignore
                    logger.info(f"{self.config.name} client closed via aclose().")
                elif hasattr(self.client, 'close') and callable(self.client.close):
                    # Run sync close in thread pool
                    await asyncio.to_thread(self.client.close)
                    logger.info(f"{self.config.name} client closed via close().")
                else:
                    logger.debug(f"Provider client for {self.config.name} has no 'aclose' or 'close' method.")
            except Exception as e:
                logger.error(f"Error closing provider ({self.config.name}) client: {e}", exc_info=True)
            finally:
                self.client = None # Ensure client is marked as closed

    def get_available_models(self) -> List[str]:
        """Returns a list of *internal* model keys configured for this provider."""
        return list(self.config.models.keys())

    def get_model_config(self, model_key: Optional[str] = None) -> ModelConfig:
        """Gets the configuration for a specific model by its internal key name."""
        effective_model_key = model_key or self.default_model
        model_conf = self.config.models.get(effective_model_key)
        if not model_conf:
            raise ValueError(f"Model key '{effective_model_key}' not found in {self.config.name} configuration. Available keys: {self.get_available_models()}")
        if not isinstance(model_conf, ModelConfig): # Ensure correct type
            logger.error(f"Configuration for model key '{effective_model_key}' in {self.config.name} is not a valid ModelConfig object. Found: {type(model_conf)}")
            raise TypeError(f"Invalid configuration type for model key '{effective_model_key}'. Expected ModelConfig.")
        return model_conf

    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        """
        Gets a standard (non-streaming) chat completion. Handles initialization,
        formatting, API call execution, response processing, and error handling.
        """
        await self._ensure_client_initialized()
        if not self.client: # Should be initialized now
            raise RuntimeError(f"{self.config.name} client failed to initialize.")

        effective_model_key = model or self.default_model
        try:
            model_config = self.get_model_config(effective_model_key)
            api_model_name = model_config.name # Get the name to send to the API
            logger.debug(f"Using API model name: '{api_model_name}' for internal key '{effective_model_key}'")

            formatted_messages = self._format_messages(messages)
            if formatted_messages is None: # Check if formatting failed
                raise ValueError("Message formatting failed.")

            # Prepare common parameters (subclass _execute_api_call can override/add)
            params = {
                'max_tokens': kwargs.pop('max_tokens', 4096),
                'temperature': kwargs.pop('temperature', 0.7),
                **kwargs # Pass remaining kwargs
            }
            logger.debug(f"Calling {self.config.name} API (model: {api_model_name}, stream: False) with params: {params}")

            # Execute API call via subclass implementation
            raw_response = await self._execute_api_call(
                formatted_messages=formatted_messages,
                api_model_name=api_model_name,
                stream=False,
                **params
            )

            # Process response via subclass implementation
            content = self._process_response(raw_response)
            # Log usage (if available - subclass _process_response could potentially extract it)
            # Consider adding optional usage return from _process_response
            logger.info(f"{self.config.name} chat completion successful.")
            return content

        except self._get_sdk_exception_types() as e:
            status_code, err_msg = self._extract_error_details(e)
            status_str = f" (Status: {status_code})" if status_code else ""
            log_msg = f"{self.config.name} API Error{status_str}: {err_msg}"
            logger.error(log_msg, exc_info=False) # exc_info=False as details are extracted
            # Check for potential model name errors
            err_msg_lower = err_msg.lower()
            if "model" in err_msg_lower or "not found" in err_msg_lower or (status_code in [400, 404]):
                api_model_name_attempt = self.get_model_config(effective_model_key).name # Re-fetch for logging
                logger.error(f"Potential invalid model name used: '{api_model_name_attempt}'. Verify config for key '{effective_model_key}'.")
            raise RuntimeError(log_msg) from e
        except Exception as e: # Catch other unexpected errors
            logger.error(f"Unexpected error during {self.config.name} chat completion: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error during API call: {str(e)}") from e

    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """
        Gets a streaming chat completion, yielding text chunks. Handles initialization,
        formatting, API call execution, stream processing, and error handling.
        """
        await self._ensure_client_initialized()
        if not self.client:
            raise RuntimeError(f"{self.config.name} client failed to initialize.")

        effective_model_key = model or self.default_model
        stream_iterator = None # Define variable for finally block

        try:
            model_config = self.get_model_config(effective_model_key)
            api_model_name = model_config.name
            logger.debug(f"Using API model name: '{api_model_name}' for internal key '{effective_model_key}'")

            formatted_messages = self._format_messages(messages)
            if formatted_messages is None:
                raise ValueError("Message formatting failed.")

            params = {
                'max_tokens': kwargs.pop('max_tokens', 4096),
                'temperature': kwargs.pop('temperature', 0.7),
                **kwargs
            }
            logger.debug(f"Calling {self.config.name} API (model: {api_model_name}, stream: True) with params: {params}")

            # Execute streaming API call via subclass
            stream_iterator = await self._execute_api_call(
                formatted_messages=formatted_messages,
                api_model_name=api_model_name,
                stream=True,
                **params
            )

            if not hasattr(stream_iterator, '__aiter__'):
                logger.error(f"Internal Error: _execute_api_call did not return an async iterator for streaming. Got: {type(stream_iterator)}")
                raise RuntimeError("Internal error: Failed to obtain stream iterator.")

            # Process stream via subclass implementation
            async for chunk in stream_iterator:
                text_delta = self._process_stream_chunk(chunk)
                if text_delta is not None: # Yield only if chunk contained text
                    yield text_delta
            logger.info(f"{self.config.name} stream completed.")

        except self._get_sdk_exception_types() as e:
            status_code, err_msg = self._extract_error_details(e)
            status_str = f" (Status: {status_code})" if status_code else ""
            log_msg = f"{self.config.name} API Error during streaming{status_str}: {err_msg}"
            logger.error(log_msg, exc_info=False)
            err_msg_lower = err_msg.lower()
            if "model" in err_msg_lower or (status_code in [400, 404]):
                api_model_name_attempt = self.get_model_config(effective_model_key).name
                logger.error(f"Potential invalid model name used in stream: '{api_model_name_attempt}'. Check config key '{effective_model_key}'.")
            raise RuntimeError(log_msg) from e
        except Exception as e:
            logger.error(f"Unexpected error during {self.config.name} streaming: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected streaming error: {str(e)}") from e
        finally:
            # Attempt to close the stream iterator if it exists and has aclose
            if stream_iterator and hasattr(stream_iterator, 'aclose'):
                try:
                    await stream_iterator.aclose()
                    logger.debug(f"{self.config.name} stream context closed.")
                except Exception as close_err:
                    logger.warning(f"Error closing {self.config.name} stream context: {close_err}", exc_info=False)
