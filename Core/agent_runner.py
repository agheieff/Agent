import json
import logging
import re
import os # For urandom
from typing import List, Dict, Optional, Any, Tuple, Union, Literal # Added Literal
from dataclasses import dataclass, field # Added dataclass, field
import httpx # Import httpx for MCP calls
import asyncio # Added for sleep

# Use relative imports if running as part of the package
try:
    from ..Clients import BaseClient, Message # Removed get_client, as runner receives an initialized client
    from ..Prompts.main import generate_system_prompt
    # Import MCP models relative to the Core package's position
    from ..MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse # Added MCPRequest
    from ..MCP.errors import ErrorCode, MCPError # Added MCPError
except (ImportError, ValueError): # Handle path/import issues during testing/direct run
    # Fallback for potential path issues
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Now try absolute imports
    from Clients import BaseClient, Message
    from Prompts.main import generate_system_prompt
    from MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode, MCPError

logger = logging.getLogger(__name__)

# --- Define MCP related constants ---
DEFAULT_MCP_TIMEOUT = 30.0
# --- End Constants ---

# Define a result type for run_autonomous
@dataclass
class AgentRunResult:
    status: Literal["completed", "max_steps", "error", "interrupted"]
    steps_taken: int
    final_message: Optional[str] = None
    final_history: Optional[List[Message]] = None # Optional: return history if needed


class AgentRunner:
    """
    Manages the autonomous execution steps for an AI agent, including interacting with LLMs
    and executing MCP operations. Contains the main autonomous loop.
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
                                Optional for test cases or if MCP is not needed.
            agent_id: The ID to use when executing MCP operations (for permissions).
            mcp_timeout: Timeout in seconds for MCP requests.
            max_steps: The maximum number of iterations allowed.
        """
        if not isinstance(client, BaseClient):
            raise TypeError("client must be an instance of BaseClient or its subclass.")
        if not mcp_server_url:
             logger.warning("mcp_server_url is not provided. MCP operations will fail.")
             # Consider raising error if MCP is essential, or just allow running without it.

        self.client = client
        self.goal = goal
        self.agent_id = agent_id
        self.max_steps = max_steps
        self.history: List[Message] = []
        self.system_prompt: str = ""

        # --- MCP Configuration ---
        self.mcp_server_url = mcp_server_url
        self.mcp_timeout = mcp_timeout
        self.http_client: Optional[httpx.AsyncClient] = None # Initialize lazily
        # --- End MCP Configuration ---

        logger.info(f"Initializing AgentRunner for agent '{self.agent_id}' with goal: {self.goal}")
        self._prepare_initial_state()
        self._initialize_http_client() # Initialize the client for MCP calls

    def _initialize_http_client(self):
        """Initializes the httpx client for MCP communication if URL is set."""
        if not self.http_client and self.mcp_server_url:
            self.http_client = httpx.AsyncClient(timeout=self.mcp_timeout)
            logger.info(f"Initialized shared HTTP client for MCP calls to {self.mcp_server_url} (Timeout: {self.mcp_timeout}s).")
        elif not self.mcp_server_url:
             logger.warning("Cannot initialize HTTP client: mcp_server_url not set.")


    async def close(self):
        """Closes the underlying LLM client and the internal HTTP client."""
        closed_llm = False
        closed_http = False
        if self.client:
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
        try:
            # Generate system prompt including the goal and provider specifics
            # Note: generate_system_prompt now relies on MCP registry being populated
            # Ensure MCP registry discovery happens before this if needed standalone.
            self.system_prompt = generate_system_prompt(
                provider=self.client.config.name,
                goal=self.goal
            )
            # Add system prompt to history - client._format_messages will handle it
            self.history = [Message(role="system", content=self.system_prompt)]
            logger.debug("AgentRunner initial state prepared with system prompt in history.")
            # Log the full system prompt for debugging if needed (can be long)
            # logger.debug(f"System Prompt:\n{self.system_prompt}")
        except Exception as e:
            logger.error(f"Failed to generate system prompt: {e}", exc_info=True)
            self.system_prompt = f"Error generating prompt. Base Goal: {self.goal}"
            # Start with minimal history if prompt generation fails
            self.history = [Message(role="system", content=self.system_prompt)]


    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses the LLM response text to find a valid MCP operation JSON block.
        (Implementation remains the same as provided before)
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
        (Implementation remains the same as provided before)
        """
        req_id = getattr(mcp_response, 'id', 'unknown') # Get associated request ID

        if isinstance(mcp_response, MCPSuccessResponse):
            # Format success: Use JSON for complex data (dict/list)
            result_data = mcp_response.result
            try:
                if isinstance(result_data, (dict, list)):
                    # Limit size of JSON representation in history? Maybe later.
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
        (Implementation remains the same as provided before)
        """
        if not self.http_client:
            logger.error("HTTP client not initialized. Cannot execute MCP operation.")
            # Attempt to initialize it now? Or just fail? Let's fail for clarity.
            self._initialize_http_client() # Try to init
            if not self.http_client: # Check again
                return MCPErrorResponse(id="internal", error_code=ErrorCode.INVALID_OPERATION_STATE, message="HTTP client not available or MCP URL not set.")

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
                    error_code=ErrorCode.INVALID_RESPONSE,
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

    # --- Autonomous Execution Loop ---
    async def run_autonomous(self) -> AgentRunResult:
        """
        Runs the main autonomous loop for the agent.
        The agent will attempt to achieve its goal by interacting with the LLM
        and executing MCP operations until the goal is finished, max steps are
        reached, or an unrecoverable error occurs.
        """
        logger.info(f"Starting autonomous run for agent '{self.agent_id}'. Goal: {self.goal}")
        step_count = 0
        final_summary = None

        while step_count < self.max_steps:
            step_count += 1
            logger.info(f"--- Step {step_count}/{self.max_steps} ---")

            # 1. Prepare messages for LLM
            # History already includes system prompt from _prepare_initial_state
            messages_for_llm = self.history.copy()
            if len(messages_for_llm) == 1 and messages_for_llm[0].role == "system":
                # If only the system prompt exists, add the initial user goal message
                initial_user_message = f"My goal is: {self.goal}. Please devise a plan and proceed using the available MCP Operations."
                messages_for_llm.append(Message(role="user", content=initial_user_message))
                logger.info("Added initial user goal message to history.")

            logger.debug(f"Messages for LLM Call {step_count}:\n{[{'role': m.role, 'content': m.content} for m in messages_for_llm]}") # Convert dataclass to dict manually

            # 2. Call LLM
            try:
                logger.info("Agent thinking...")
                # Use the configured client's chat_completion method
                llm_response_text = await self.client.chat_completion(
                    messages=messages_for_llm # Pass the prepared list
                    # Model is handled by the client's default or method override
                )
                logger.debug(f"LLM Raw Response Text: <<<{llm_response_text}>>>")

                if not llm_response_text or not llm_response_text.strip():
                    logger.warning("LLM returned an empty or whitespace-only response. Stopping.")
                    self.history.append(Message(role="system", content="LLM returned an empty response. Stopping."))
                    return AgentRunResult(status="error", steps_taken=step_count, final_message="LLM returned empty response.", final_history=self.history)

                # Add assistant response to history *before* parsing for MCP calls
                self.history.append(Message(role="assistant", content=llm_response_text))

            except Exception as e:
                logger.error(f"Error during LLM call in step {step_count}: {e}", exc_info=True)
                error_msg = f"System Error: Error calling LLM: {e}. Stopping run."
                self.history.append(Message(role="system", content=error_msg))
                return AgentRunResult(status="error", steps_taken=step_count, final_message=error_msg, final_history=self.history)

            # 3. Parse LLM response for MCP call
            # This expects the specific ```json ... ``` block format
            mcp_call_data = self._parse_llm_response(llm_response_text)

            if mcp_call_data:
                # 4. Handle MCP Operation
                operation_details = mcp_call_data.get("mcp_operation", {})
                op_name = operation_details.get("operation_name")
                op_args = operation_details.get("arguments", {})

                if not op_name:
                    logger.error("Parsed MCP call, but 'operation_name' is missing.")
                    result_msg_content = "System Error: Assistant tried to call an operation but did not specify 'operation_name'."
                    self.history.append(Message(role="system", content=result_msg_content))
                    # Continue to next loop iteration, agent might correct itself
                    continue

                logger.info(f"Agent wants to execute MCP operation: {op_name}({op_args})")

                # Check for finish_goal *before* executing
                if op_name == "finish_goal":
                    final_summary = op_args.get("summary", "[No summary provided]")
                    logger.info(f"Agent initiated 'finish_goal'. Summary: {final_summary}")
                    self.history.append(Message(role="system", content=f"Agent signaled goal completion. Summary: {final_summary}"))
                    return AgentRunResult(status="completed", steps_taken=step_count, final_message=final_summary, final_history=self.history)

                # Execute the operation via MCP
                try:
                    if not self.mcp_server_url:
                         raise MCPError(ErrorCode.INVALID_OPERATION_STATE, "MCP Server URL is not configured, cannot execute operation.")

                    mcp_result = await self.execute_mcp_operation(
                        operation_name=op_name,
                        arguments=op_args
                    )
                    result_msg = self._format_mcp_result(mcp_result)
                    self.history.append(result_msg) # Add MCP result to history

                    if isinstance(mcp_result, MCPSuccessResponse):
                        logger.info(f"MCP Operation '{op_name}' successful.")
                    elif isinstance(mcp_result, MCPErrorResponse):
                        logger.warning(f"MCP Operation '{op_name}' failed: {mcp_result.error_code} - {mcp_result.message}")
                        # Agent will see the error message in history and decide next action

                except Exception as e:
                    logger.error(f"Error executing MCP operation '{op_name}' via AgentRunner: {e}", exc_info=True)
                    error_content = f"System Error: Failed to execute MCP operation '{op_name}': {e}"
                    self.history.append(Message(role="system", content=error_content))
                    # Let the agent decide how to proceed after seeing the system error
                    # Depending on the error, we might want to stop here instead.
                    # For now, continue loop to see if agent can recover.

            else:
                # 5. No MCP operation found - Treat as plain text response
                logger.info("LLM response was text-based (no MCP operation detected).")
                # The text response is already added to history.
                # In a purely autonomous loop, we don't prompt the user here.
                # The agent must decide the next step based on the history in the next loop iteration.
                # We could add logic here to check if the agent seems "stuck" or repeating itself.
                # If the agent explicitly asks a question, the loop continues, but no answer is provided.
                # Check if agent *thinks* it's finished without calling the tool
                if "goal achieved" in llm_response_text.lower() or "objective complete" in llm_response_text.lower():
                     logger.warning("Agent indicated goal achieved via text, but did not use 'finish_goal' operation. Consider refining prompts.")
                     # Optionally, treat this as completion? Or let it continue until max steps?
                     # Let's let it continue for now.

            # Optional: Add a small delay between steps if needed
            # await asyncio.sleep(0.1)

        # --- End of while loop ---
        logger.warning(f"Reached maximum steps ({self.max_steps}). Stopping execution.")
        self.history.append(Message(role="system", content=f"System Notice: Reached maximum steps ({self.max_steps}). Stopping execution."))
        return AgentRunResult(status="max_steps", steps_taken=step_count, final_message="Reached maximum steps.", final_history=self.history)
