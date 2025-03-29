import json
import logging
import re
import os # For urandom
from typing import List, Dict, Optional, Any, Tuple, Union
import httpx # Import httpx for MCP calls

# Use relative imports if running as part of the package
try:
    from ..Clients import BaseClient, Message, get_client
    from ..Prompts.main import generate_system_prompt
    # Import MCP models relative to the Core package's position
    from ..MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse # Added MCPRequest
    from ..MCP.errors import ErrorCode, MCPError # Added MCPError, MCPRequest
except (ImportError, ValueError): # Handle path/import issues during testing/direct run
    # Fallback for potential path issues
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Now try absolute imports
    from Clients import BaseClient, Message, get_client
    from Prompts.main import generate_system_prompt
    from MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode, MCPError

logger = logging.getLogger(__name__)

# --- Define MCP related constants ---
DEFAULT_MCP_TIMEOUT = 30.0
# --- End Constants ---


class AgentRunner:
    """
    Manages the autonomous execution steps for an AI agent, including interacting with LLMs
    and executing MCP operations. Designed for external loop control (e.g., by run.py).
    """
    def __init__(self,
                 client: BaseClient,
                 goal: str,
                 mcp_server_url: Optional[str] = None,
                 agent_id: Optional[str] = "autonomous-agent",
                 mcp_timeout: float = DEFAULT_MCP_TIMEOUT,
                 max_steps: int = 10):
        """
        Initializes the AgentRunner.

        Args:
            client: An initialized instance of a BaseClient subclass (e.g., AnthropicClient).
            goal: The initial high-level goal for the agent.
            mcp_server_url: The URL of the running MCP server (e.g., "http://localhost:8000/mcp").
                            Optional for test cases.
            agent_id: The ID to use when executing MCP operations (for permissions).
            mcp_timeout: Timeout in seconds for MCP requests.
            max_steps: The maximum number of iterations allowed (informational, loop controlled externally).
        """
        if not isinstance(client, BaseClient):
            raise TypeError("client must be an instance of BaseClient or its subclass.")

        self.client = client
        self.goal = goal
        self.agent_id = agent_id
        self.max_steps = max_steps # Store for reference
        self.history: List[Message] = []
        self.system_prompt: str = ""

        # --- MCP Configuration ---
        self.mcp_server_url = mcp_server_url
        self.mcp_timeout = mcp_timeout
        self.http_client: Optional[httpx.AsyncClient] = None # Initialize lazily or here
        # --- End MCP Configuration ---

        logger.info(f"Initializing AgentRunner for agent '{self.agent_id}' with goal: {self.goal}")
        self._prepare_initial_state()
        self._initialize_http_client() # Initialize the client for MCP calls

    def _initialize_http_client(self):
        """Initializes the httpx client for MCP communication."""
        if not self.http_client and self.mcp_server_url:
            self.http_client = httpx.AsyncClient(timeout=self.mcp_timeout)
            logger.info(f"Initialized shared HTTP client for MCP calls (Timeout: {self.mcp_timeout}s).")

    async def close(self):
        """Closes the underlying LLM client and the internal HTTP client."""
        closed_llm = False
        closed_http = False
        try:
            await self.client.close()
            closed_llm = True
        except Exception as e:
            logger.error(f"Error closing LLM client: {e}", exc_info=True)

        if self.http_client:
            try:
                await self.http_client.aclose()
                self.http_client = None
                closed_http = True
            except Exception as e:
                logger.error(f"Error closing internal HTTP client: {e}", exc_info=True)

        if closed_llm or closed_http:
             logger.info("AgentRunner closed associated resources.")


    def _prepare_initial_state(self):
        """Generates the system prompt and resets history."""
        # Generate system prompt including the goal and provider specifics
        try:
            self.system_prompt = generate_system_prompt(
                provider=self.client.config.name,
                goal=self.goal
            )
            # Add system prompt to history *if* the provider doesn't handle it separately
            # Anthropic expects it separate, OpenAI prefers it as first message.
            # Let's assume BaseClient subclasses handle where the system prompt goes.
            # If not, add logic here:
            # if self.client.config.name == "openai": # Example
            #     self.history = [Message(role="system", content=self.system_prompt)]
            # else:
            #     self.history = []
            self.history = [] # Keep history clean initially

            logger.debug("AgentRunner initial state prepared.")
            # Log the full system prompt for debugging if needed (can be long)
            # logger.debug(f"System Prompt:\n{self.system_prompt}")
        except Exception as e:
             logger.error(f"Failed to generate system prompt: {e}", exc_info=True)
             # Decide how to handle this - raise error? Use default prompt?
             self.system_prompt = f"Error generating prompt. Base Goal: {self.goal}"
             self.history = []


    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses the LLM response text to find a valid MCP operation JSON block.

        Args:
            response_text: The text response from the LLM.

        Returns:
            A dictionary representing the parsed JSON operation call (the outer structure
            containing 'mcp_operation' key), or None if not found or invalid.
            Expected format: {"mcp_operation": {"operation_name": "...", "arguments": {...}}}
        """
        # Regex to find ```json ... ``` blocks, non-greedy, handling whitespace and case.
        match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL | re.IGNORECASE)

        if not match:
            logger.debug("No valid JSON code block found in LLM response.")
            return None

        json_str = match.group(1).strip()
        logger.debug(f"Found potential JSON block: {json_str}")

        try:
            parsed_json = json.loads(json_str)

            # --- Validate Structure ---
            if not isinstance(parsed_json, dict) or "mcp_operation" not in parsed_json:
                logger.warning(f"JSON block found, but missing 'mcp_operation' key or is not a dictionary.")
                return None

            mcp_call = parsed_json["mcp_operation"]
            if not isinstance(mcp_call, dict):
                 logger.warning(f"Value of 'mcp_operation' key is not a dictionary: {type(mcp_call)}")
                 return None

            op_name = mcp_call.get("operation_name")
            op_args = mcp_call.get("arguments") # Get arguments, default to None if missing

            # Check operation_name: must be a non-empty string
            if not isinstance(op_name, str) or not op_name:
                logger.warning(f"JSON 'mcp_operation' block has missing or invalid 'operation_name': '{op_name}'")
                return None

            # Check arguments: must be a dictionary if present
            if op_args is not None and not isinstance(op_args, dict):
                 logger.warning(f"JSON 'mcp_operation' block has invalid 'arguments' (must be a dictionary or omitted): {type(op_args)}")
                 return None
            # --- End Validation ---

            logger.info(f"Parsed valid MCP operation call: {op_name}")
            # Ensure arguments key exists even if empty, matching MCPRequest model expectation
            if op_args is None:
                 parsed_json["mcp_operation"]["arguments"] = {}

            return parsed_json # Return the full outer structure

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON block: {e}\nBlock content: {json_str}", exc_info=False)
            return None
        except Exception as e: # Catch unexpected errors during validation
            logger.error(f"Unexpected error parsing or validating JSON block: {e}\nBlock content: {json_str}", exc_info=True)
            return None


    def _format_mcp_result(self, mcp_response: Union[MCPSuccessResponse, MCPErrorResponse]) -> Message:
        """
        Formats the result of an MCP operation into a Message object for conversation history.

        Args:
            mcp_response: The MCPSuccessResponse or MCPErrorResponse object.

        Returns:
            A Message object (role='system') representing the operation result.
        """
        req_id = getattr(mcp_response, 'id', 'unknown') # Get associated request ID

        if isinstance(mcp_response, MCPSuccessResponse):
            # Format success: Use JSON for complex data (dict/list)
            result_data = mcp_response.result
            try:
                if isinstance(result_data, (dict, list)):
                    result_str = f"```json\n{json.dumps(result_data, indent=2)}\n```"
                elif result_data is None:
                    result_str = "[No data returned]"
                else:
                    result_str = str(result_data) # Simple string conversion
            except Exception as format_err:
                logger.warning(f"Could not format successful MCP result data (Req ID: {req_id}): {format_err}")
                result_str = "[Could not format result data]"

            content = f"MCP Operation Successful (ID: {req_id}):\nResult:\n{result_str}"
            logger.info(f"Formatted success result for request ID: {req_id}")

        elif isinstance(mcp_response, MCPErrorResponse):
            # Format error: Include code, name (if possible), message, details
            try:
                error_code_enum = ErrorCode(mcp_response.error_code)
                error_code_name = error_code_enum.name
                error_code_str = f"{mcp_response.error_code} ({error_code_name})"
            except ValueError:
                # Code not found in Enum
                error_code_str = str(mcp_response.error_code)

            content = (f"MCP Operation Failed (ID: {req_id}):\n"
                       f"Error Code: {error_code_str}\n"
                       f"Message: {mcp_response.message}")

            if mcp_response.details:
                 try:
                     # Format details as JSON if possible, otherwise use string
                     if isinstance(mcp_response.details, (dict, list)):
                         details_str = f"```json\n{json.dumps(mcp_response.details, indent=2)}\n```"
                     else:
                         details_str = str(mcp_response.details)
                 except Exception as format_err:
                     logger.warning(f"Could not format MCP error details (Req ID: {req_id}): {format_err}")
                     details_str = str(mcp_response.details) # Fallback to plain string
                 content += f"\nDetails:\n{details_str}"
            logger.warning(f"Formatted error result for request ID: {req_id}, Code: {mcp_response.error_code}")
        else:
            # Handle unexpected input type
            content = f"MCP Operation returned unexpected result type: {type(mcp_response)}"
            logger.error(content)

        # Use 'system' role for observations/results from tools/environment
        return Message(role="system", content=content)


    async def execute_mcp_operation(self, operation_name: str, arguments: Dict[str, Any]) -> Union[MCPSuccessResponse, MCPErrorResponse]:
        """
        Executes an operation on the configured MCP server.

        Args:
            operation_name: The name of the operation to execute.
            arguments: A dictionary of arguments for the operation.

        Returns:
            An MCPSuccessResponse if the operation succeeded, or an MCPErrorResponse if it failed.
            Returns MCPErrorResponse for network errors or invalid responses.
        """
        if not self.http_client:
             logger.error("HTTP client not initialized. Cannot execute MCP operation.")
             # Attempt to initialize it now? Or just fail? Let's fail for clarity.
             # self._initialize_http_client() # Optionally initialize lazily
             # if not self.http_client: # Check again if lazy init failed
             return MCPErrorResponse(id="internal", error_code=ErrorCode.INVALID_OPERATION_STATE, message="HTTP client not available.")

        request_id = f"mcp-req-{os.urandom(4).hex()}" # Generate unique request ID
        payload = MCPRequest(
            id=request_id,
            operation=operation_name,
            arguments=arguments if arguments is not None else {}, # Ensure arguments dict exists
            agent_id=self.agent_id
        )

        logger.info(f"Executing MCP operation '{operation_name}' via {self.mcp_server_url} (Agent: {self.agent_id}, Req ID: {request_id})")
        logger.debug(f"MCP Request Payload: {payload.model_dump()}")

        try:
            # Send POST request to MCP server
            response = await self.http_client.post(self.mcp_server_url, json=payload.model_dump())
            # Raise exception for non-2xx HTTP status codes
            response.raise_for_status()
            response_data = response.json()
            logger.debug(f"MCP Response Raw JSON: {response_data}")

            # Parse response using Pydantic models
            if response_data.get("status") == "success":
                mcp_response = MCPSuccessResponse(**response_data)
                logger.info(f"MCP operation '{operation_name}' successful (Req ID: {request_id}).")
                return mcp_response
            elif response_data.get("status") == "error":
                mcp_response = MCPErrorResponse(**response_data)
                logger.warning(f"MCP operation '{operation_name}' failed (Req ID: {request_id}): Code={mcp_response.error_code}, Msg='{mcp_response.message}'")
                return mcp_response
            else:
                # Invalid format from server (but HTTP 2xx)
                logger.error(f"Invalid MCP response format received (Req ID: {request_id}): {response_data}")
                return MCPErrorResponse(
                    id=request_id,
                    error_code=ErrorCode.INVALID_RESPONSE, # Consider adding INVALID_RESPONSE code
                    message="Invalid response format received from MCP server."
                )

        except httpx.TimeoutException as e:
             logger.error(f"Timeout calling MCP server at {self.mcp_server_url}: {e}", exc_info=False)
             return MCPErrorResponse(id=request_id, error_code=ErrorCode.TIMEOUT, message=f"Timeout connecting to MCP server: {e}")
        except httpx.RequestError as e:
            # Includes network errors, connection refused, DNS errors etc.
            logger.error(f"Network error calling MCP server at {self.mcp_server_url}: {e}", exc_info=True)
            return MCPErrorResponse(
                id=request_id,
                error_code=ErrorCode.NETWORK_ERROR,
                message=f"Network error connecting to MCP server: {e}"
            )
        except httpx.HTTPStatusError as e:
            # Handle 4xx/5xx errors from the server
            logger.error(f"MCP server returned HTTP error {e.response.status_code}: {e.response.text}", exc_info=False)
            try:
                # Try to parse the error response body as MCPErrorResponse
                error_data = e.response.json()
                if error_data.get("status") == "error":
                    # Re-package as MCPErrorResponse if structure matches
                    return MCPErrorResponse(**error_data)
            except Exception:
                 # If body isn't valid JSON or doesn't match MCPErrorResponse, create generic one
                 pass
            # Fallback generic error
            return MCPErrorResponse(
                id=request_id,
                # Map HTTP status if possible, otherwise use NETWORK_ERROR or UNKNOWN_ERROR
                error_code=ErrorCode.NETWORK_ERROR, # Or map e.response.status_code
                message=f"MCP server returned HTTP {e.response.status_code}"
            )
        except json.JSONDecodeError as e:
             logger.error(f"Failed to decode JSON response from MCP server: {e}", exc_info=False)
             return MCPErrorResponse(id=request_id, error_code=ErrorCode.INVALID_RESPONSE, message="Invalid JSON received from MCP server.")
        except Exception as e:
            # Catch-all for other unexpected errors during MCP call
            logger.error(f"Unexpected error during MCP operation execution (Req ID: {request_id}): {e}", exc_info=True)
            return MCPErrorResponse(
                id=request_id,
                error_code=ErrorCode.UNKNOWN_ERROR,
                message=f"An unexpected error occurred during MCP communication: {e}"
            )
