import json
import logging
import re
from typing import List, Dict, Optional, Any, Tuple, Union # Added Union

# Use relative imports if running as part of the package,
# or adjust sys.path if running standalone for testing.
try:
    # Relative imports within the package structure
    from ..Clients import BaseClient, Message, get_client
    from ..Prompts.main import generate_system_prompt
    # Import MCP models relative to the Core package's position
    from ..MCP.models import MCPSuccessResponse, MCPErrorResponse
    from ..MCP.errors import ErrorCode
except (ImportError, ValueError): # ValueError handles cases like "attempted relative import beyond top-level package"
    # Fallback for potential path issues during direct execution/testing
    # This assumes the script is run from the project root or Core directory
    import sys
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Now try absolute imports
    from Clients import BaseClient, Message, get_client
    from Prompts.main import generate_system_prompt
    from MCP.models import MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode

logger = logging.getLogger(__name__)

class AgentRunner:
    """
    Manages the autonomous execution loop for an AI agent using MCP operations.
    This version is designed to be used by a controlling script (like run.py)
    rather than running the full loop itself. It provides methods for preparing
    state and handling individual steps, allowing the caller to manage I/O.
    """
    def __init__(self,
                 client: BaseClient,
                 goal: str,
                 agent_id: Optional[str] = "autonomous-agent",
                 max_steps: int = 10): # max_steps is informational here, loop control is external
        """
        Initializes the AgentRunner.

        Args:
            client: An initialized instance of a BaseClient subclass (e.g., AnthropicClient).
            goal: The initial high-level goal for the agent.
            agent_id: The ID to use when executing MCP operations (for permissions).
            max_steps: The maximum number of iterations allowed (informational).
        """
        if not isinstance(client, BaseClient):
            raise TypeError("client must be an instance of BaseClient or its subclass.")

        self.client = client
        self.goal = goal
        self.agent_id = agent_id
        self.max_steps = max_steps # Store for reference
        self.history: List[Message] = []
        self.system_prompt: str = "" # Store the generated system prompt

        logger.info(f"Initializing AgentRunner for agent '{self.agent_id}' with goal: {self.goal}")
        self._prepare_initial_state()

    def _prepare_initial_state(self):
        """Generates the system prompt."""
        # Generate system prompt including the goal and provider specifics
        self.system_prompt = generate_system_prompt(
            provider=self.client.config.name,
            goal=self.goal
        )
        # Ensure history is clean at start
        self.history = []
        logger.debug("AgentRunner initial state prepared.")
        # Log the full system prompt for debugging if needed (can be long)
        # logger.debug(f"System Prompt:\n{self.system_prompt}")

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses the LLM response to find an MCP operation call JSON block.
        (Visibility changed to public for use by run.py, though underscore suggests internal use)

        Args:
            response_text: The text response from the LLM.

        Returns:
            A dictionary representing the parsed JSON operation call, or None if not found.
            Expected format: {"mcp_operation": {"operation_name": "...", "arguments": {...}}}
        """
        # Use regex to find ```json ... ``` blocks
        # Make the regex non-greedy (.*?) and handle potential leading/trailing whitespace
        # Added re.IGNORECASE for flexibility
        match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL | re.IGNORECASE)

        if not match:
            logger.debug("No JSON block found in LLM response.")
            return None

        json_str = match.group(1).strip()
        logger.debug(f"Found potential JSON block: {json_str}")

        try:
            parsed_json = json.loads(json_str)
            # Validate the expected structure more robustly
            if isinstance(parsed_json, dict) and "mcp_operation" in parsed_json:
                mcp_call = parsed_json["mcp_operation"]
                # Check inner structure: must be dict, have 'operation_name', and 'arguments' (even if empty)
                if isinstance(mcp_call, dict) and \
                   "operation_name" in mcp_call and \
                   isinstance(mcp_call.get("arguments"), dict): # Ensure arguments is a dict
                    op_name = mcp_call["operation_name"]
                    if isinstance(op_name, str) and op_name: # Operation name must be non-empty string
                         logger.info(f"Parsed MCP operation call: {op_name}")
                         return parsed_json # Return the full outer structure for the caller
                    else:
                         logger.warning(f"JSON 'mcp_operation' block has invalid 'operation_name': {op_name}")
                else:
                    logger.warning(f"JSON 'mcp_operation' block has incorrect inner structure: {mcp_call}")
            else:
                logger.warning(f"JSON block found, but missing 'mcp_operation' key or incorrect type: {parsed_json}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON block: {e}\nBlock content: {json_str}", exc_info=False) # exc_info=False for cleaner logs here
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON block: {e}\nBlock content: {json_str}", exc_info=True)

        return None # Return None if parsing fails or structure is wrong

    def _format_mcp_result(self, mcp_response: Union[MCPSuccessResponse, MCPErrorResponse]) -> Message:
        """
        Formats the result of an MCP operation (MCPSuccessResponse or MCPErrorResponse)
        into a Message object suitable for adding to the conversation history.
        (Visibility changed to public for use by run.py)

        Args:
            mcp_response: The MCPSuccessResponse or MCPErrorResponse object from client.execute_mcp_operation.

        Returns:
            A Message object representing the operation result.
        """
        req_id = getattr(mcp_response, 'id', 'unknown') # Get request ID if available

        if isinstance(mcp_response, MCPSuccessResponse):
            # Format success result, include JSON if result is complex
            result_data = mcp_response.result
            try:
                # Nicely format complex results (dict/list) as JSON
                if isinstance(result_data, (dict, list)):
                     result_str = f"```json\n{json.dumps(result_data, indent=2)}\n```"
                elif result_data is None:
                     result_str = "[No data returned]"
                else:
                     result_str = str(result_data) # Simple string conversion otherwise
            except Exception:
                 result_str = "[Could not format result data]" # Fallback

            content = f"MCP Operation Successful (ID: {req_id}):\nResult:\n{result_str}"
            logger.info(f"Formatted success result for request ID: {req_id}")

        elif isinstance(mcp_response, MCPErrorResponse):
            # Format error result
            try:
                # Try to get enum name if it exists
                error_code_name = ErrorCode(mcp_response.error_code).name
                content = (f"MCP Operation Failed (ID: {req_id}):\n"
                           f"Error Code: {mcp_response.error_code} ({error_code_name})\n"
                           f"Message: {mcp_response.message}\n")
            except ValueError:
                # If error code is not in enum, just show the code value
                content = (f"MCP Operation Failed (ID: {req_id}):\n"
                           f"Error Code: {mcp_response.error_code}\n"
                           f"Message: {mcp_response.message}\n")
            if mcp_response.details:
                try:
                    # Format details as JSON if possible
                    # Only use JSON formatting for dict/list types
                    if isinstance(mcp_response.details, (dict, list)):
                        details_str = f"```json\n{json.dumps(mcp_response.details, indent=2)}\n```"
                    else:
                        # For other types, just convert to string
                        details_str = str(mcp_response.details)
                except Exception:
                     details_str = str(mcp_response.details)
                content += f"Details:\n{details_str}"
            logger.warning(f"Formatted error result for request ID: {req_id}, Code: {mcp_response.error_code}")
        else:
            # Handle unexpected input type
            content = f"MCP Operation returned unexpected result type: {type(mcp_response)}"
            logger.error(content)

        # Use 'system' role to indicate an observation/result from the environment/tools
        return Message(role="system", content=content)

    # --- REMOVED run_autonomous Method ---
    # The loop control logic is now moved to the calling script (run.py)
    # to allow for interactive user input.

    async def close(self):
         """Closes the underlying client resources."""
         await self.client.close()
         logger.info("AgentRunner closed client resources.")
