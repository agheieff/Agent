import openai # Keep specific SDK import
import os
import logging
import json # Added for formatting tool call results
import asyncio # Import needed in base, good to have here too if used directly
from typing import Dict, List, Optional, Any, AsyncIterator, Union, Tuple, Type

# Use relative imports within the package
from ..base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message
# Removed: from ...MCP.Operations.base import ArgumentDefinition # <-- REMOVED

# --- Configuration (Keep as is per user request, with minor corrections) ---
# (DEEPSEEK_CONFIG remains the same as provided)
DEEPSEEK_CONFIG = ProviderConfig(
    name="deepseek",
    api_base="https://api.deepseek.com/v1",
    api_key_env="DEEPSEEK_API_KEY",
    default_model="deepseek-chat",
    requires_import="openai",
    models={
        "deepseek-chat": ModelConfig(
            name="deepseek-chat", # API model name
            context_length=128000, # Deepseek chat has large context
            pricing=PricingTier(input=0.14, output=0.28) # Per Million Tokens (example, verify)
        ),
        "deepseek-coder": ModelConfig(
            name="deepseek-coder", # API model name
            context_length=128000,
            pricing=PricingTier(input=0.14, output=0.28) # Per Million Tokens (example, verify)
        )
        # Note: deepseek-reasoner might be a specific capability, not a base model name.
        # Use 'deepseek-chat' or 'deepseek-coder' for the model parameter.
    },
    default_timeout=60.0,
    default_max_retries=2
)
# --- End Configuration ---

logger = logging.getLogger(__name__)

# --- Helper Function for Function Calling ---

# FIX 2: Removed List[ArgumentDefinition] type hint here
def _arguments_to_json_schema(arguments: List[Any]) -> Dict[str, Any]:
    """Converts a list of MCP ArgumentDefinitions to JSON Schema for OpenAI tools."""
    properties = {}
    required_args = []
    # Map MCP types to JSON Schema types
    type_mapping = {
        'string': 'string',
        'integer': 'integer',
        'boolean': 'boolean',
        'float': 'number',
        'object': 'object',
        'array': 'array',
        'filepath': 'string' # Treat filepath as string for JSON schema
    }

    for arg in arguments:
        # Access attributes using getattr for safety if type hint is removed
        arg_name = getattr(arg, 'name', None)
        arg_type = getattr(arg, 'type', 'string') # Default if missing
        arg_description = getattr(arg, 'description', '')
        arg_required = getattr(arg, 'required', False)

        if arg_name is None:
            logger.warning(f"Skipping argument definition missing 'name': {arg}")
            continue

        schema_type = type_mapping.get(arg_type, 'string') # Default to string if unknown
        prop_definition = {"type": schema_type, "description": arg_description}
        properties[arg_name] = prop_definition
        if arg_required:
            required_args.append(arg_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required_args
    }

# --- DeepSeekClient Class ---

class DeepSeekClient(BaseClient):
    def __init__(self, config: Optional[ProviderConfig] = None):
        """Initializes the DeepSeekClient."""
        effective_config = config or DEEPSEEK_CONFIG
        super().__init__(effective_config)
        # Flag to indicate if function calling should be attempted
        self._enable_function_calling = True # Assume enabled for now

    def _initialize_provider_client(self) -> openai.AsyncOpenAI:
        """(Sync) Initializes the OpenAI SDK client configured for DeepSeek."""
        # (Implementation remains the same as provided before)
        if not self.api_key:
            raise RuntimeError("API key unexpectedly missing during client initialization.")
        try:
            return openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.config.api_base,
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek client (via AsyncOpenAI): {e}", exc_info=True)
            raise

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Formats messages for the OpenAI compatible API."""
        # (Implementation remains the same as provided before)
        formatted = []
        for msg in messages:
            # Skip system prompt if handled separately (though OpenAI usually wants it first)
            # if msg.role == "system": continue # Optional: skip if handled via 'tools' or elsewhere

            if isinstance(msg.content, str):
                formatted.append({"role": msg.role, "content": msg.content})
            else:
                # Handle potential complex content (e.g., images) - currently log/convert
                logger.warning(f"Unsupported content type {type(msg.content)} in DeepSeek message, converting to string.")
                formatted.append({"role": msg.role, "content": str(msg.content)})
        if not formatted:
            logger.error("Cannot make OpenAI-compatible API call with empty formatted messages.")
            # Returning empty list instead of None to avoid downstream errors expecting list
            return []
        return formatted

    async def _execute_api_call(
        self,
        formatted_messages: List[Dict[str, Any]], # Expects list from _format_messages
        api_model_name: str,
        stream: bool,
        **kwargs
    ) -> Union[openai.types.chat.ChatCompletion, AsyncIterator[openai.types.chat.ChatCompletionChunk]]:
        """Makes the actual OpenAI SDK call for DeepSeek, potentially adding tools."""
        if self.client is None:
            raise RuntimeError("DeepSeek client (AsyncOpenAI) not initialized before API call.")

        # --- Tool/Function Calling Setup ---
        tools_param = []
        tool_choice_param = None # Let the model decide ("auto") by default
        if self._enable_function_calling:
            try:
                # Import dynamically inside method to avoid circular dependency at module level
                # And ensure registry is populated when called
                # ----- FIX 1: Use absolute import -----
                from MCP.registry import operation_registry # Use absolute import
                # --------------------------------------
                all_ops = operation_registry.get_all() # Ensure discovery ran
                if not all_ops:
                    logger.warning("MCP Operation Registry is empty. Cannot generate tools for DeepSeek.")
                else:
                    ops_for_tool_gen = []
                    for op_name, op_instance in all_ops.items():
                        # Exclude finish_goal from being presented as a callable tool
                        if op_name == "finish_goal":
                            continue
                        # Ensure op_instance has required attributes
                        op_desc = getattr(op_instance, 'description', f'Operation {op_name}')
                        # Ensure arguments attribute exists and is iterable
                        op_args_defs_raw = getattr(op_instance, 'arguments', [])
                        op_args_defs = list(op_args_defs_raw) if isinstance(op_args_defs_raw, (list, tuple)) else []

                        ops_for_tool_gen.append({
                            "name": op_name,
                            "description": op_desc,
                            "arguments": op_args_defs # Pass the actual list of arg definitions
                        })

                    # Generate JSON schema from collected definitions
                    if ops_for_tool_gen:
                        for op_data in ops_for_tool_gen:
                            tools_param.append({
                                "type": "function",
                                "function": {
                                    "name": op_data["name"],
                                    "description": op_data["description"],
                                    "parameters": _arguments_to_json_schema(op_data["arguments"]) # Call helper here
                                }
                            })
                        tool_choice_param = "auto"
                        logger.debug(f"Generated {len(tools_param)} tools for DeepSeek API call.")

            # ----- FIX 1: Catch potential ImportError here too -----
            except ImportError as e:
                logger.error(f"Could not import MCP Operation Registry (ImportError: {e}). Function calling disabled.")
                tools_param = [] # Ensure params are empty on failure
                tool_choice_param = None
            # ------------------------------------------------------
            except Exception as e:
                logger.error(f"Error generating tools for DeepSeek API: {e}", exc_info=True)
                tools_param = [] # Ensure params are empty on failure
                tool_choice_param = None
        # --- End Tool Setup ---

        params = {
            "messages": formatted_messages,
            "model": api_model_name,
            "stream": stream,
            **kwargs # Include max_tokens, temperature etc. from BaseClient caller
        }

        # Add tools if available
        if tools_param:
            params["tools"] = tools_param
        if tool_choice_param:
            params["tool_choice"] = tool_choice_param

        # Filter out unsupported parameters (remains the same)
        valid_extra_params = {"top_p", "frequency_penalty", "presence_penalty", "stop"}
        # Add tool parameters to the list of known valid keys
        valid_keys = set(params.keys()) | valid_extra_params | {"tools", "tool_choice"}
        final_params = {k: v for k, v in params.items() if k in valid_keys or k in ["messages", "model", "stream", "max_tokens", "temperature"]}

        # Log removed keys if any
        removed_keys = set(params.keys()) - set(final_params.keys())
        if removed_keys:
            logger.warning(f"Ignoring unsupported parameters for DeepSeek/OpenAI: {removed_keys}")


        logger.debug(f"Calling DeepSeek API with params: {final_params}")
        # Make the SDK call (let BaseClient handle exceptions)
        response = await self.client.chat.completions.create(**final_params) # Use filtered params

        # Log usage for non-streaming immediately (remains the same)
        if not stream and isinstance(response, openai.types.chat.ChatCompletion) and response.usage:
            logger.info(f"DeepSeek API Usage: Input={response.usage.prompt_tokens}, Output={response.usage.completion_tokens}, Total={response.usage.total_tokens}")
            if response.choices and response.choices[0].finish_reason == 'tool_calls':
                logger.info("DeepSeek API call finished with tool_calls.")

        return response

    def _process_response(self, response: openai.types.chat.ChatCompletion) -> str:
        """
        Extracts text content or formats the first tool call into MCP JSON
        from a non-streaming OpenAI-compatible response.
        """
        if not response.choices:
            logger.warning("Received no choices from DeepSeek/OpenAI.")
            return ""

        message = response.choices[0].message

        # --- Check for Tool Calls ---
        if message.tool_calls:
            first_tool_call = message.tool_calls[0]
            if first_tool_call.type == "function":
                function_call = first_tool_call.function
                op_name = function_call.name
                try:
                    # Arguments are a JSON string, need to parse them
                    op_args = json.loads(function_call.arguments or '{}')
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON arguments for tool call '{op_name}': {function_call.arguments}")
                    op_args = {} # Use empty dict on parse failure

                # Format as the MCP JSON structure expected by AgentRunner
                mcp_json_payload = {
                    "mcp_operation": {
                        "operation_name": op_name,
                        "arguments": op_args
                    }
                }
                # Wrap in ```json block
                mcp_json_string = f"```json\n{json.dumps(mcp_json_payload, indent=2)}\n```"
                logger.info(f"Processed tool call '{op_name}' into MCP JSON format.")
                return mcp_json_string
            else:
                logger.warning(f"Received unsupported tool call type: {first_tool_call.type}")
                # Fall through to process content if any

        # --- Process Regular Content ---
        if message.content:
            return message.content.strip()
        else:
            # If no tool call and no content, return empty
            # Log the finish reason if available and potentially informative
            finish_reason = response.choices[0].finish_reason
            logger.warning(f"Received choice but no message content or tool calls from DeepSeek/OpenAI. Finish reason: {finish_reason}")
            return ""


    def _process_stream_chunk(self, chunk: openai.types.chat.ChatCompletionChunk) -> Optional[str]:
        """
        Extracts text delta from an OpenAI-compatible stream chunk.
        NOTE: Streaming tool calls are NOT fully handled here yet. This primarily handles text deltas.
        """
        if chunk.choices:
            delta = chunk.choices[0].delta
            # --- Handle Text Delta ---
            if delta and delta.content:
                return delta.content

            # --- Basic Logging for Tool Call Chunks (Full reconstruction not implemented) ---
            if delta and delta.tool_calls:
                logger.debug(f"Received tool_call chunk delta: {delta.tool_calls}")
                # To fully support streaming tool calls, need to accumulate chunks here
                # and yield the formatted MCP JSON once a full call is received.
                # For Phase 1, relying on non-streaming tool calls via _process_response.

            # Log finish reason if present in the chunk delta
            finish_reason = chunk.choices[0].finish_reason
            if finish_reason:
                logger.debug(f"Stream chunk indicates finish_reason: {finish_reason}")
                if finish_reason == 'tool_calls':
                    logger.info("Stream finished with tool_calls.")


        return None # No text delta in this chunk or only tool call chunk part

    # --- SDK Error Handling (remains the same) ---
    def _get_sdk_exception_types(self) -> Tuple[Type[Exception], ...]:
        return (
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.APIStatusError,
            openai.APIError # Catch broader SDK errors too
        )

    def _extract_error_details(self, error: Exception) -> Tuple[Optional[int], str]:
        status_code = getattr(error, 'status_code', None)
        message = getattr(error, 'message', str(error)) # Default message

        if isinstance(error, openai.APIStatusError):
            try:
                # Access response attribute directly if available
                response = getattr(error, 'response', None)
                if response:
                    error_details = response.json()
                    message = error_details.get('error', {}).get('message', message)
                else: # Fallback if response attribute missing
                    body = getattr(error, 'body', None)
                    if isinstance(body, dict) and 'error' in body:
                        message = body.get('error',{}).get('message', message)

            except Exception: # Handle cases where response is not JSON or parsing fails
                # Try getting raw text, fallback to original message
                response = getattr(error, 'response', None)
                if response:
                    message = getattr(response, 'text', message) or message
                # Fallback to default message if all else fails

        return status_code, message

    # chat_completion and stream_chat_completion are inherited from BaseClient
    # The modifications in _execute_api_call and _process_response adapt them.
