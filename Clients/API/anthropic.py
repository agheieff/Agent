import os
import logging
import uuid # For generating unique request IDs
from typing import Dict, List, Optional, Any, AsyncIterator, Union

import httpx # For making requests to MCP server
import anthropic

from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message
# Attempt to import MCP models, handle gracefully if not found/installed
try:
    from MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    # Define dummy classes if MCP is not available to avoid runtime errors on load
    # Although the methods using them won't work.
    class MCPRequest: pass
    class MCPSuccessResponse: pass
    class MCPErrorResponse: pass
    class ErrorCode:
        UNKNOWN_ERROR = 1
        NETWORK_ERROR = 105


logger = logging.getLogger(__name__)


ANTHROPIC_CONFIG = ProviderConfig(
    name="anthropic",
    api_base="https://api.anthropic.com",
    api_key_env="ANTHROPIC_API_KEY",
    # *** Reverted default_model and models dict back to user's original definition ***
    default_model="claude-3-7-sonnet",
    requires_import="anthropic",
    models={
        "claude-3-7-sonnet": ModelConfig(
            name="claude-3-7-sonnet-latest", # As originally defined by user
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
        "claude-3-5-sonnet": ModelConfig(
            name="claude-3-5-sonnet-latest", # As originally defined by user
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
    }
)

class AnthropicClient(BaseClient):
    def __init__(self,
                 config: ProviderConfig = None,
                 mcp_server_url: Optional[str] = None,
                 mcp_agent_id: Optional[str] = "anthropic-agent"): # Default agent ID
        """
        Initializes the AnthropicClient.

        Args:
            config: Provider configuration. Defaults to ANTHROPIC_CONFIG.
            mcp_server_url: The URL of the running MCP server (e.g., "http://localhost:8000/mcp").
                            Defaults to MCP_SERVER_URL environment variable or None.
            mcp_agent_id: The agent ID to use when making requests to the MCP server.
        """
        self.timeout = 60.0  # Increased timeout
        self.max_retries = 2 # Reduced default retries
        config = config or ANTHROPIC_CONFIG
        super().__init__(config) # This calls self._initialize() which sets up self.client and self.http_client

        # MCP Configuration
        self.mcp_server_url = mcp_server_url or os.getenv("MCP_SERVER_URL")
        self.mcp_agent_id = mcp_agent_id
        self.default_model = config.default_model # Ensure default model is set using the provided config

        if not MCP_AVAILABLE:
            logger.warning("MCP models package not found or failed to import. MCP features will be unavailable.")
        elif not self.mcp_server_url:
            logger.warning("MCP_SERVER_URL is not set. MCP features will be unavailable.")

        # Ensure http_client is initialized by the base class
        if not self.http_client:
             logger.warning("HTTP client was not initialized in BaseClient. MCP calls may fail.")
             # Optionally, initialize it here as a fallback, though it's better if BaseClient handles it.
             # self.http_client = httpx.AsyncClient(timeout=30.0)


    def _initialize_client(self):
        """Initializes the Anthropic SDK client."""
        # Ensure API key is available before creating client
        if not self.api_key:
            raise ValueError(f"API key not found in environment variable {self.config.api_key_env}")

        try:
            # Use the official Anthropic async client
            async_anthropic_client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
            logger.info("Anthropic AsyncClient initialized successfully.")
            return async_anthropic_client
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic AsyncClient: {e}", exc_info=True)
            raise RuntimeError(f"Anthropic client initialization failed: {str(e)}") from e


    def _format_messages(self, messages: List[Message]) -> (List[Dict[str, Any]], Optional[str]):
        """
        Formats a list of Message objects into the structure Anthropic API expects.
        Handles potential multi-part content (e.g., images) in the future if needed.
        Separates the system prompt.
        """
        formatted = []
        system_prompt = None
        for msg in messages:
            if msg.role == "system":
                if system_prompt is None:
                    system_prompt = msg.content
                else:
                    # Append to existing system prompt if multiple are found
                    system_prompt += "\n" + msg.content
                    logger.warning("Multiple system messages found. Concatenating them.")
            elif msg.role in ["user", "assistant"]:
                 # Basic handling: assumes content is just text
                 # Future enhancement: check content type (e.g., if it's a dict for image/text)
                 if isinstance(msg.content, str):
                     content_block = {"type": "text", "text": msg.content}
                 # Add more complex content handling here if needed (e.g., images)
                 # elif isinstance(msg.content, dict) and msg.content.get("type") == "image_url":
                 #     content_block = ...
                 else:
                      logger.warning(f"Unsupported message content type: {type(msg.content)}. Skipping.")
                      continue

                 # Check if the last message was the same role, if so, merge content
                 # Anthropic API requires alternating user/assistant roles
                 if formatted and formatted[-1]["role"] == msg.role:
                      last_content = formatted[-1]["content"]
                      if isinstance(last_content, list):
                           last_content.append(content_block)
                      else: # Should ideally not happen if always list, but handle defensively
                           formatted[-1]["content"] = [last_content, content_block]
                      logger.debug(f"Merging consecutive messages from role: {msg.role}")
                 else:
                     formatted.append({"role": msg.role, "content": [content_block]})
            else:
                logger.warning(f"Unsupported message role '{msg.role}'. Skipping message.")

        # Ensure the first message is from the 'user' role if system prompt is present
        if system_prompt and formatted and formatted[0]['role'] != 'user':
             logger.warning("First message after system prompt is not 'user'. This might cause API errors.")
             # Optionally: Insert a dummy user message, or raise an error? For now, just warn.

        return formatted, system_prompt

    async def _call_api(self, messages: List[Message], model: str, stream: bool = False, **kwargs) -> Union[anthropic.types.Message, AsyncIterator[anthropic.types.MessageStreamEvent]]:
        """Internal method to make the actual API call."""
        if not self.client:
            raise RuntimeError("Anthropic client is not initialized.")

        # *** Uses the model name key provided (e.g., "claude-3-7-sonnet") to find the config ***
        model_config = self._get_model_config(model)
        formatted_msgs, system = self._format_messages(messages)

        # Ensure required parameters are present
        params = {
            "messages": formatted_msgs,
            # *** Sends the name from ModelConfig (e.g., "claude-3-7-sonnet-latest") to the API ***
            # *** This name might be invalid for the actual Anthropic API ***
            "model": model_config.name,
            "max_tokens": kwargs.get('max_tokens', 1024), # Default max_tokens
            "temperature": kwargs.get('temperature', 0.7),
            "stream": stream,
        }
        if system is not None:
            params["system"] = system

        # Add any other valid kwargs passed in
        valid_anthropic_params = {"top_p", "top_k", "stop_sequences"}
        for key, value in kwargs.items():
            if key in valid_anthropic_params:
                params[key] = value

        logger.debug(f"Calling Anthropic API with params: {params}")

        try:
            if stream:
                # The stream=True call returns a context manager
                # We need to await it to get the async iterator
                response_stream = await self.client.messages.create(**params)
                return response_stream # Return the stream directly
            else:
                response = await self.client.messages.create(**params)
                return response
        except anthropic.APIConnectionError as e:
            logger.error(f"Anthropic API Connection Error: {e}", exc_info=True)
            raise ConnectionError(f"Connection error: {e}") from e
        except anthropic.RateLimitError as e:
             logger.error(f"Anthropic Rate Limit Error: {e}", exc_info=True)
             raise RuntimeError(f"API rate limit exceeded: {e.message}") from e
        except anthropic.APIStatusError as e:
            logger.error(f"Anthropic API Status Error: {e.status_code} - {e.message}", exc_info=True)
            # Check if the error is due to an invalid model name
            if "model" in e.message.lower() or e.status_code == 400: # Or check specific error details if available
                 logger.error(f"Potential invalid model name used: '{model_config.name}'. Please verify it matches a valid Anthropic API model identifier.")
            raise RuntimeError(f"API error: {e.status_code} - {e.message}") from e
        except anthropic.APIError as e: # Catch generic Anthropic errors
             logger.error(f"Anthropic API Error: {e}", exc_info=True)
             raise RuntimeError(f"Generic API error: {e.message}") from e
        except Exception as e:
            logger.error(f"Unexpected error during Anthropic API call: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error: {str(e)}") from e

    def _process_response(self, response: anthropic.types.Message) -> str:
        """Extracts the text content from a standard API response."""
        if not response.content:
            logger.warning("Received empty content list from Anthropic.")
            return ""
        # Assuming the first content block is the primary text response
        first_block = response.content[0]
        if hasattr(first_block, 'text'):
             return first_block.text
        else:
             logger.warning(f"First content block has no 'text' attribute: {first_block}")
             return ""


    async def chat_completion(self, messages: List[Message], model: str = None, **kwargs) -> str:
        """Gets a standard chat completion from Anthropic."""
        effective_model = model or self.default_model
        response = await self._call_api(messages=messages, model=effective_model, stream=False, **kwargs)
        # Type hint suggests response is Message, but check just in case
        if isinstance(response, anthropic.types.Message):
            return self._process_response(response)
        else:
            # This case should not happen if stream=False
            logger.error(f"Unexpected response type for non-streaming call: {type(response)}")
            raise RuntimeError("Internal error: Unexpected response type received from _call_api")


    async def stream_chat_completion(self, messages: List[Message], model: str = None, **kwargs) -> AsyncIterator[str]:
        """Streams chat completions from Anthropic, yielding text chunks."""
        effective_model = model or self.default_model
        stream = await self._call_api(messages=messages, model=effective_model, stream=True, **kwargs)

        try:
             # Iterate through the events in the stream
             async for event in stream:
                 # Check event type and yield relevant content
                 if event.type == "content_block_delta":
                     if event.delta.type == "text_delta":
                         yield event.delta.text
                 elif event.type == "message_start":
                     # Log model used, etc. if needed
                     logger.debug(f"Stream started for model: {event.message.model}")
                 elif event.type == "message_delta":
                     # Contains usage updates in delta.usage
                     # logger.debug(f"Usage update: {event.delta.usage}")
                     pass # Ignore for now, but could collect usage
                 elif event.type == "content_block_start":
                     # logger.debug(f"Content block started: Index {event.index}")
                     pass
                 elif event.type == "content_block_stop":
                      # logger.debug(f"Content block stopped: Index {event.index}")
                      pass
                 elif event.type == "message_stop":
                      # Final event, stream ends. Log final metrics.
                      logger.debug("Stream finished.")
                      # Access final metrics if needed: await stream.get_final_message()
                      break
                 # Handle other event types if necessary
                 # else:
                 #    logger.debug(f"Received stream event type: {event.type}")

        except anthropic.APIConnectionError as e:
            logger.error(f"Connection error during streaming: {e}", exc_info=True)
            raise ConnectionError(f"Connection error during streaming: {e}") from e
        except anthropic.APIStatusError as e:
            logger.error(f"API error during streaming: {e.status_code} - {e.message}", exc_info=True)
            # Check if the error is due to an invalid model name during streaming
            if "model" in e.message.lower() or e.status_code == 400:
                 logger.error(f"Potential invalid model name used in stream: Check config for model key '{effective_model}'. Please verify it maps to a valid Anthropic API model identifier.")
            raise RuntimeError(f"API error during streaming: {e.status_code} - {e.message}") from e
        except Exception as e:
            logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected streaming error: {str(e)}") from e
        finally:
             # Ensure the stream context manager is properly closed if applicable
             # (The async for loop usually handles this for async iterators)
             # If the stream object returned by _call_api needs explicit closing:
             if hasattr(stream, 'aclose'):
                 await stream.aclose()


    async def execute_mcp_operation(self, operation_name: str, arguments: Dict[str, Any]) -> Union[MCPSuccessResponse, MCPErrorResponse]:
        """
        Executes an operation on the configured MCP server.

        Args:
            operation_name: The name of the MCP operation to call.
            arguments: A dictionary of arguments for the operation.

        Returns:
            An MCPSuccessResponse if the operation succeeded, or an MCPErrorResponse if it failed.
            Returns an MCPErrorResponse with NETWORK_ERROR or UNKNOWN_ERROR for connection/parsing issues.
        """
        if not MCP_AVAILABLE:
            logger.error("MCP package not available. Cannot execute MCP operation.")
            return MCPErrorResponse(id="mcp-unavailable", error_code=ErrorCode.UNKNOWN_ERROR, message="MCP package not available.") # type: ignore
        if not self.mcp_server_url:
            logger.error("MCP_SERVER_URL not configured. Cannot execute MCP operation.")
            return MCPErrorResponse(id="mcp-unconfigured", error_code=ErrorCode.UNKNOWN_ERROR, message="MCP server URL not configured.") # type: ignore
        if not self.http_client:
            logger.error("HTTP client not available. Cannot execute MCP operation.")
            return MCPErrorResponse(id="http-client-unavailable", error_code=ErrorCode.UNKNOWN_ERROR, message="HTTP client not available.") # type: ignore

        request_id = f"mcp-req-{uuid.uuid4()}"
        payload = MCPRequest(
            id=request_id,
            operation=operation_name,
            arguments=arguments,
            agent_id=self.mcp_agent_id
        )

        logger.info(f"Executing MCP operation '{operation_name}' via {self.mcp_server_url} with Agent ID '{self.mcp_agent_id}' (Req ID: {request_id})")
        logger.debug(f"MCP Request Payload: {payload.dict()}") # Use .model_dump() for Pydantic v2+

        try:
            response = await self.http_client.post(self.mcp_server_url, json=payload.dict()) # Use .model_dump() for Pydantic v2+
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            response_data = response.json()
            logger.debug(f"MCP Response Raw: {response_data}")

            # Try parsing as success or error
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
                return MCPErrorResponse(id=request_id, error_code=ErrorCode.UNKNOWN_ERROR, message="Invalid response format from MCP server.") # type: ignore

        except httpx.ConnectError as e:
            logger.error(f"Connection error calling MCP server at {self.mcp_server_url}: {e}", exc_info=True)
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.NETWORK_ERROR, message=f"Could not connect to MCP server: {e}") # type: ignore
        except httpx.TimeoutException as e:
             logger.error(f"Timeout calling MCP server at {self.mcp_server_url}: {e}", exc_info=True)
             return MCPErrorResponse(id=request_id, error_code=ErrorCode.NETWORK_ERROR, message=f"Timeout connecting to MCP server: {e}") # type: ignore
        except httpx.HTTPStatusError as e:
            logger.error(f"MCP server returned HTTP error {e.response.status_code}: {e.response.text}", exc_info=True)
            # Try to parse error response from MCP body if possible
            try:
                error_data = e.response.json()
                if error_data.get("status") == "error":
                    return MCPErrorResponse(**error_data)
            except Exception:
                 pass # Ignore parsing errors, fall back to generic message
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.NETWORK_ERROR, message=f"MCP server returned HTTP {e.response.status_code}") # type: ignore
        except Exception as e:
            logger.error(f"Unexpected error during MCP operation execution (Req ID: {request_id}): {e}", exc_info=True)
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.UNKNOWN_ERROR, message=f"An unexpected error occurred: {e}") # type: ignore
