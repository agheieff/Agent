import json
import logging
import re
import os # For urandom
from typing import List, Dict, Optional, Any, Tuple, Union, Literal
from dataclasses import dataclass, field
import httpx # Import httpx for MCP calls
import asyncio

# --- Updated Imports ---
# Use absolute imports, assuming project structure is consistent
try:
    from ..Clients import BaseClient, Message
    # Import prompt generation functions and registry (needed here now)
    from ..Prompts.main import generate_system_prompt, generate_operations_documentation
    from ..MCP.registry import operation_registry
    # Import MCP models and errors
    from ..MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
    from ..MCP.errors import ErrorCode, MCPError
except (ImportError, ValueError) as e:
    # Fallback for potential path issues during testing/direct run
    # (Keep this fallback logic, but errors should ideally be fixed via correct execution context)
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Now try absolute imports again
    from Clients import BaseClient, Message
    from Prompts.main import generate_system_prompt, generate_operations_documentation
    from MCP.registry import operation_registry
    from MCP.models import MCPRequest, MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode, MCPError
    # Add logger definition in except block if it relies on this structure
    if 'logger' not in locals():
        logger = logging.getLogger(__name__)
    # Keep warning if fallback is used
    logger.warning(f"AgentRunner using fallback imports due to: {e}")
# --- End Updated Imports ---

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_MCP_TIMEOUT = 30.0
# --- End Constants ---

# Define AgentRunResult (assuming it's not moved elsewhere)
@dataclass
class AgentRunResult:
    status: Literal["completed", "max_steps", "error", "interrupted"]
    steps_taken: int
    final_message: Optional[str] = None
    final_history: Optional[List[Message]] = None


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
            client: An initialized instance of a BaseClient subclass.
            goal: The initial high-level goal for the agent.
            mcp_server_url: The URL of the running MCP server.
            agent_id: The ID to use when executing MCP operations.
            mcp_timeout: Timeout in seconds for MCP requests.
            max_steps: The maximum number of iterations allowed.
        """
        if not isinstance(client, BaseClient):
            raise TypeError("client must be an instance of BaseClient or its subclass.")
        if not mcp_server_url:
            # Keep warning
            logger.warning("mcp_server_url is not provided. MCP operations will fail.")

        self.client = client
        self.goal = goal
        self.agent_id = agent_id
        self.max_steps = max_steps
        self.history: List[Message] = []
        self.system_prompt: str = "" # Generated by _prepare_initial_state

        # Fix HTTPS to HTTP for local development if needed
        if mcp_server_url and mcp_server_url.startswith("https://127.0.0.1"):
            mcp_server_url = mcp_server_url.replace("https://", "http://")
            logger.debug(f"Changed HTTPS to HTTP for local MCP connection: {mcp_server_url}")
        
        self.mcp_server_url = mcp_server_url
        self.mcp_timeout = mcp_timeout
        self.http_client: Optional[httpx.AsyncClient] = None

        # Changed from INFO to DEBUG
        logger.debug(f"Initializing AgentRunner for agent '{self.agent_id}' with goal: {self.goal}")
        # Ensure registry is populated *before* preparing initial state which uses it
        operation_registry.discover_operations() # Ensure discovery runs if not already done
        self._prepare_initial_state()
        self._initialize_http_client()

    def _initialize_http_client(self):
        """Initializes the httpx client for MCP communication if URL is set."""
        if not self.http_client and self.mcp_server_url:
            self.http_client = httpx.AsyncClient(timeout=self.mcp_timeout)
            # Changed from INFO to DEBUG
            logger.debug(f"Initialized shared HTTP client for MCP calls to {self.mcp_server_url} (Timeout: {self.mcp_timeout}s).")
        elif not self.mcp_server_url:
            # Keep warning
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
                # Keep error log
                logger.error(f"Error closing LLM client: {e}", exc_info=True)

        if self.http_client:
            try:
                await self.http_client.aclose()
                self.http_client = None
                closed_http = True
            except Exception as e:
                # Keep error log
                logger.error(f"Error closing internal HTTP client: {e}", exc_info=True)

        if closed_llm or closed_http:
            # Changed from INFO to DEBUG
            logger.debug("AgentRunner closed associated resources.")

    def _prepare_initial_state(self):
        """Generates the system prompt using discovered operations and resets history."""
        try:
            # 1. Get available operations from the registry
            # Ensure discovery happened in __init__ or handle case where registry is empty
            ops_dict = operation_registry.get_all()
            if not ops_dict:
                # Keep warning
                logger.warning("MCP Operation Registry is empty during system prompt generation.")

            # 2. Generate documentation string from operations
            ops_docs = generate_operations_documentation(ops_dict)

            # 3. Generate the full system prompt, passing in the docs
            self.system_prompt = generate_system_prompt(
                operations_doc=ops_docs, # Pass generated docs
                provider=self.client.config.name,
                goal=self.goal
            )
            # Add system prompt to history
            self.history = [Message(role="system", content=self.system_prompt)]
            # Keep DEBUG log
            logger.debug("AgentRunner initial state prepared with system prompt in history.")
            # Optionally log the full prompt (can be very long)
            # logger.debug(f"System Prompt:\n{self.system_prompt}")

        except Exception as e:
            # Keep error log
            logger.error(f"Failed to generate system prompt: {e}", exc_info=True)
            # Fallback prompt if generation fails
            self.system_prompt = f"Error generating prompt. Base Goal: {self.goal}. MCP Operations list might be missing."
            self.history = [Message(role="system", content=self.system_prompt)]

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses the LLM response text to find a valid MCP operation JSON block.
        """
        # Search for ```json ... ``` block, ignoring case for ```json
        match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL | re.IGNORECASE)
        if not match:
            logger.debug("No valid JSON code block found in LLM response.")
            return None

        json_str = match.group(1).strip()
        logger.debug(f"Found potential JSON block: {json_str}")

        try:
            parsed_json = json.loads(json_str)

            # Validate basic structure
            if not isinstance(parsed_json, dict) or "mcp_operation" not in parsed_json:
                # Keep warning
                logger.warning(f"JSON block found, but missing 'mcp_operation' key or is not a dictionary.")
                return None

            mcp_call = parsed_json["mcp_operation"]
            if not isinstance(mcp_call, dict):
                # Keep warning
                logger.warning(f"Value of 'mcp_operation' key is not a dictionary: {type(mcp_call)}")
                return None

            op_name = mcp_call.get("operation_name")
            op_args = mcp_call.get("arguments")

            if not isinstance(op_name, str) or not op_name:
                # Keep warning
                logger.warning(f"JSON 'mcp_operation' block has missing or invalid 'operation_name': '{op_name}'")
                return None

            if op_args is not None and not isinstance(op_args, dict):
                # Keep warning
                logger.warning(f"JSON 'mcp_operation' block has invalid 'arguments' (must be a dictionary or omitted): {type(op_args)}")
                return None

            # Changed from INFO to DEBUG
            logger.debug(f"Parsed valid MCP operation call: {op_name}")

            # Ensure 'arguments' is a dict if it was null/omitted
            if op_args is None:
                parsed_json["mcp_operation"]["arguments"] = {}

            return parsed_json

        except json.JSONDecodeError as e:
            # Keep error log
            logger.error(f"Failed to decode JSON block: {e}\nBlock content: {json_str}", exc_info=False)
            return None
        except Exception as e:
            # Keep error log
            logger.error(f"Unexpected error parsing or validating JSON block: {e}\nBlock content: {json_str}", exc_info=True)
            return None


    def _format_mcp_result(self, mcp_response: Union[MCPSuccessResponse, MCPErrorResponse]) -> Message:
        """
        Formats the result of an MCP operation into a Message object for conversation history.
        """
        req_id = getattr(mcp_response, 'id', 'unknown')

        if isinstance(mcp_response, MCPSuccessResponse):
            result_data = mcp_response.result
            try:
                if isinstance(result_data, (dict, list)):
                    result_str = f"```json\n{json.dumps(result_data, indent=2)}\n```"
                elif result_data is None:
                    result_str = "[No data returned]"
                else:
                    result_str = str(result_data)
            except Exception as format_err:
                # Keep warning
                logger.warning(f"Could not format successful MCP result data (Req ID: {req_id}): {format_err}")
                result_str = "[Could not format result data]"

            content = f"MCP Operation Successful (ID: {req_id}):\nResult:\n{result_str}"
            # Changed from INFO to DEBUG
            logger.debug(f"Formatted success result for request ID: {req_id}")

        elif isinstance(mcp_response, MCPErrorResponse):
            try:
                error_code_enum = ErrorCode(mcp_response.error_code)
                error_code_name = error_code_enum.name
                error_code_str = f"{mcp_response.error_code} ({error_code_name})"
            except ValueError:
                # Handle unknown error codes gracefully
                error_code_str = str(mcp_response.error_code)

            content = (f"MCP Operation Failed (ID: {req_id}):\n"
                       f"Error Code: {error_code_str}\n"
                       f"Message: {mcp_response.message}")
            if mcp_response.details:
                try:
                    if isinstance(mcp_response.details, (dict, list)):
                        details_str = f"```json\n{json.dumps(mcp_response.details, indent=2)}\n```"
                    else:
                        details_str = str(mcp_response.details)
                except Exception as format_err:
                    # Keep warning
                    logger.warning(f"Could not format MCP error details (Req ID: {req_id}): {format_err}")
                    details_str = str(mcp_response.details)
                content += f"\nDetails:\n{details_str}"
            # Keep warning for errors
            logger.warning(f"Formatted error result for request ID: {req_id}, Code: {mcp_response.error_code}")

        else:
            content = f"MCP Operation returned unexpected result type: {type(mcp_response)}"
            # Keep error log
            logger.error(content)

        # Always return a system message
        return Message(role="system", content=content)


    async def execute_mcp_operation(self, operation_name: str, arguments: Dict[str, Any]) -> Union[MCPSuccessResponse, MCPErrorResponse]:
        """
        Executes an operation on the configured MCP server.
        """
        if not self.http_client:
            # Keep error log
            logger.error("HTTP client not initialized. Cannot execute MCP operation.")
            # Try initializing again just in case URL was set late
            self._initialize_http_client()
            if not self.http_client:
                return MCPErrorResponse(id="internal", error_code=ErrorCode.INVALID_OPERATION_STATE, message="HTTP client not available or MCP URL not set.")

        request_id = f"mcp-req-{os.urandom(4).hex()}"
        payload = MCPRequest(id=request_id, operation=operation_name, arguments=arguments if arguments is not None else {}, agent_id=self.agent_id)

        # Changed from INFO to DEBUG
        logger.debug(f"Executing MCP operation '{operation_name}' via {self.mcp_server_url} (Agent: {self.agent_id}, Req ID: {request_id})")
        logger.debug(f"MCP Request Payload: {payload.model_dump()}")

        try:
            response = await self.http_client.post(self.mcp_server_url, json=payload.model_dump())
            response.raise_for_status() # Raise exception for 4xx/5xx responses

            response_data = response.json()
            logger.debug(f"MCP Response Raw JSON: {response_data}")

            if response_data.get("status") == "success":
                mcp_response = MCPSuccessResponse(**response_data)
                # Changed from INFO to DEBUG
                logger.debug(f"MCP operation '{operation_name}' successful (Req ID: {request_id}).")
                return mcp_response
            elif response_data.get("status") == "error":
                mcp_response = MCPErrorResponse(**response_data)
                # Keep warning for errors reported by MCP server
                logger.warning(f"MCP operation '{operation_name}' failed (Req ID: {request_id}): Code={mcp_response.error_code}, Msg='{mcp_response.message}'")
                return mcp_response
            else:
                # Keep error log for invalid response format
                logger.error(f"Invalid MCP response format received (Req ID: {request_id}): {response_data}")
                return MCPErrorResponse(id=request_id, error_code=ErrorCode.INVALID_RESPONSE, message="Invalid response format received from MCP server.")

        except httpx.TimeoutException as e:
            # Keep error log for timeouts
            logger.error(f"Timeout calling MCP server at {self.mcp_server_url}: {e}", exc_info=False)
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.TIMEOUT, message=f"Timeout connecting to MCP server: {e}")
        except httpx.RequestError as e:
            # Keep error log for network issues
            logger.error(f"Network error calling MCP server at {self.mcp_server_url}: {e}", exc_info=True)
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.NETWORK_ERROR, message=f"Network error connecting to MCP server: {e}")
        except httpx.HTTPStatusError as e:
            # Keep error log for HTTP errors from MCP server
            logger.error(f"MCP server returned HTTP error {e.response.status_code}: {e.response.text}", exc_info=False)
            # Try to parse error response from body if possible
            try:
                error_data = e.response.json()
                if error_data.get("status") == "error":
                    return MCPErrorResponse(**error_data)
            except Exception:
                pass # Ignore if body is not valid JSON or expected error format
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.NETWORK_ERROR, message=f"MCP server returned HTTP {e.response.status_code}")
        except json.JSONDecodeError as e:
            # Keep error log for JSON decoding issues
            logger.error(f"Failed to decode JSON response from MCP server: {e}", exc_info=False)
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.INVALID_RESPONSE, message="Invalid JSON received from MCP server.")
        except Exception as e:
            # Keep error log for any other unexpected error during MCP call
            logger.error(f"Unexpected error during MCP operation execution (Req ID: {request_id}): {e}", exc_info=True)
            return MCPErrorResponse(id=request_id, error_code=ErrorCode.UNKNOWN_ERROR, message=f"An unexpected error occurred during MCP communication: {e}")

    # --- Autonomous Execution Loop ---
    async def run_autonomous(self) -> AgentRunResult:
        """
        Runs the main autonomous loop for the agent.
        """
        # Changed from INFO to DEBUG
        logger.debug(f"Starting autonomous run for agent '{self.agent_id}'. Goal: {self.goal}")
        step_count = 0
        final_summary = None

        while step_count < self.max_steps:
            step_count += 1
            # Changed from INFO to DEBUG
            logger.debug(f"--- Step {step_count}/{self.max_steps} ---")

            messages_for_llm = self.history.copy()

            # Add initial user message if only system prompt exists
            if len(messages_for_llm) == 1 and messages_for_llm[0].role == "system":
                initial_user_message = f"My goal is: {self.goal}. Please devise a plan and proceed using the available MCP Operations."
                messages_for_llm.append(Message(role="user", content=initial_user_message))
                # Changed from INFO to DEBUG
                logger.debug("Added initial user goal message to history.")

            logger.debug(f"Messages for LLM Call {step_count}:\n{[{'role': m.role, 'content': str(m.content)[:200]+'...' if isinstance(m.content, str) else type(m.content)} for m in messages_for_llm]}") # Log truncated content

            try:
                # Changed print/info to DEBUG
                logger.debug("Agent thinking...")
                # Print to stdout for test visibility and user feedback
                print("Agent thinking...")
                # Call LLM
                llm_response_text = await self.client.chat_completion(messages=messages_for_llm)
                logger.debug(f"LLM Raw Response Text (Step {step_count}): <<<{llm_response_text}>>>")

                if not llm_response_text or not llm_response_text.strip():
                    # Keep warning
                    logger.warning("LLM returned an empty or whitespace-only response. Stopping.")
                    self.history.append(Message(role="system", content="LLM returned an empty response. Stopping."))
                    return AgentRunResult(status="error", steps_taken=step_count, final_message="LLM returned empty response.", final_history=self.history)

                # Add assistant response to history
                self.history.append(Message(role="assistant", content=llm_response_text))

            except Exception as e:
                # Keep error log
                logger.error(f"Error during LLM call in step {step_count}: {e}", exc_info=True)
                error_msg = f"System Error: Error calling LLM: {e}. Stopping run."
                self.history.append(Message(role="system", content=error_msg))
                return AgentRunResult(status="error", steps_taken=step_count, final_message=error_msg, final_history=self.history)

            # --- Parse and Handle Response ---
            mcp_call_data = self._parse_llm_response(llm_response_text)

            if mcp_call_data:
                # LLM wants to execute an operation
                operation_details = mcp_call_data.get("mcp_operation", {})
                op_name = operation_details.get("operation_name")
                op_args = operation_details.get("arguments", {}) # Default to {}

                if not op_name:
                    # Keep error log
                    logger.error("Parsed MCP call, but 'operation_name' is missing.")
                    result_msg_content = "System Error: Assistant tried to call an operation but did not specify 'operation_name'."
                    self.history.append(Message(role="system", content=result_msg_content))
                    continue # Proceed to next step, maybe LLM corrects itself

                # Keep INFO log for actual tool usage intent
                logger.info(f"Agent wants to execute MCP operation: {op_name}({op_args})")

                # --- Handle finish_goal explicitly ---
                if op_name == "finish_goal":
                    final_summary = op_args.get("summary", "[No summary provided]")
                    # Keep INFO log for goal completion signal
                    logger.info(f"Agent initiated 'finish_goal'. Summary: {final_summary}")
                    self.history.append(Message(role="system", content=f"Agent signaled goal completion. Summary: {final_summary}"))
                    return AgentRunResult(status="completed", steps_taken=step_count, final_message=final_summary, final_history=self.history)

                # --- Execute other MCP operations ---
                try:
                    if not self.mcp_server_url:
                        raise MCPError(ErrorCode.INVALID_OPERATION_STATE, "MCP Server URL is not configured, cannot execute operation.")

                    mcp_result = await self.execute_mcp_operation(operation_name=op_name, arguments=op_args)
                    result_msg = self._format_mcp_result(mcp_result)
                    self.history.append(result_msg) # Add formatted result (success or error) back to history

                    # Keep logging for MCP operation results (success debugged, errors warned)
                    if isinstance(mcp_result, MCPSuccessResponse):
                        logger.debug(f"MCP Operation '{op_name}' execution reported success by server.")
                    elif isinstance(mcp_result, MCPErrorResponse):
                        # Warning is already logged in _format_mcp_result and execute_mcp_operation
                        pass

                except MCPError as e: # Catch errors specifically from execute_mcp_operation if they bubble up (e.g., URL not set)
                     # Keep error log
                     logger.error(f"MCPError executing operation '{op_name}': {e}", exc_info=False)
                     error_content = f"System Error: Failed to execute MCP operation '{op_name}': {e.message}"
                     self.history.append(Message(role="system", content=error_content))
                except Exception as e:
                    # Keep error log for unexpected execution errors
                    logger.error(f"Unexpected error executing MCP operation '{op_name}' via AgentRunner: {e}", exc_info=True)
                    error_content = f"System Error: Failed to execute MCP operation '{op_name}': {e}"
                    self.history.append(Message(role="system", content=error_content))
                    # Consider stopping the run on unexpected execution errors?
                    # return AgentRunResult(status="error", steps_taken=step_count, final_message=error_content, final_history=self.history)

            else:
                # LLM response was text-based (no MCP operation detected)
                # Changed from INFO to DEBUG
                logger.debug("LLM response was text-based (no MCP operation detected).")
                # Check if the agent *thinks* it's finished without using the operation
                if "goal achieved" in llm_response_text.lower() or "objective complete" in llm_response_text.lower():
                    # Keep warning for potential prompt refinement needed
                    logger.warning("Agent indicated goal achieved via text, but did not use 'finish_goal' operation. Consider refining prompts.")
                    # Optionally, treat this as completion? For now, just warn and continue.
                    # final_summary = f"[Agent indicated completion via text]: {llm_response_text}"
                    # return AgentRunResult(status="completed", steps_taken=step_count, final_message=final_summary, final_history=self.history)


        # --- Loop finished ---
        # Keep warning for reaching max steps
        logger.warning(f"Reached maximum steps ({self.max_steps}). Stopping execution.")
        self.history.append(Message(role="system", content=f"System Notice: Reached maximum steps ({self.max_steps}). Stopping execution."))
        return AgentRunResult(status="max_steps", steps_taken=step_count, final_message="Reached maximum steps.", final_history=self.history)
