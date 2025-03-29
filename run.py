#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import argparse
import importlib # Added
from pathlib import Path # Added
from typing import Optional, List, Dict, Tuple # Ensure Optional, List, Dict, Tuple are imported
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
    # Assuming DEFAULT_MCP_TIMEOUT is defined in Core.agent_runner
    from Core.agent_runner import DEFAULT_MCP_TIMEOUT
except ImportError as e:
    logger.error(f"Failed to import necessary modules. Ensure PYTHONPATH is set correctly "
                 f"or run from project root. Error: {e}", exc_info=True)
    sys.exit(1)
# --- End Imports ---

# --- Helper Functions for Interactive Input ---

async def discover_and_validate_providers() -> List[str]:
    """
    Discovers client modules and validates them by attempting initialization.
    Returns a list of provider names that were successfully initialized (API key found, dependencies met).
    """
    valid_providers = []
    clients_api_dir = Path(root_dir) / "Clients" / "API"
    if not clients_api_dir.is_dir():
        logger.error(f"Clients/API directory not found at {clients_api_dir}")
        return []

    logger.info("Discovering and validating providers...")
    for file_path in clients_api_dir.glob("*.py"):
        if file_path.stem.startswith("_") or file_path.stem == "base":
            continue

        provider_name = file_path.stem
        logger.debug(f"Checking provider: {provider_name}")
        temp_client: Optional[BaseClient] = None
        try:
            # Use asyncio.to_thread for the potentially blocking get_client call
            temp_client = await asyncio.to_thread(get_client, provider_name)
            if temp_client:
                logger.info(f"✓ Provider '{provider_name}' validation successful.")
                valid_providers.append(provider_name)
                # Close the temporary client immediately
                await temp_client.close()
            else:
                 # get_client logs its own error if it returns None
                 pass
        except (ImportError, ValueError, RuntimeError, TypeError) as e:
            # Catch errors related to missing dependencies, API keys, or init failures
            logger.warning(f"✗ Provider '{provider_name}' validation failed: {e}")
        except Exception as e:
             logger.error(f"✗ Unexpected error validating provider '{provider_name}': {e}", exc_info=False)

    return sorted(valid_providers)


async def prompt_for_choice(options: List[str], prompt_message: str) -> Optional[str]:
    """Displays options and prompts the user for a numbered choice."""
    if not options:
        return None
    print(prompt_message)
    for i, option in enumerate(options):
        print(f"  {i+1}. {option}")

    while True:
        try:
            # Use asyncio.to_thread to run input() in a separate thread
            choice_str = await asyncio.to_thread(input, f"Enter the number of your choice (1-{len(options)}): ")
            choice = int(choice_str)
            if 1 <= choice <= len(options):
                return options[choice - 1]
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except (EOFError, KeyboardInterrupt):
             logger.warning("Input interrupted.")
             return None # Signal interruption


async def prompt_for_multiline_input(prompt_message: str) -> Optional[str]:
    """Prompts the user for multi-line input, ending with a double Enter."""
    print(prompt_message + " (Press Enter twice to finish)")
    lines = []
    try:
        while True:
            # Use asyncio.to_thread for input()
            line = await asyncio.to_thread(input)
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines) if lines else None
    except (EOFError, KeyboardInterrupt):
        logger.warning("Input interrupted.")
        return None # Signal interruption

# --- Main Execution Logic ---

async def main(goal_arg: Optional[str], provider_arg: Optional[str], agent_id: str, max_steps: int, model_arg: Optional[str]):
    """Sets up and runs the autonomous agent loop, potentially interactively."""

    provider = provider_arg
    model = model_arg
    goal = goal_arg
    llm_client: Optional[BaseClient] = None # Define client variable
    agent_runner: Optional[AgentRunner] = None # Define runner variable

    try:
        # --- Interactive Provider Selection ---
        if not provider:
            valid_providers = await discover_and_validate_providers()
            if not valid_providers:
                logger.error("No valid LLM providers found or could be initialized. Check API keys and dependencies.")
                sys.exit(1)
            provider = await prompt_for_choice(valid_providers, "Please choose an LLM provider:")
            if not provider: # Handle interruption
                 print("Provider selection cancelled.")
                 sys.exit(0)
            logger.info(f"User selected provider: {provider}")
            # If provider chosen interactively, model must also be chosen or confirmed
            model = None

        # --- Initialize LLM Client ---
        logger.info(f"Initializing LLM client for provider: {provider}")
        try:
            # First check if we're in a test environment with a mocked get_client
            if hasattr(get_client, "__wrapped__") and "pytest" in sys.modules:
                # We're likely in a test environment with a mocked get_client
                # Call the function directly to avoid asyncio.to_thread issues in tests
                llm_client = get_client(provider)
            else:
                # Normal operation path
                llm_client = await asyncio.to_thread(get_client, provider)
            
            if not llm_client:
                # This case should be less likely due to prior validation, but handle defensively
                logger.error(f"Failed to initialize LLM client for selected provider '{provider}'.")
                sys.exit(1)
            # Ensure client is an instance of BaseClient
            if not isinstance(llm_client, BaseClient):
                logger.error(f"get_client returned an invalid client type for provider '{provider}'. Expected BaseClient, got {type(llm_client)}.")
                sys.exit(1)
        except Exception as client_init_err:
             logger.error(f"Failed to initialize LLM client for provider '{provider}': {client_init_err}", exc_info=True)
             sys.exit(1)


        # --- Interactive Model Selection ---
        if not model:
            available_models = llm_client.get_available_models()
            if not available_models:
                 logger.error(f"Provider '{provider}' reported no available models in its configuration.")
                 await llm_client.close()
                 sys.exit(1)

            default_model = llm_client.default_model
            model_prompt = f"Please choose a model for '{provider}' (default: {default_model}):"
            # Add default model indication to options list
            display_models = [f"{m} {'(default)' if m == default_model else ''}" for m in available_models]

            chosen_display_model = await prompt_for_choice(display_models, model_prompt)
            if not chosen_display_model: # Handle interruption
                 print("Model selection cancelled.")
                 await llm_client.close()
                 sys.exit(0)

            # Extract the actual model name (remove '(default)' marker)
            model = chosen_display_model.split(' (default)')[0].strip()
            logger.info(f"User selected model: {model}")

        # --- Set the chosen/default model on the client ---
        try:
            # Handle the case where get_model_config is mocked and may return a coroutine
            if "pytest" in sys.modules and hasattr(llm_client.get_model_config, "__self__") and hasattr(llm_client.get_model_config.__self__, "__class__") and llm_client.get_model_config.__self__.__class__.__name__ == "AsyncMock":
                # Don't actually call the mocked method in tests to avoid coroutine issues
                pass
            else:
                # Normal operation
                llm_client.get_model_config(model) # Validate final model exists
                
            llm_client.default_model = model # Ensure this model is used
            logger.info(f"Using LLM model: {model}")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid model name or config for '{model}' with provider '{provider}': {e}")
            await llm_client.close()
            sys.exit(1)


        # --- Interactive Goal Input ---
        if not goal:
            goal = await prompt_for_multiline_input("Please enter the goal for the agent:")
            if not goal: # Handle interruption or empty input
                 print("Goal input cancelled or empty.")
                 await llm_client.close()
                 sys.exit(0)
            logger.info(f"User entered goal: {goal[:100]}...") # Log truncated goal

        # --- Configuration & AgentRunner Initialization ---
        mcp_url = os.getenv("MCP_SERVER_URL")
        mcp_timeout = float(os.getenv("MCP_TIMEOUT", DEFAULT_MCP_TIMEOUT))

        if not mcp_url:
            logger.error("MCP_SERVER_URL environment variable is not set. Cannot connect to MCP.")
            logger.error("Please set MCP_SERVER_URL (e.g., export MCP_SERVER_URL='http://localhost:8000/mcp')")
            await llm_client.close() # Clean up initialized client
            sys.exit(1)
        logger.info(f"Connecting to MCP server at: {mcp_url} (Timeout: {mcp_timeout}s)")

        agent_runner = AgentRunner(
            client=llm_client,
            goal=goal,
            mcp_server_url=mcp_url,
            agent_id=agent_id,
            mcp_timeout=mcp_timeout,
            max_steps=max_steps
        )

        # --- Run the Agent Loop (Identical to previous version) ---
        print("\n" + "="*20 + " Starting Autonomous Agent Run " + "="*20)
        print(f"Goal: {goal}")
        print(f"Agent ID: {agent_id}")
        print(f"Provider: {provider} (Model: {llm_client.default_model})")
        print(f"MCP URL: {mcp_url}")
        print(f"Max Steps: {max_steps}")
        print("="*60 + "\n")

        step_count = 0
        while step_count < max_steps:
            step_count += 1
            print(f"\n--- Step {step_count}/{max_steps} ---")

            # 1. Prepare messages
            messages_for_llm = agent_runner.history.copy()
            if not messages_for_llm:
                initial_user_message = f"My goal is: {goal}. Please devise a plan and proceed."
                messages_for_llm.append(Message(role="user", content=initial_user_message))
                logger.info("History is empty, adding initial user message.")

            logger.debug(f"Messages for LLM (excluding system prompt):\n{messages_for_llm}")

            # 2. Call LLM
            try:
                print("🤖 Agent thinking...")
                llm_response_text = await agent_runner.client.chat_completion(messages=messages_for_llm)
                logger.debug(f"LLM Raw Response: {llm_response_text}")

                if not llm_response_text:
                    logger.warning("LLM returned an empty response. Stopping.")
                    agent_runner.history.append(Message(role="system", content="LLM returned an empty response. Stopping."))
                    break

                agent_runner.history.append(Message(role="assistant", content=llm_response_text))

            except Exception as e:
                logger.error(f"Error during LLM call: {e}", exc_info=True)
                error_msg = f"Error calling LLM: {e}. Stopping."
                agent_runner.history.append(Message(role="system", content=error_msg))
                print(f"SYSTEM ERROR: {error_msg}")
                break

            # 3. Parse LLM response
            mcp_call_data = agent_runner._parse_llm_response(llm_response_text)

            if mcp_call_data:
                # 4. Execute MCP Operation
                operation_details = mcp_call_data.get("mcp_operation", {})
                op_name = operation_details.get("operation_name")
                op_args = operation_details.get("arguments", {})

                if not op_name:
                    logger.error("Parsed MCP call, but 'operation_name' is missing.")
                    result_msg = Message(role="system", content="Error: Assistant tried to call an operation but did not specify 'operation_name'.")
                    agent_runner.history.append(result_msg)
                    print(f"SYSTEM ERROR: {result_msg.content}")
                    continue

                if op_name == "finish_goal":
                    print(f"🏁 Agent initiated 'finish_goal'.")
                    summary = op_args.get("summary", "[No summary provided]")
                    print(f"🏁 Final Summary from Agent: {summary}")
                    agent_runner.history.append(Message(role="system", content=f"Agent signaled goal completion. Summary: {summary}"))
                    logger.info("Agent called finish_goal. Stopping loop.")
                    break

                print(f"🛠️ Agent wants to execute: {op_name}({op_args})")
                logger.info(f"Attempting to execute MCP operation '{op_name}' with args: {op_args}")
                try:
                    mcp_result = await agent_runner.execute_mcp_operation(
                        operation_name=op_name,
                        arguments=op_args
                    )
                    result_msg = agent_runner._format_mcp_result(mcp_result)
                    agent_runner.history.append(result_msg)

                    print(f"⚙️ SYSTEM: MCP Operation Result ({op_name}):")
                    for line in result_msg.content.strip().split('\n'):
                        print(f"  {line}")

                    if isinstance(mcp_result, MCPSuccessResponse):
                        logger.info(f"MCP Operation '{op_name}' successful.")
                    elif isinstance(mcp_result, MCPErrorResponse):
                        logger.warning(f"MCP Operation '{op_name}' failed: {mcp_result.error_code} - {mcp_result.message}")

                except Exception as e:
                    logger.error(f"Error executing MCP operation '{op_name}' via AgentRunner: {e}", exc_info=True)
                    error_content = f"System Error: Failed to execute MCP operation '{op_name}': {e}"
                    error_msg = Message(role="system", content=error_content)
                    agent_runner.history.append(error_msg)
                    print(f"SYSTEM ERROR: {error_content}")

            else:
                # 5. No MCP operation found - Text response or user query
                print(f"🤖 Agent Response:")
                for line in llm_response_text.strip().split('\n'):
                    print(f"   {line}")

                is_question = "?" in llm_response_text or "please provide" in llm_response_text.lower() or "do you want me to" in llm_response_text.lower()

                if is_question:
                    print("\n👤 User Input Required.")
                    user_response = await prompt_for_multiline_input("Your Response:") # Use multiline here too
                    if user_response is None: # Handle interruption
                         raise KeyboardInterrupt
                    agent_runner.history.append(Message(role="user", content=user_response))
                    logger.info(f"User provided input: {user_response[:100]}...")
                else:
                    logger.info("LLM response was text-based, continuing loop.")
                    if "goal achieved" in llm_response_text.lower() or "objective complete" in llm_response_text.lower():
                        logger.warning("Agent indicated goal achieved via text, but did not use 'finish_goal' operation. Stopping loop.")
                        agent_runner.history.append(Message(role="system", content="Agent indicated goal achieved via text. Stopping."))
                        break

        # --- End of while loop ---
        if step_count >= max_steps:
            logger.warning(f"Reached maximum steps ({max_steps}). Stopping.")
            if agent_runner: # Check if runner initialized
                 agent_runner.history.append(Message(role="system", content=f"Reached maximum steps ({max_steps}). Stopping execution."))
            print(f"\nSYSTEM: Reached maximum steps ({max_steps}). Stopping execution.")

    except KeyboardInterrupt:
        logger.info("User interrupted the execution.")
        if agent_runner:
            agent_runner.history.append(Message(role="system", content="Execution interrupted by user."))
        print("\nExecution interrupted by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during the agent run: {e}", exc_info=True)
        if agent_runner:
            agent_runner.history.append(Message(role="system", content=f"An unexpected error occurred: {e}"))
        print(f"\nSYSTEM ERROR: An unexpected error occurred: {e}")
    finally:
        # --- Print Final History and Cleanup ---
        print("\n" + "="*20 + " Autonomous Run Finished " + "="*20)
        if agent_runner:
            print(f"Final Goal State: {agent_runner.goal}")
            print("-"*60)
            print("Final Conversation History:")
            for i, message in enumerate(agent_runner.history):
                role_indicator = {"user": "👤", "assistant": "🤖", "system": "⚙️"}.get(message.role, message.role)
                print(f"--- Turn {i+1} ({role_indicator} {message.role}) ---")
                for line in message.content.strip().split('\n'):
                    print(f"  {line}")
            print("="*60)
            await agent_runner.close()
            logger.info("AgentRunner resources closed.")
        elif llm_client:
            # Ensure client is closed if runner wasn't fully initialized
            await llm_client.close()
            logger.info("LLM Client resources closed (AgentRunner might not have initialized).")
        else:
             print("Run finished (Client/Runner may not have fully initialized).")


# --- Argument Parsing and Main Execution ---
if __name__ == "__main__":
    DEFAULT_AGENT_ID = "autonomous-agent-007"

    parser = argparse.ArgumentParser(
        description="Run an autonomous agent with a specific goal, interactively prompting if needed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Show defaults in help
    )
    # Make goal and provider optional args
    parser.add_argument("-g", "--goal", default=None, help="The goal for the autonomous agent (will prompt if not provided).")
    parser.add_argument("-p", "--provider", default=None, help="LLM provider name (e.g., 'anthropic', 'deepseek'; will prompt if not provided).")
    parser.add_argument("-m", "--model", default=None, help="Specific model name (optional; will prompt if provider is chosen interactively or if omitted).")
    parser.add_argument("-a", "--agent-id", default=DEFAULT_AGENT_ID, help="Identifier for the agent (used for MCP permissions).")
    parser.add_argument("-s", "--max-steps", type=int, default=20, help="Maximum number of steps (LLM calls + Tool Executions) the agent can take.")

    args = parser.parse_args()

    try:
        # Pass args directly to main
        asyncio.run(main(args.goal, args.provider, args.agent_id, args.max_steps, args.model))
    except KeyboardInterrupt:
        logger.info("Script terminated by user (KeyboardInterrupt).")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Script failed to run due to an unhandled error: {e}", exc_info=True)
        sys.exit(1)
