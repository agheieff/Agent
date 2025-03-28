#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import argparse
from typing import Optional # Ensure Optional is imported
from dotenv import load_dotenv

# --- Setup Project Path ---
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
# --- End Setup ---

# --- Configure Logging ---
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
    from Clients import get_client, Message, BaseClient # Import BaseClient for type hint
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
    mcp_url = os.getenv("MCP_SERVER_URL")
    mcp_timeout = float(os.getenv("MCP_TIMEOUT", DEFAULT_MCP_TIMEOUT)) # Get MCP timeout from env or default

    # --- Sanity Checks ---
    if not mcp_url:
        logger.error("MCP_SERVER_URL environment variable is not set. Cannot connect to MCP.")
        logger.error("Please set MCP_SERVER_URL (e.g., export MCP_SERVER_URL='http://localhost:8000/mcp')")
        sys.exit(1)
    logger.info(f"Connecting to MCP server at: {mcp_url} (Timeout: {mcp_timeout}s)")

    # --- Initialize LLM Client ---
    logger.info(f"Initializing LLM client for provider: {provider}")
    llm_client: Optional[BaseClient] = None
    agent_runner: Optional[AgentRunner] = None # Define runner variable

    try:
        # Pass only provider config to get_client
        llm_client = get_client(provider) # mcp_server_url and mcp_agent_id removed

        if not llm_client:
            logger.error(f"Failed to initialize LLM client for provider '{provider}'. Check API keys and dependencies.")
            sys.exit(1)

        # Optional: Set specific model if provided
        if model:
            try:
                llm_client.get_model_config(model) # Validate model exists in config
                llm_client.default_model = model
                logger.info(f"Using LLM model: {model}")
            except (ValueError, TypeError) as e: # Catch TypeError for invalid config structure
                logger.error(f"Invalid model name or config for '{model}' with provider '{provider}': {e}")
                await llm_client.close() # Clean up initialized client
                sys.exit(1)
        else:
            logger.info(f"Using default model for {provider}: {llm_client.default_model}")


        # --- Initialize AgentRunner ---
        # Pass LLM client and MCP details to AgentRunner
        agent_runner = AgentRunner(
            client=llm_client,
            goal=goal,
            mcp_server_url=mcp_url, # Pass MCP URL here
            agent_id=agent_id,
            mcp_timeout=mcp_timeout, # Pass MCP timeout here
            max_steps=max_steps
        )

    except Exception as setup_err:
         logger.error(f"Failed during setup: {setup_err}", exc_info=True)
         if llm_client: await llm_client.close() # Attempt cleanup
         if agent_runner: await agent_runner.close()
         sys.exit(1)

    # --- Run the Agent Loop ---
    print("\n" + "="*20 + " Starting Autonomous Agent Run " + "="*20)
    print(f"Goal: {goal}")
    print(f"Agent ID: {agent_id}")
    print(f"Provider: {provider} (Model: {llm_client.default_model})") # Use llm_client here
    print(f"MCP URL: {mcp_url}")
    print(f"Max Steps: {max_steps}")
    print("="*60 + "\n")

    step_count = 0
    try:
        while step_count < max_steps:
            step_count += 1
            print(f"\n--- Step {step_count}/{max_steps} ---")

            # 1. Prepare messages for LLM
            # AgentRunner history contains the state
            messages_for_llm = agent_runner.history.copy()
            # Add initial prompt or context if history is empty
            if not messages_for_llm:
                 # Add a user message to kick off the process based on the goal
                 initial_user_message = f"My goal is: {goal}. Please devise a plan and proceed."
                 # Or simply:
                 # initial_user_message = "Proceed with the initial goal."
                 messages_for_llm.append(Message(role="user", content=initial_user_message))
                 logger.info("History is empty, adding initial user message.")

            logger.debug(f"Messages for LLM (excluding system prompt):\n{messages_for_llm}")

            # 2. Call LLM using the client associated with AgentRunner
            try:
                print("🤖 Agent thinking...")
                # AgentRunner's client handles system prompt based on its type
                llm_response_text = await agent_runner.client.chat_completion(
                    messages=messages_for_llm
                    # Pass other kwargs like temperature, max_tokens if needed
                    # temperature=0.5
                )
                logger.debug(f"LLM Raw Response: {llm_response_text}")

                if not llm_response_text:
                    logger.warning("LLM returned an empty response. Stopping.")
                    agent_runner.history.append(Message(role="system", content="LLM returned an empty response. Stopping."))
                    break

                # Add LLM response to history *before* parsing/execution
                agent_runner.history.append(Message(role="assistant", content=llm_response_text))

            except Exception as e:
                logger.error(f"Error during LLM call: {e}", exc_info=True)
                error_msg = f"Error calling LLM: {e}. Stopping."
                agent_runner.history.append(Message(role="system", content=error_msg))
                print(f"SYSTEM ERROR: {error_msg}")
                break # Stop execution on LLM error

            # 3. Parse LLM response for MCP operation using AgentRunner's method
            mcp_call_data = agent_runner.parse_llm_response(llm_response_text) # Use renamed method

            if mcp_call_data:
                # 4. Execute MCP Operation
                operation_details = mcp_call_data.get("mcp_operation", {})
                op_name = operation_details.get("operation_name")
                # Use .get with default {} for arguments
                op_args = operation_details.get("arguments", {})

                if not op_name:
                    logger.error("Parsed MCP call, but 'operation_name' is missing.")
                    result_msg = Message(role="system", content="Error: Assistant tried to call an operation but did not specify 'operation_name'.")
                    agent_runner.history.append(result_msg)
                    print(f"SYSTEM ERROR: {result_msg.content}")
                    continue # Go to next step

                # Handle 'finish_goal' sentinel operation
                if op_name == "finish_goal":
                    print(f"🏁 Agent initiated 'finish_goal'.")
                    summary = op_args.get("summary", "[No summary provided]")
                    print(f"🏁 Final Summary from Agent: {summary}")
                    # Add system message confirming finish signal
                    agent_runner.history.append(Message(role="system", content=f"Agent signaled goal completion. Summary: {summary}"))
                    logger.info("Agent called finish_goal. Stopping loop.")
                    break # Exit the loop

                # Execute other operations using AgentRunner's method
                print(f"🛠️ Agent wants to execute: {op_name}({op_args})")
                logger.info(f"Attempting to execute MCP operation '{op_name}' with args: {op_args}")
                try:
                    # Use AgentRunner's execute method
                    mcp_result = await agent_runner.execute_mcp_operation(
                        operation_name=op_name,
                        arguments=op_args
                    )

                    # Format result using AgentRunner's method and add to history
                    result_msg = agent_runner.format_mcp_result(mcp_result) # Use renamed method
                    agent_runner.history.append(result_msg)

                    # Display result to user
                    print(f"⚙️ SYSTEM: MCP Operation Result ({op_name}):")
                    # Use the formatted message content for display
                    for line in result_msg.content.strip().split('\n'):
                         print(f"  {line}")

                    if isinstance(mcp_result, MCPSuccessResponse):
                        logger.info(f"MCP Operation '{op_name}' successful.")
                    elif isinstance(mcp_result, MCPErrorResponse):
                        logger.warning(f"MCP Operation '{op_name}' failed: {mcp_result.error_code} - {mcp_result.message}")
                    # Loop continues, agent sees the result message in history

                except Exception as e:
                    # Catch errors during the MCP execution call itself (if AgentRunner raises them)
                    logger.error(f"Error executing MCP operation '{op_name}' via AgentRunner: {e}", exc_info=True)
                    error_content = f"System Error: Failed to execute MCP operation '{op_name}': {e}"
                    error_msg = Message(role="system", content=error_content)
                    agent_runner.history.append(error_msg)
                    print(f"SYSTEM ERROR: {error_content}")
                    # Continue loop, let agent see the system error message

            else:
                # 5. No MCP operation found - Treat as text response or user query
                print(f"🤖 Agent Response:")
                # Indent agent's text response for clarity
                for line in llm_response_text.strip().split('\n'):
                    print(f"   {line}")

                # Check if response implies user input is needed
                is_question = "?" in llm_response_text or "please provide" in llm_response_text.lower() or "do you want me to" in llm_response_text.lower()

                if is_question:
                    print("\n👤 User Input Required.")
                    try:
                        # Use asyncio.to_thread to avoid blocking the event loop with input()
                        user_response = await asyncio.to_thread(input, "Your Response: ")
                        agent_runner.history.append(Message(role="user", content=user_response))
                        logger.info(f"User provided input: {user_response}")
                    except (EOFError, KeyboardInterrupt): # Catch Ctrl+D or Ctrl+C during input
                        logger.warning("User input interrupted (EOF or KeyboardInterrupt). Stopping.")
                        agent_runner.history.append(Message(role="system", content="User input stream closed. Stopping."))
                        raise KeyboardInterrupt # Re-raise to exit main loop cleanly
                else:
                    # If it's not an operation and not clearly a question, just log and continue.
                    logger.info("LLM response was text-based, continuing loop.")
                    # Check if agent is hallucinating goal completion without using the operation
                    if "goal achieved" in llm_response_text.lower() or "objective complete" in llm_response_text.lower():
                        logger.warning("Agent indicated goal achieved via text, but did not use 'finish_goal' operation. Stopping loop.")
                        agent_runner.history.append(Message(role="system", content="Agent indicated goal achieved via text. Stopping."))
                        break

            # Optional delay between steps if needed
            # await asyncio.sleep(0.5)

        # End of while loop
        if step_count >= max_steps:
            logger.warning(f"Reached maximum steps ({max_steps}). Stopping.")
            agent_runner.history.append(Message(role="system", content=f"Reached maximum steps ({max_steps}). Stopping execution."))
            print(f"\nSYSTEM: Reached maximum steps ({max_steps}). Stopping execution.")

    except KeyboardInterrupt:
        logger.info("User interrupted the execution.")
        if agent_runner: # Add message only if runner was initialized
             agent_runner.history.append(Message(role="system", content="Execution interrupted by user."))
        print("\nExecution interrupted by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during the agent run: {e}", exc_info=True)
        if agent_runner: # Add message only if runner was initialized
             agent_runner.history.append(Message(role="system", content=f"An unexpected error occurred: {e}"))
        print(f"\nSYSTEM ERROR: An unexpected error occurred: {e}")
    finally:
        # --- Print Final History ---
        print("\n" + "="*20 + " Autonomous Run Finished " + "="*20)
        if agent_runner: # Check if runner was initialized before accessing history
             print(f"Final Goal State: {agent_runner.goal}")
             print("-"*60)
             print("Final Conversation History:")
             for i, message in enumerate(agent_runner.history):
                 role_indicator = {"user": "👤", "assistant": "🤖", "system": "⚙️"}.get(message.role, message.role)
                 print(f"--- Turn {i+1} ({role_indicator} {message.role}) ---")
                 # Indent content for readability
                 for line in message.content.strip().split('\n'):
                     print(f"  {line}")
             print("="*60)

             # Ensure AgentRunner resources (including its http_client) are closed
             await agent_runner.close()
             logger.info("AgentRunner resources closed.")
        else:
             print("Run finished (AgentRunner may not have fully initialized).")
             # Ensure LLM client is closed if it was created but runner failed
             if llm_client:
                  await llm_client.close()
                  logger.info("LLM Client resources closed.")


# --- Argument Parsing and Main Execution ---
if __name__ == "__main__":
    # Default agent ID from permissions config
    DEFAULT_AGENT_ID = "autonomous-agent-007"

    parser = argparse.ArgumentParser(description="Run an autonomous agent with a specific goal.")
    parser.add_argument("goal", help="The goal for the autonomous agent.")
    parser.add_argument("-p", "--provider", default="anthropic", help="LLM provider name (e.g., 'anthropic', 'deepseek'). Default: anthropic")
    parser.add_argument("-m", "--model", default=None, help="Specific model name (optional, uses client default if not specified).")
    parser.add_argument("-a", "--agent-id", default=DEFAULT_AGENT_ID, help=f"Identifier for the agent (used for MCP permissions). Default: {DEFAULT_AGENT_ID}")
    parser.add_argument("-s", "--max-steps", type=int, default=20, help="Maximum number of steps (LLM calls + Tool Executions) the agent can take. Default: 20")

    args = parser.parse_args()

    # --- Add Import statement for DEFAULT_MCP_TIMEOUT ---
    try:
        # Assuming DEFAULT_MCP_TIMEOUT is defined in Core.agent_runner
        from Core.agent_runner import DEFAULT_MCP_TIMEOUT
    except ImportError:
        # Fallback or re-definition if import fails
        DEFAULT_MCP_TIMEOUT = 30.0
        logger.warning("Could not import DEFAULT_MCP_TIMEOUT, using fallback value.")
    # --- End Import statement ---


    try:
        asyncio.run(main(args.goal, args.provider, args.agent_id, args.max_steps, args.model))
    except KeyboardInterrupt:
         logger.info("Script terminated by user (KeyboardInterrupt).")
         sys.exit(0) # Clean exit on Ctrl+C
    except Exception as e:
        logger.critical(f"Script failed to run due to an unhandled error: {e}", exc_info=True)
        sys.exit(1)
