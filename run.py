#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import argparse
from dotenv import load_dotenv

# --- Setup Project Path ---
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
# --- End Setup ---

# --- Configure Logging ---
# Load .env early to potentially get LOG_LEVEL
load_dotenv()
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level_str,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Reduce verbosity of HTTPX logs
logger = logging.getLogger(__name__)
# --- End Logging Config ---

# --- Import Core Components (after path setup and logging) ---
try:
    from Clients import get_client, Message
    from Core import AgentRunner
    from MCP.models import MCPSuccessResponse, MCPErrorResponse # For type checking result format
except ImportError as e:
    logger.error(f"Failed to import necessary modules. Ensure PYTHONPATH is set correctly "
                 f"or run from project root. Error: {e}", exc_info=True)
    sys.exit(1)
# --- End Imports ---


async def main(goal: str, provider: str, agent_id: str, max_steps: int, model: Optional[str] = None):
    """Sets up and runs the autonomous agent loop."""

    # --- Configuration ---
    mcp_url = os.getenv("MCP_SERVER_URL") # Get from environment

    # --- Sanity Checks ---
    if not mcp_url:
        logger.error("MCP_SERVER_URL environment variable is not set. Cannot connect to MCP.")
        logger.error("Please set MCP_SERVER_URL in your .env file or environment (e.g., export MCP_SERVER_URL='http://localhost:8000/mcp')")
        sys.exit(1)
    logger.info(f"Connecting to MCP server at: {mcp_url}")

    # --- Initialize Client ---
    logger.info(f"Initializing client for provider: {provider}")
    client = get_client(provider, mcp_server_url=mcp_url, mcp_agent_id=agent_id)

    if not client:
        logger.error(f"Failed to initialize client for provider '{provider}'. Check API keys (e.g., ANTHROPIC_API_KEY) and dependencies.")
        sys.exit(1)

    # Optional: Set specific model if provided
    if model:
        try:
            client.get_model_config(model) # Validate model exists in config
            client.default_model = model
            logger.info(f"Using model: {model}")
        except ValueError as e:
            logger.error(f"Invalid model name '{model}' for provider '{provider}': {e}")
            await client.close() # Clean up initialized client
            sys.exit(1)
    else:
        logger.info(f"Using default model for {provider}: {client.default_model}")


    # --- Initialize AgentRunner ---
    agent_runner = AgentRunner(
        client=client,
        goal=goal,
        agent_id=agent_id,
        max_steps=max_steps # AgentRunner itself handles max_steps limit
    )

    # --- Run the Agent Loop ---
    print("\n" + "="*20 + " Starting Autonomous Agent Run " + "="*20)
    print(f"Goal: {goal}")
    print(f"Agent ID: {agent_id}")
    print(f"Provider: {provider} (Model: {client.default_model})")
    print(f"Max Steps: {max_steps}")
    print("="*60)

    step_count = 0
    try:
        while step_count < max_steps:
            step_count += 1
            print(f"\n--- Step {step_count}/{max_steps} ---")

            # 1. Prepare messages for LLM
            messages_for_llm = agent_runner.history.copy()
            if not messages_for_llm:
                messages_for_llm.append(Message(role="user", content="Proceed with the initial goal."))
            logger.debug(f"Messages for LLM (excluding system prompt):\n{messages_for_llm}")


            # 2. Call LLM
            try:
                print("🤖 Agent thinking...")
                # Use client's chat_completion which handles system prompt internally
                llm_response_text = await client.chat_completion(
                    messages=messages_for_llm
                    # **kwargs for temperature, max_tokens etc. could be added here
                )
                logger.debug(f"LLM Raw Response: {llm_response_text}")

                if not llm_response_text:
                    logger.warning("LLM returned an empty response. Stopping.")
                    agent_runner.history.append(Message(role="system", content="LLM returned an empty response. Stopping."))
                    break

                # Add LLM response to history *before* potential operation execution
                agent_runner.history.append(Message(role="assistant", content=llm_response_text))

            except Exception as e:
                logger.error(f"Error during LLM call: {e}", exc_info=True)
                error_msg = f"Error calling LLM: {e}. Stopping."
                agent_runner.history.append(Message(role="system", content=error_msg))
                print(f"SYSTEM: {error_msg}")
                break # Stop execution on LLM error

            # 3. Parse LLM response for MCP operation
            mcp_call_data = agent_runner._parse_llm_response(llm_response_text) # Use AgentRunner's parser

            if mcp_call_data:
                # 4. Execute MCP Operation
                operation_details = mcp_call_data.get("mcp_operation", {})
                op_name = operation_details.get("operation_name")
                op_args = operation_details.get("arguments", {})

                if not op_name:
                    logger.error("Parsed MCP call, but 'operation_name' is missing.")
                    result_msg = Message(role="system", content="Error: Assistant tried to call an operation but did not specify 'operation_name'.")
                    agent_runner.history.append(result_msg)
                    print(f"SYSTEM: {result_msg.content}")
                    continue # Go to next step

                # Check for the 'finish_goal' operation
                if op_name == "finish_goal":
                    print(f"🏁 Agent initiated 'finish_goal'.")
                    summary = op_args.get("summary", "No summary provided.")
                    print(f"🏁 Final Summary from Agent: {summary}")
                    agent_runner.history.append(Message(role="system", content=f"Agent finished goal. Summary: {summary}"))
                    logger.info("Agent called finish_goal. Stopping loop.")
                    break # Exit the loop

                # Execute other operations
                print(f"🛠️ Agent wants to execute: {op_name}({op_args})")
                logger.info(f"Attempting to execute MCP operation '{op_name}' with args: {op_args}")
                try:
                    # Use the client's execute_mcp_operation method
                    mcp_result = await client.execute_mcp_operation(
                        operation_name=op_name,
                        arguments=op_args
                        # agent_id and mcp_server_url are handled by the client instance
                    )

                    # Format result and add to history
                    result_msg = agent_runner._format_mcp_result(mcp_result) # Use AgentRunner's formatter
                    agent_runner.history.append(result_msg)

                    # Print result for user
                    print(f"SYSTEM: MCP Operation Result ({op_name}):")
                    if isinstance(mcp_result, MCPSuccessResponse):
                        print(f"  Status: Success")
                        print(f"  Result Data: {mcp_result.result}")
                        logger.info(f"MCP Operation '{op_name}' successful.")
                    elif isinstance(mcp_result, MCPErrorResponse):
                        print(f"  Status: Error")
                        print(f"  Error Code: {mcp_result.error_code}")
                        print(f"  Message: {mcp_result.message}")
                        logger.warning(f"MCP Operation '{op_name}' failed: {mcp_result.error_code} - {mcp_result.message}")
                    else:
                         print(f"  Unexpected result type: {type(mcp_result)}")
                         logger.error(f"Unexpected MCP result type: {type(mcp_result)}")
                    # Loop continues, agent sees the result

                except Exception as e:
                    logger.error(f"Error executing MCP operation '{op_name}': {e}", exc_info=True)
                    # Format an error message for history and user
                    error_content = f"Failed to execute MCP operation '{op_name}': {e}"
                    error_msg = Message(role="system", content=error_content)
                    agent_runner.history.append(error_msg)
                    print(f"SYSTEM: {error_content}")
                    # Continue, let the agent see the execution failure

            else:
                # 5. No MCP operation found - Treat as agent's text response or question for user
                print(f"🤖 Agent Response:")
                # Indent agent's text response for clarity
                for line in llm_response_text.strip().split('\n'):
                    print(f"   {line}")

                # Check if the response seems like a question requiring user input
                # Simple check, could be improved (e.g., checking for "?")
                is_question = "?" in llm_response_text or "please provide" in llm_response_text.lower()

                if is_question:
                    print("\n👤 User Input Required.")
                    try:
                        user_response = input("Your Response: ")
                        agent_runner.history.append(Message(role="user", content=user_response))
                        logger.info(f"User provided input: {user_response}")
                    except EOFError:
                        logger.warning("EOF detected, stopping.")
                        agent_runner.history.append(Message(role="system", content="User input stream closed. Stopping."))
                        break
                else:
                    # If it's not an operation and not clearly a question, let the loop continue.
                    # The agent might be explaining its reasoning or stating a fact.
                    logger.info("LLM response was text-based, continuing loop.")
                    # Optional: Add a check here for "Goal Achieved" text if the agent fails
                    # to use the finish_goal operation, but using the operation is preferred.
                    if "goal achieved" in llm_response_text.lower():
                         logger.warning("Agent indicated goal achieved via text, but did not use 'finish_goal' operation. Stopping anyway.")
                         agent_runner.history.append(Message(role="system", content="Agent indicated goal achieved via text. Stopping."))
                         break


            # Optional delay?
            # await asyncio.sleep(1)

        # End of loop
        if step_count >= max_steps:
            logger.warning(f"Reached maximum steps ({max_steps}). Stopping.")
            agent_runner.history.append(Message(role="system", content=f"Reached maximum steps ({max_steps}). Stopping execution."))
            print(f"\nSYSTEM: Reached maximum steps ({max_steps}). Stopping execution.")

    except KeyboardInterrupt:
        logger.info("User interrupted the execution.")
        agent_runner.history.append(Message(role="system", content="Execution interrupted by user."))
        print("\nExecution interrupted by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during the agent run: {e}", exc_info=True)
        agent_runner.history.append(Message(role="system", content=f"An unexpected error occurred: {e}"))
        print(f"\nSYSTEM: An unexpected error occurred: {e}")
    finally:
        # --- Print Final History ---
        print("\n" + "="*20 + " Autonomous Run Finished " + "="*20)
        print(f"Final Goal State: {goal}")
        print("-"*60)
        # Consider writing history to a log file as well
        # logger.info("Final Conversation History:\n" + "\n".join([f"{m.role}: {m.content}" for m in agent_runner.history]))
        print("Final Conversation History:")
        for i, message in enumerate(agent_runner.history):
             role_indicator = {"user": "👤", "assistant": "🤖", "system": "⚙️"}.get(message.role, message.role)
             print(f"--- Turn {i+1} ({role_indicator} {message.role}) ---")
             # Indent content for readability
             for line in message.content.strip().split('\n'):
                 print(f"  {line}")
        print("="*60)

        # Ensure client resources are closed
        if client and hasattr(client, 'close'):
            await client.close()
            logger.info("Client resources closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an autonomous agent with a specific goal.")
    parser.add_argument("goal", help="The goal for the autonomous agent.")
    parser.add_argument("-p", "--provider", default="anthropic", help="LLM provider name (e.g., 'anthropic', 'deepseek'). Default: anthropic")
    parser.add_argument("-m", "--model", default=None, help="Specific model name (optional, uses client default if not specified).")
    parser.add_argument("-a", "--agent-id", default="autonomous-agent-007", help="Identifier for the agent (used for MCP permissions). Default: autonomous-agent-007")
    parser.add_argument("-s", "--max-steps", type=int, default=20, help="Maximum number of steps (LLM calls + Tool Executions) the agent can take. Default: 20")

    args = parser.parse_args()

    try:
        asyncio.run(main(args.goal, args.provider, args.agent_id, args.max_steps, args.model))
    except Exception as e:
        logger.critical(f"Script failed to run: {e}", exc_info=True)
        sys.exit(1)
