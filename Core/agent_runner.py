import json
import logging
import re
from typing import List, Dict, Optional, Any, Tuple

# Use relative imports if running as part of the package,
# or adjust sys.path if running standalone for testing.
try:
    from Clients import BaseClient, Message, get_client
    from Prompts.main import generate_system_prompt
    from MCP.models import MCPSuccessResponse, MCPErrorResponse # For type hinting
except ImportError:
    # Fallback for potential path issues during direct execution/testing
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from Clients import BaseClient, Message, get_client
    from Prompts.main import generate_system_prompt
    from MCP.models import MCPSuccessResponse, MCPErrorResponse


logger = logging.getLogger(__name__)

class AgentRunner:
    """
    Manages the autonomous execution loop for an AI agent using MCP operations.
    """
    def __init__(self,
                 client: BaseClient,
                 goal: str,
                 agent_id: Optional[str] = "autonomous-agent",
                 max_steps: int = 10):
        """
        Initializes the AgentRunner.

        Args:
            client: An initialized instance of a BaseClient subclass (e.g., AnthropicClient).
            goal: The initial high-level goal for the agent.
            agent_id: The ID to use when executing MCP operations (for permissions).
            max_steps: The maximum number of iterations (LLM calls + Tool Executions) allowed.
        """
        if not isinstance(client, BaseClient):
            raise TypeError("client must be an instance of BaseClient or its subclass.")

        self.client = client
        self.goal = goal
        self.agent_id = agent_id
        self.max_steps = max_steps
        self.history: List[Message] = []
        self.system_prompt: str = ""

        logger.info(f"Initializing AgentRunner for agent '{self.agent_id}' with goal: {self.goal}")
        self._prepare_initial_state()

    def _prepare_initial_state(self):
        """Generates the system prompt and sets up the initial history."""
        # Generate system prompt including the goal
        self.system_prompt = generate_system_prompt(
            provider=self.client.config.name, # Pass provider name for specific instructions
            goal=self.goal # Pass the specific goal
        )
        # Clear history and add system prompt (if client expects it this way)
        # Note: Anthropic prefers 'system' parameter, others might want it in messages.
        # BaseClient/AnthropicClient handles separation, so don't add system prompt to history here.
        self.history = []
        logger.debug("Initial state prepared.")
        # Log the full system prompt for debugging if needed
        # logger.debug(f"System Prompt:\n{self.system_prompt}")

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses the LLM response to find an MCP operation call JSON block.

        Args:
            response_text: The text response from the LLM.

        Returns:
            A dictionary representing the parsed JSON operation call, or None if not found.
            Expected format: {"mcp_operation": {"operation_name": "...", "arguments": {...}}}
        """
        # Use regex to find ```json ... ``` blocks
        # Make the regex non-greedy (.*?) and handle potential leading/trailing whitespace
        match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL | re.IGNORECASE)

        if not match:
            logger.debug("No JSON block found in LLM response.")
            return None

        json_str = match.group(1).strip()
        logger.debug(f"Found potential JSON block: {json_str}")

        try:
            parsed_json = json.loads(json_str)
            # Validate the expected structure
            if isinstance(parsed_json, dict) and "mcp_operation" in parsed_json:
                mcp_call = parsed_json["mcp_operation"]
                if isinstance(mcp_call, dict) and \
                   "operation_name" in mcp_call and \
                   isinstance(mcp_call.get("arguments"), dict): # Allow empty args dict
                    logger.info(f"Parsed MCP operation call: {mcp_call['operation_name']}")
                    return parsed_json # Return the full outer structure
                else:
                    logger.warning(f"JSON 'mcp_operation' block has incorrect inner structure: {mcp_call}")
            else:
                 logger.warning(f"JSON block found, but missing 'mcp_operation' key or incorrect type: {parsed_json}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON block: {e}\nBlock content: {json_str}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON block: {e}\nBlock content: {json_str}", exc_info=True)

        return None # Return None if parsing fails or structure is wrong

    def _format_mcp_result(self, result: Union[MCPSuccessResponse, MCPErrorResponse]) -> Message:
        """
        Formats the result of an MCP operation into a Message for the history.

        Args:
            result: The MCPSuccessResponse or MCPErrorResponse object.

        Returns:
            A Message object representing the operation result.
        """
        if isinstance(result, MCPSuccessResponse):
            content = f"MCP Operation Successful:\nResult:\n```json\n{json.dumps(result.result, indent=2)}\n```"
            logger.info(f"Formatted success result for request ID: {result.id}")
        elif isinstance(result, MCPErrorResponse):
            content = (f"MCP Operation Failed:\n"
                       f"Error Code: {result.error_code}\n"
                       f"Message: {result.message}\n")
            if result.details:
                 content += f"Details:\n```json\n{json.dumps(result.details, indent=2)}\n```"
            logger.warning(f"Formatted error result for request ID: {result.id}, Code: {result.error_code}")
        else:
            content = f"MCP Operation returned unexpected result type: {type(result)}"
            logger.error(content)

        # Use 'system' role to indicate an observation/result from the environment
        return Message(role="system", content=content)

    async def run_autonomous(self) -> List[Message]:
        """
        Runs the autonomous agent loop.

        Returns:
            The final conversation history.
        """
        logger.info(f"Starting autonomous run for agent '{self.agent_id}'...")

        for step in range(self.max_steps):
            logger.info(f"--- Step {step + 1}/{self.max_steps} ---")

            # 1. Prepare messages for LLM (Combine history)
            # The BaseClient/AnthropicClient handles system prompt separately
            messages_for_llm = self.history.copy()
            if not messages_for_llm:
                 # Add a dummy initial user message if history is empty,
                 # as some models require a user message to start.
                 # The goal is already in the system prompt.
                 messages_for_llm.append(Message(role="user", content="Proceed with the goal."))


            logger.debug(f"Messages for LLM (excluding system prompt):\n{messages_for_llm}")

            # 2. Call LLM
            try:
                # Use the client's system prompt capability
                llm_response_text = await self.client.chat_completion(
                    messages=messages_for_llm,
                    # System prompt is passed internally by AnthropicClient if set
                )
                logger.debug(f"LLM Raw Response: {llm_response_text}")
                if not llm_response_text:
                     logger.warning("LLM returned an empty response.")
                     # Decide how to handle: stop, retry, add error message?
                     self.history.append(Message(role="system", content="LLM returned an empty response. Stopping."))
                     break

                # Add LLM's response to history *before* potential operation execution
                self.history.append(Message(role="assistant", content=llm_response_text))

            except Exception as e:
                logger.error(f"Error during LLM call: {e}", exc_info=True)
                self.history.append(Message(role="system", content=f"Error calling LLM: {e}. Stopping."))
                break # Stop execution on LLM error

            # 3. Parse LLM response for MCP operation
            mcp_call_data = self._parse_llm_response(llm_response_text)

            if mcp_call_data:
                # 4. Execute MCP Operation
                operation_details = mcp_call_data.get("mcp_operation", {})
                op_name = operation_details.get("operation_name")
                op_args = operation_details.get("arguments", {})

                if not op_name:
                    logger.error("Parsed MCP call, but 'operation_name' is missing.")
                    result_msg = Message(role="system", content="Error: Assistant tried to call an operation but did not specify 'operation_name'.")
                    self.history.append(result_msg)
                    continue # Go to next step

                logger.info(f"Attempting to execute MCP operation '{op_name}' with args: {op_args}")
                try:
                    # Use the client's execute_mcp_operation method
                    mcp_result = await self.client.execute_mcp_operation(
                        operation_name=op_name,
                        arguments=op_args
                        # agent_id and mcp_server_url are handled by the client instance
                    )
                    # Format result and add to history
                    result_msg = self._format_mcp_result(mcp_result)
                    self.history.append(result_msg)

                    if isinstance(mcp_result, MCPErrorResponse):
                        logger.warning(f"MCP Operation '{op_name}' failed. Error added to history.")
                        # Continue the loop, letting the agent see the error

                except Exception as e:
                    logger.error(f"Error executing MCP operation '{op_name}': {e}", exc_info=True)
                    error_msg = self._format_mcp_result(MCPErrorResponse(
                        id="runner-exec-error", # Generate an appropriate ID or use one?
                        error_code=1, # UNKNOWN_ERROR
                        message=f"Failed to execute MCP operation: {e}"
                    ))
                    self.history.append(error_msg)
                    # Continue, let the agent see the execution failure

            else:
                # 5. No MCP operation found - potentially a final answer or clarification
                logger.info("LLM response did not contain a valid MCP operation call.")
                # Check if the response indicates goal completion
                # (This is a simple check, could be made more robust)
                if "goal achieved" in llm_response_text.lower() or \
                   "task complete" in llm_response_text.lower():
                    logger.info("Agent indicated goal achieved. Stopping.")
                    break
                # Otherwise, just continue the loop with the assistant's text response added

            # Optional: Add a small delay between steps if needed
            # await asyncio.sleep(1)

        # End of loop
        if step == self.max_steps - 1:
            logger.warning(f"Reached maximum steps ({self.max_steps}). Stopping.")
            self.history.append(Message(role="system", content=f"Reached maximum steps ({self.max_steps}). Stopping execution."))
        else:
             logger.info("Autonomous run finished.")

        # Clean up client resources
        await self.client.close()
        logger.info("Client resources closed.")

        return self.history
