import importlib
import os
import logging
import asyncio # Import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, AsyncIterator, Union
import httpx # Keep httpx here if subclasses *might* use it for other things, otherwise remove

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
    name: str
    context_length: int
    pricing: PricingTier

@dataclass
class ProviderConfig:
    name: str
    api_base: str
    api_key_env: str
    models: Dict[str, ModelConfig]
    default_model: str
    requires_import: Optional[str] = None
    # Shared client settings can be defined here if applicable
    default_timeout: float = 30.0
    default_max_retries: int = 2

@dataclass
class UsageStats:
    input_tokens: int
    output_tokens: int
    cost: Optional[float] = None # Cost calculation might be provider-specific

class BaseClient:
    """
    Abstract base class for LLM API clients.
    Handles common initialization like API key loading, dependency checking,
    and managing provider-specific SDK clients.
    """
    def __init__(self, config: ProviderConfig):
        """
        Initializes the BaseClient.

        Args:
            config: The configuration specific to the LLM provider.
        """
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        # Allow subclasses to override timeout/retries in their __init__ *before* calling super()
        # or by setting the attributes before _initialize() is called.
        # Defaulting here based on config.
        self.timeout = getattr(self, 'timeout', config.default_timeout)
        self.max_retries = getattr(self, 'max_retries', config.default_max_retries)
        self.default_model = config.default_model
        self.client: Any = None # Primary provider SDK client (e.g., AsyncAnthropic)

        # Perform initialization steps
        self._initialize()

    def _initialize(self):
        """Performs common initialization steps."""
        if not self.api_key:
            raise ValueError(f"API key not found in environment variable {self.config.api_key_env}")

        # Check for required Python package dependency
        try:
            if self.config.requires_import:
                importlib.import_module(self.config.requires_import)
                logger.debug(f"Successfully imported required package '{self.config.requires_import}' for {self.config.name}.")
        except ImportError as e:
            raise ImportError(f"Required package '{self.config.requires_import}' not installed for {self.config.name} client.") from e

        # Initialize the provider-specific SDK client
        try:
            # _initialize_provider_client should return the SDK client instance
            self.client = self._initialize_provider_client()
            if self.client is None and self.config.requires_import: # If import required, client shouldn't be None
                 # Added check: If an import is required, the provider client should be initialized.
                 logger.warning(f"_initialize_provider_client for {self.config.name} returned None despite requiring import '{self.config.requires_import}'.")
                 # Consider raising error here depending on strictness desired.
                 # raise RuntimeError(f"_initialize_provider_client for {self.config.name} returned None.")

            logger.info(f"{self.config.name} client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize {self.config.name} provider client: {e}", exc_info=True)
            # No http_client to clean up here anymore
            raise RuntimeError(f"{self.config.name} client initialization failed: {str(e)}") from e

    def _initialize_provider_client(self) -> Any:
        """
        Initializes and returns the specific provider's SDK client (e.g., AsyncAnthropic, AsyncOpenAI).
        Must be implemented by subclasses.
        Should raise exceptions on failure.
        """
        raise NotImplementedError("Subclasses must implement _initialize_provider_client")

    async def close(self):
        """Clean up resources, like the provider's SDK client if needed."""
        closed_provider = False
        client_to_close = self.client
        if client_to_close: # Use a temporary variable to avoid issues if self.client is set to None concurrently
            try:
                logger.debug(f"Attempting to close provider client for {self.config.name}...")
                # --- CORRECTED Logic ---
                if hasattr(client_to_close, 'aclose'):
                    # Check if it's awaitable
                    if asyncio.iscoroutinefunction(client_to_close.aclose) or asyncio.iscoroutine(client_to_close.aclose):
                        logger.debug("Using await client.aclose()")
                        await client_to_close.aclose()
                        closed_provider = True
                    # If aclose exists but isn't async (unusual), try calling it
                    elif callable(client_to_close.aclose):
                         logger.debug("Using client.aclose() (sync)")
                         client_to_close.aclose() # type: ignore
                         closed_provider = True

                elif hasattr(client_to_close, 'close') and callable(client_to_close.close):
                    # Fallback to sync close if aclose doesn't exist
                    # Consider running sync close in thread pool if it blocks significantly
                    # For simplicity here, just call it directly.
                    logger.debug("Using client.close() (sync)")
                    # await asyncio.to_thread(client_to_close.close) # Option for thread pool
                    client_to_close.close()
                    closed_provider = True
                else:
                     logger.debug(f"Provider client for {self.config.name} has no 'aclose' or 'close' method.")
                # --- END CORRECTED Logic ---

            except Exception as e:
                logger.error(f"Error closing provider ({self.config.name}) client: {e}", exc_info=True)
            finally:
                # Set client to None regardless of close success/failure
                self.client = None # Ensure it's set to None after attempting close

        if closed_provider:
            logger.info(f"{self.config.name} client resources closed.")
        # else: logger.debug(f"{self.config.name} client had no close method or was already None.")


    def get_available_models(self) -> List[str]:
        """Returns a list of model names configured for this provider."""
        return list(self.config.models.keys())

    def get_model_config(self, model_name: Optional[str] = None) -> ModelConfig:
        """Gets the configuration for a specific model by its key name."""
        effective_model_key = model_name or self.default_model
        model_conf = self.config.models.get(effective_model_key)
        if not model_conf:
            raise ValueError(f"Model key '{effective_model_key}' not found in {self.config.name} configuration. Available keys: {self.get_available_models()}")
        # Ensure the returned object is indeed a ModelConfig instance (due to potential config structure issues)
        if not isinstance(model_conf, ModelConfig):
            # This might happen if the config dict wasn't structured correctly initially
            logger.error(f"Configuration for model key '{effective_model_key}' in {self.config.name} is not a valid ModelConfig object. Found: {type(model_conf)}")
            raise TypeError(f"Invalid configuration type for model key '{effective_model_key}'. Expected ModelConfig.")
        return model_conf

    def _format_messages(self, messages: List[Message]) -> Any:
        """
        Formats a list of Message objects into the structure expected by the specific provider's API.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _format_messages")

    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        """
        Gets a standard (non-streaming) chat completion from the provider.
        Must be implemented by subclasses.
        Should handle selecting the model (using get_model_config), formatting messages,
        calling the API, and processing the response to return the text content.
        """
        raise NotImplementedError("Subclasses must implement chat_completion")

    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """
        Gets a streaming chat completion from the provider, yielding text chunks.
        Must be implemented by subclasses.
        Should handle model selection, message formatting, calling the streaming API,
        and yielding processed text chunks.
        """
        raise NotImplementedError("Subclasses must implement stream_chat_completion")
        # Required yield to satisfy AsyncIterator type hint if subclass doesn't implement
        if False: # pragma: no cover
            yield ""
