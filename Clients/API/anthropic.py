import os
import logging
import uuid # For generating unique request IDs
from typing import Dict, List, Optional, Any, AsyncIterator, Union, Tuple # Added Tuple

import httpx # For making requests to MCP server
import anthropic

# Use relative imports for components within the same package
from ..base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

# Attempt to import MCP models, handle gracefully if not found/installed
try:
    # Use relative import for MCP components as well, assuming standard package structure
    from ...MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
    from ...MCP.errors import ErrorCode
    MCP_AVAILABLE = True
except ImportError:
    # Fallback for cases where structure might be different or MCP not installed
    try:
        from MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
        from MCP.errors import ErrorCode
        MCP_AVAILABLE = True
    except ImportError:
        MCP_AVAILABLE = False
        # Define dummy classes if MCP is not available to avoid runtime errors on load
        # Although the methods using them won't work.
        logger = logging.getLogger(__name__) # Need logger defined here if import fails early
        logger.warning("MCP models package not found or failed to import. MCP features will be unavailable.")
        class MCPRequest: pass
        class MCPSuccessResponse: pass
        class MCPErrorResponse: pass
        class ErrorCode:
            UNKNOWN_ERROR = 1
            NETWORK_ERROR = 105


logger = logging.getLogger(__name__) # Ensure logger is defined


# --- Configuration reverted to original definition as requested ---
ANTHROPIC_CONFIG = ProviderConfig(
    name="anthropic",
    api_base="https://api.anthropic.com",
    api_key_env="ANTHROPIC_API_KEY",
    # Using original default_model and models dict
    default_model="claude-3-7-sonnet", # Original default
    requires_import="anthropic",
    models={
        "claude-3-7-sonnet": ModelConfig(
            name="claude-3-7-sonnet-latest", # As originally defined by user - likely invalid API name
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
        "claude-3-5-sonnet": ModelConfig(
            name="claude-3-5-sonnet-latest", # As originally defined by user - likely invalid API name
            context_length=200000,
            pricing=PricingTier(input=3.00, output=15.00)
        ),
        # Note: These keys/names might need adjustment to match valid Anthropic API model IDs
        # e.g., "claude-3-5-sonnet-20240620"
    }
)
# --- End reverted configuration ---


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
        # User-specific settings first
        self.timeout = 60.0  # Increased timeout
        self.max_retries = 2 # Reduced default retries

        # Assign config, potentially overriding base class defaults
        config = config or ANTHROPIC_CONFIG

        # Pass MCP specific args to BaseClient
        super().__init__(config, mcp_server_url=mcp_server_url, mcp_agent_id=mcp_agent_id)

        # Ensure default model is set using the potentially overridden config
        self.default_model = config.default_model # This will now default to "claude-3-7-sonnet"

        if not MCP_AVAILABLE:
            logger.warning("MCP models package not found or failed to import. MCP features will be unavailable.")
        elif not self.mcp_server_url: # Check the value set by BaseClient
            logger.warning("MCP_SERVER_URL is not set. MCP features will be unavailable.")

        if not self.http_client:
             logger.error("HTTP client was not initialized in BaseClient. MCP calls will fail.")
             raise RuntimeError("HTTP Client failed to initialize in BaseClient")


    def _initialize_provider_client(self):
        """Initializes the Anthropic SDK client."""
        if not self.api_key:
             raise ValueError(f"API key not found (checked in AnthropicClient). Env var: {self.config.api_key_env}")

        try:
            async_anthropic_client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
            logger.info("Anthropic AsyncClient initialized successfully.")
            return async_anthropic_client
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic AsyncClient: {e}", exc_info=True)
            raise # Re-raise for BaseClient


    def _format_messages(self, messages: List[Message]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Formats a list of Message objects into the structure Anthropic API expects.
        Separates the system prompt. Handles potential multi-part content and merges consecutive roles.
        """
        formatted = []
        system_prompt = None

        non_system_messages = []
        for msg in messages:
            if msg.role == "system":
                if isinstance(msg.content, str): # Ensure system content is string
                    if system_prompt is None:
                        system_prompt = msg.content
                    else:
                        system_prompt += "\n" + msg.content
                        logger.warning("Multiple system messages found. Concatenating them.")
                else:
                    logger.warning(f"System message content is not a string: {type(msg.content)}. Skipping.")
            elif msg.role in ["user", "assistant"]:
                 non_system_messages.append(msg)
            else:
                logger.warning(f"Unsupported message role '{msg.role}'. Skipping message.")

        last_role = None
        for msg in non_system_messages:
             if isinstance(msg.content, str):
                 content_block = {"type": "text", "text": msg.content}
                 content_list = [content_block]
             # Example placeholder for handling image content if added later
             # elif isinstance(msg.content, list) and msg.content and msg.content[0].get("type") == "image":
             #     content_list = msg.content # Assume pre-formatted list
             else:
                 logger.warning(f"Unsupported message content type: {type(msg.content)}. Treating as empty string.")
                 content_list = [{"type": "text", "text": ""}] # Avoid skipping message entirely

             if formatted and formatted[-1]["role"] == msg.role:
                 if isinstance(formatted[-1]["content"], list):
                     formatted[-1]["content"].extend(content_list)
                     logger.debug(f"Merging consecutive '{msg.role}' message content.")
                 else:
                     logger.warning(f"Cannot merge content: Previous message content is not a list.")
                     formatted.append({"role": msg.role, "content": content_list})
             else:
                 formatted.append({"role": msg.role, "content": content_list})
             last_role = msg.role

        # Validation: Anthropic requires the first message to be 'user' if history is not empty
        if formatted and formatted[0]['role'] != 'user':
            logger.error("Anthropic API Error: First message must be from the 'user' role.")
            # Option: Raise an error to prevent API call
            raise ValueError("Conversation history for Anthropic must start with a 'user' message.")
            # Option: Log warning and proceed (API will likely reject)
            # logger.warning("First message is not 'user'. This will likely cause an API error.")

        return formatted, system_prompt


    async def _call_api(self, messages: List[Message], model: str, stream: bool = False, **kwargs) -> Union[anthropic.types.Message, AsyncIterator[anthropic.types.MessageStreamEvent]]:
        """Internal method to make the actual API call, handling system prompt."""
        if not self.client:
            raise RuntimeError("Anthropic client is not initialized.")

        # Use the config key (e.g., "claude-3-7-sonnet") to find the ModelConfig
        model_config = self._get_model_config(model)
        # Get the specific name to send to the API (e.g., "claude-3-7-sonnet-latest")
        api_model_name = model_config.name
        formatted_msgs, system_prompt = self._format_messages(messages)

        if not formatted_msgs and not system_prompt:
             raise ValueError("Cannot make API call with no messages and no system prompt.")
        elif not formatted_msgs:
             logger.warning("Making API call with only a system prompt. This might fail if a user message is required.")
             # Depending on Anthropic API specifics, might need to ensure at least one dummy user message


        params = {
            "messages": formatted_msgs,
            "model": api_model_name, # Use the name from ModelConfig
            "max_tokens": kwargs.get('max_tokens', 4096),
            "temperature": kwargs.get('temperature', 0.7),
            "stream": stream,
        }
        if system_prompt:
            params["system"] = system_prompt
            logger.debug(f"Using system prompt: '{system_prompt[:100]}...'")

        valid_anthropic_params = {"top_p", "top_k", "stop_sequences"}
        for key, value in kwargs.items():
            if key in valid_anthropic_params:
                params[key] = value

        logger.debug(f"Calling Anthropic API (model: {api_model_name}) with params (excluding messages/system): "
                     f"{{k: v for k, v in params.items() if k not in ['messages', 'system']}}")

        try:
            if stream:
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
            raise RuntimeError(f"Anthropic API rate limit exceeded: {getattr(e, 'message', str(e))}") from e
        except anthropic.APIStatusError as e:
            # Log the detailed error message from Anthropic if available
            error_body = getattr(e, 'body', None)
            error_message = getattr(e, 'message', str(e))
            if isinstance(error_body, dict): # Anthropic often returns JSON error details
                 error_message = error_body.get('error', {}).get('message', error_message)

            logger.error(f"Anthropic API Status Error: {e.status_code} - {error_message}", exc_info=False) # exc_info=False to avoid redundant traceback

            # Check specifically for model-related errors
            err_msg_lower = error_message.lower()
            if "model" in err_msg_lower or "not found" in err_msg_lower or e.status_code in [400, 404]:
                 logger.error(f"Potential invalid model name used: '{api_model_name}'. Verify this is a valid, available model ID for your Anthropic API key.")

            raise RuntimeError(f"Anthropic API error: {e.status_code} - {error_message}") from e # Chain the exception
        except anthropic.APIError as e:
             logger.error(f"Anthropic API Error: {e}", exc_info=True)
             raise RuntimeError(f"Generic Anthropic API error: {getattr(e, 'message', str(e))}") from e
        except Exception as e:
            logger.error(f"Unexpected error during Anthropic API call: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error during API call: {str(e)}") from e

    def _process_response(self, response: anthropic.types.Message) -> str:
        """Extracts the text content from a standard API response."""
        if not response.content:
            logger.warning("Received empty content list from Anthropic.")
            return ""

        full_text = ""
        for block in response.content:
             if block.type == "text":
                 full_text += block.text
             else:
                 logger.warning(f"Ignoring non-text content block of type: {block.type}")

        if not full_text and response.stop_reason:
             logger.warning(f"Received no text content, but got stop reason: {response.stop_reason}")

        return full_text.strip()


    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        """Gets a standard chat completion from Anthropic."""
        effective_model = model or self.default_model
        response = await self._call_api(messages=messages, model=effective_model, stream=False, **kwargs)

        if isinstance(response, anthropic.types.Message):
            return self._process_response(response)
        else:
            logger.error(f"Internal Error: Unexpected response type for non-streaming call: {type(response)}")
            raise RuntimeError("Internal error: Unexpected response type received from _call_api")


    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """Streams chat completions from Anthropic, yielding text chunks."""
        effective_model = model or self.default_model
        stream = None

        try:
            stream = await self._call_api(messages=messages, model=effective_model, stream=True, **kwargs)

            if not hasattr(stream, '__aiter__'):
                 logger.error(f"Internal Error: _call_api did not return an async iterator for streaming. Got: {type(stream)}")
                 raise RuntimeError("Internal error: Failed to obtain stream iterator.")

            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield event.delta.text
                elif event.type == "message_start":
                    logger.debug(f"Stream started for model: {event.message.model}")
                elif event.type == "message_stop":
                    logger.debug("Stream finished.")
                    # final_message = await stream.get_final_message() # Get final usage etc.
                    # logger.info(f"Stream Final Usage: Input={final_message.usage.input_tokens}, Output={final_message.usage.output_tokens}")
                    break
                # Ignore other event types for simplicity (e.g., message_delta, content_block_start/stop)

        except anthropic.APIConnectionError as e:
            logger.error(f"Connection error during streaming: {e}", exc_info=True)
            raise ConnectionError(f"Connection error during streaming: {e}") from e
        except anthropic.APIStatusError as e:
            error_body = getattr(e, 'body', None)
            error_message = getattr(e, 'message', str(e))
            if isinstance(error_body, dict):
                 error_message = error_body.get('error', {}).get('message', error_message)
            logger.error(f"API error during streaming: {e.status_code} - {error_message}", exc_info=False)
            err_msg_lower = error_message.lower()
            if "model" in err_msg_lower or e.status_code in [400, 404]:
                 api_model_name = self._get_model_config(effective_model).name
                 logger.error(f"Potential invalid model name used in stream: '{api_model_name}'. Check config key '{effective_model}'.")
            raise RuntimeError(f"API error during streaming: {e.status_code} - {error_message}") from e
        except Exception as e:
            logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected streaming error: {str(e)}") from e
        finally:
            if stream and hasattr(stream, 'aclose'):
                 try:
                      await stream.aclose()
                      logger.debug("Stream context closed.")
                 except Exception as close_err:
                      logger.error(f"Error closing Anthropic stream context: {close_err}", exc_info=True)

    # execute_mcp_operation is inherited from BaseClient
