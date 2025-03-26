import importlib
import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, AsyncIterator, Union
import httpx

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
    Abstract base class for API clients.
    Handles common initialization like API key loading, dependency checking,
    and managing shared HTTP clients.
    """
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        self.timeout = getattr(self, 'timeout', config.default_timeout) # Allow subclasses to override
        self.max_retries = getattr(self, 'max_retries', config.default_max_retries) # Allow subclasses to override
        self.default_model = config.default_model
        self.client: Any = None # Primary provider SDK client
        self.http_client: Optional[httpx.AsyncClient] = None # Shared client for other HTTP requests

        self._initialize()

    def _initialize(self):
        if not self.api_key:
            raise ValueError(f"API key not found in environment variable {self.config.api_key_env}")

        try:
            if self.config.requires_import:
                importlib.import_module(self.config.requires_import)
        except ImportError as e:
            raise ImportError(f"Required package '{self.config.requires_import}' not installed for {self.config.name} client.") from e

        try:
            self.client = self._initialize_provider_client()
            # Initialize a shared httpx client - useful for things like MCP calls
            self.http_client = httpx.AsyncClient(timeout=self.timeout)
            logger.info(f"{self.config.name} client initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize {self.config.name} client: {e}", exc_info=True)
            # Attempt cleanup if http_client was created before failure
            # Note: Proper async closing should happen in `close` method
            if self.http_client:
                 # Cannot await here, rely on close() or GC
                 pass
            raise RuntimeError(f"{self.config.name} client initialization failed: {str(e)}") from e

    def _initialize_provider_client(self) -> Any:
        """
        Initializes and returns the specific provider's SDK client (e.g., Anthropic, OpenAI).
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _initialize_provider_client")

    async def close(self):
        """Clean up resources, like HTTP clients and provider clients."""
        closed_http = False
        if self.http_client:
            try:
                await self.http_client.aclose()
                self.http_client = None
                closed_http = True
            except Exception as e:
                 logger.error(f"Error closing shared HTTP client: {e}", exc_info=True)

        closed_provider = False
        if self.client:
            try:
                if hasattr(self.client, 'aclose'):
                    await self.client.aclose()
                    closed_provider = True
                elif hasattr(self.client, 'close'):
                     # For synchronous close methods, consider running in thread pool if necessary
                    self.client.close()
                    closed_provider = True
            except Exception as e:
                 logger.error(f"Error closing provider ({self.config.name}) client: {e}", exc_info=True)

        if closed_http or closed_provider:
            logger.info(f"{self.config.name} client resources closed.")

    def get_available_models(self) -> List[str]:
        """Returns a list of model names available for this provider."""
        return list(self.config.models.keys())

    def get_model_config(self, model_name: Optional[str] = None) -> ModelConfig:
        """Gets the configuration for a specific model."""
        effective_model = model_name or self.default_model
        config = self.config.models.get(effective_model)
        if not config:
            raise ValueError(f"Model '{effective_model}' not found in {self.config.name} configuration.")
        return config

    def _format_messages(self, messages: List[Message]) -> Any:
        """
        Formats a list of Message objects into the structure expected by the provider's API.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _format_messages")

    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        """
        Gets a standard (non-streaming) chat completion.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement chat_completion")

    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """
        Gets a streaming chat completion, yielding text chunks.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement stream_chat_completion")
        yield "" # Required for AsyncIterator type hint satisfaction if not implemented

    async def execute_mcp_operation(self, operation_name: str, arguments: Dict[str, Any], mcp_server_url: str, agent_id: Optional[str]) -> Any:
        """
        Helper to execute an operation on a remote MCP server.
        Relies on the shared self.http_client.
        
        Returns:
            An MCPSuccessResponse if the operation succeeded, or an MCPErrorResponse if it failed.
            Raises RuntimeError if MCP package is not available.
        """
        # Import MCP modules - if they're not available, raise a clear error
        try:
            from MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
            from MCP.errors import ErrorCode, MCPError
        except ImportError:
            logger.error("MCP package not available. Cannot execute MCP operation.")
            raise RuntimeError("MCP package not available. This function requires the MCP module.")

        # Validate prerequisites
        if not mcp_server_url:
            logger.error("MCP_SERVER_URL not provided. Cannot execute MCP operation.")
            raise ValueError("MCP server URL not provided")

        if not self.http_client:
            logger.error("HTTP client not initialized. Cannot execute MCP operation.")
            raise RuntimeError("HTTP client not initialized")

        # Create request
        request_id = f"mcp-req-{os.urandom(4).hex()}"
        payload = MCPRequest(
            id=request_id,
            operation=operation_name,
            arguments=arguments,
            agent_id=agent_id
        )

        logger.info(f"Executing MCP operation '{operation_name}' via {mcp_server_url} (Agent: {agent_id}, Req ID: {request_id})")
        logger.debug(f"MCP Request Payload: {payload.model_dump()}")

        try:
            # Send request
            response = await self.http_client.post(mcp_server_url, json=payload.model_dump())
            response.raise_for_status()
            response_data = response.json()
            logger.debug(f"MCP Response Raw: {response_data}")

            # Parse response
            if response_data.get("status") == "success":
                mcp_response = MCPSuccessResponse(**response_data)
                logger.info(f"MCP operation '{operation_name}' successful (Req ID: {request_id}).")
                return mcp_response
            elif response_data.get("status") == "error":
                mcp_response = MCPErrorResponse(**response_data)
                logger.warning(f"MCP operation '{operation_name}' failed (Req ID: {request_id}): Code={mcp_response.error_code}, Msg='{mcp_response.message}'")
                return mcp_response
            else:
                logger.error(f"Invalid MCP response format received (Req ID: {request_id}): {response_data}")
                return MCPErrorResponse(
                    id=request_id, 
                    error_code=ErrorCode.UNKNOWN_ERROR, 
                    message="Invalid response format from MCP server."
                )

        except httpx.RequestError as e:
            logger.error(f"Network error calling MCP server at {mcp_server_url}: {e}", exc_info=True)
            return MCPErrorResponse(
                id=request_id, 
                error_code=ErrorCode.NETWORK_ERROR, 
                message=f"Network error connecting to MCP server: {e}"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"MCP server returned HTTP error {e.response.status_code}: {e.response.text}", exc_info=True)
            try:
                error_data = e.response.json()
                if error_data.get("status") == "error":
                    return MCPErrorResponse(**error_data)
            except Exception:
                pass  # Fallback to generic message
            return MCPErrorResponse(
                id=request_id, 
                error_code=ErrorCode.NETWORK_ERROR, 
                message=f"MCP server returned HTTP {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during MCP operation execution (Req ID: {request_id}): {e}", exc_info=True)
            return MCPErrorResponse(
                id=request_id, 
                error_code=ErrorCode.UNKNOWN_ERROR, 
                message=f"An unexpected error occurred: {e}"
            )
