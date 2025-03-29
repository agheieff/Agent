#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import argparse
import importlib # Added
from pathlib import Path # Added
from typing import Optional, List, Dict, Tuple, Any # Ensure Optional, List, Dict, Tuple, Any are imported
from dataclasses import dataclass, field # Added for AgentRunResult if defined here or imported
from dotenv import load_dotenv

# --- Setup Project Path ---
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
# --- End Setup ---

# --- Configure Logging ---
load_dotenv()
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
# Determine if running in test environment to potentially increase log level
is_testing = "pytest" in sys.modules
effective_log_level = "DEBUG" if is_testing else log_level_str # Use DEBUG for tests

logging.basicConfig(
    level=effective_log_level, # Use potentially adjusted level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Reduce verbosity of specific libraries unless debugging
if effective_log_level != "DEBUG":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
# --- End Logging Config ---

# --- Import Core Components (after path setup and logging) ---
try:
    from Clients import get_client, Message, BaseClient # Import BaseClient for type hint
    from Core import AgentRunner
    # Import AgentRunResult - assuming it's defined in AgentRunner or Core/__init__
    from Core.agent_runner import AgentRunResult, DEFAULT_MCP_TIMEOUT
    # MCP Models no longer needed directly in run.py
except ImportError as e:
    logger.critical(f"Failed to import necessary modules. Ensure PYTHONPATH is set correctly "
                   f"or run from project root. Error: {e}", exc_info=True)
    sys.exit(1)
# --- End Imports ---

# --- Helper Functions for Interactive Input ---

async def discover_and_validate_providers() -> List[str]:
    """
    Discovers client modules and validates them by attempting initialization.
    Returns a list of provider names that were successfully initialized.
    (Implementation remains the same as provided before)
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
    """
    Displays options and prompts the user for a numbered choice.
    (Implementation remains the same as provided before)
    """
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
    """
    Prompts the user for multi-line input, ending with a double Enter.
    (Implementation remains the same as provided before)
    """
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

async def run_agent_session(goal_arg: Optional[str], provider_arg: Optional[str], agent_id: str, max_steps: int, model_arg: Optional[str]):
    """Sets up and runs the autonomous agent session."""

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
                logger.critical("No valid LLM providers found or could be initialized. Check API keys and dependencies.")
                return # Exit gracefully
            provider = await prompt_for_choice(valid_providers, "Please choose an LLM provider:")
            if not provider:
                print("Provider selection cancelled.")
                return
            logger.info(f"User selected provider: {provider}")
            model = None # Reset model if provider chosen interactively

        # --- Initialize LLM Client ---
        logger.info(f"Initializing LLM client for provider: {provider}")
        try:
            llm_client = await asyncio.to_thread(get_client, provider)
            if not llm_client or not isinstance(llm_client, BaseClient):
                 logger.critical(f"Failed to initialize a valid LLM client for provider '{provider}'.")
                 return
        except Exception as client_init_err:
            logger.critical(f"Failed to initialize LLM client for provider '{provider}': {client_init_err}", exc_info=True)
            return

        # --- Interactive Model Selection ---
        if not model:
            available_models = llm_client.get_available_models()
            if not available_models:
                logger.error(f"Provider '{provider}' reported no available models in its configuration.")
                await llm_client.close()
                return

            default_model = llm_client.default_model
            model_prompt = f"Please choose a model for '{provider}' (default: {default_model}):"
            display_models = [f"{m} {'(default)' if m == default_model else ''}" for m in available_models]

            chosen_display_model = await prompt_for_choice(display_models, model_prompt)
            if not chosen_display_model:
                print("Model selection cancelled.")
                await llm_client.close()
                return

            model = chosen_display_model.split(' (default)')[0].strip()
            logger.info(f"User selected model: {model}")

        # --- Set and Validate Model on Client ---
        try:
            llm_client.get_model_config(model) # Validate final model exists
            llm_client.default_model = model # Ensure this model is used for subsequent calls
            logger.info(f"Using LLM model: {model}")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid model name or config for '{model}' with provider '{provider}': {e}")
            await llm_client.close()
            return

        # --- Interactive Goal Input ---
        if not goal:
            goal = await prompt_for_multiline_input("Please enter the goal for the agent:")
            if not goal:
                print("Goal input cancelled or empty.")
                await llm_client.close()
                return
            logger.info(f"User entered goal: {goal[:100]}...") # Log truncated goal

        # --- Configuration & AgentRunner Initialization ---
        mcp_url = os.getenv("MCP_SERVER_URL")
        mcp_timeout = float(os.getenv("MCP_TIMEOUT", DEFAULT_MCP_TIMEOUT))

        if not mcp_url:
            logger.critical("MCP_SERVER_URL environment variable is not set. Cannot connect to MCP.")
            logger.critical("Please set MCP_SERVER_URL (e.g., export MCP_SERVER_URL='http://localhost:8000/mcp')")
            await llm_client.close()
            return
        logger.info(f"Connecting to MCP server at: {mcp_url} (Timeout: {mcp_timeout}s)")

        agent_runner = AgentRunner(
            client=llm_client,
            goal=goal,
            mcp_server_url=mcp_url,
            agent_id=agent_id,
            mcp_timeout=mcp_timeout,
            max_steps=max_steps
        )

        # --- Run the Agent's Autonomous Loop ---
        print("\n" + "="*20 + " Starting Autonomous Agent Run " + "="*20)
        print(f"Goal: {goal}")
        print(f"Agent ID: {agent_id}")
        print(f"Provider: {provider} (Model: {model})")
        print(f"MCP URL: {mcp_url}")
        print(f"Max Steps: {max_steps}")
        print("="*60 + "\n")

        # Execute the autonomous run
        run_result: AgentRunResult = await agent_runner.run_autonomous()

        # --- Process Result ---
        print("\n" + "="*20 + " Autonomous Run Finished " + "="*20)
        print(f"Outcome: {run_result.status}")
        print(f"Steps Taken: {run_result.steps_taken}")
        if run_result.status == "completed":
             print(f"Final Summary: {run_result.final_message}")
        elif run_result.status == "error":
             print(f"Error Message: {run_result.final_message}")

        # Optionally print final history (can be verbose)
        if run_result.final_history and logger.isEnabledFor(logging.DEBUG):
             print("\n" + "-"*20 + " Final Conversation History " + "-"*20)
             for i, message in enumerate(run_result.final_history):
                 role_indicator = {"user": "👤", "assistant": "🤖", "system": "⚙️"}.get(message.role, message.role)
                 print(f"--- Turn {i+1} ({role_indicator} {message.role}) ---")
                 for line in str(message.content).strip().split('\n'): # Ensure content is string
                     print(f"  {line}")
             print("="*60)

    except KeyboardInterrupt:
        logger.info("User interrupted the session setup.")
        print("\nSession setup interrupted by user.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during setup or execution: {e}", exc_info=True)
        print(f"\nSYSTEM ERROR: An unexpected error occurred: {e}")
    finally:
        # --- Cleanup ---
        if agent_runner: # If runner was initialized, use its close method
            await agent_runner.close()
            logger.info("AgentRunner resources closed.")
        elif llm_client: # Otherwise, ensure the client is closed
            await llm_client.close()
            logger.info("LLM Client resources closed (AgentRunner might not have initialized).")
        else:
            logger.info("Run finished (Client/Runner may not have fully initialized).")


# --- Argument Parsing and Main Execution ---
if __name__ == "__main__":
    DEFAULT_AGENT_ID = "autonomous-agent-007" # Default agent ID from permissions

    parser = argparse.ArgumentParser(
        description="Run an autonomous agent with a specific goal, interactively prompting if needed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Show defaults in help
    )
    parser.add_argument("-g", "--goal", default=None, help="The goal for the autonomous agent (will prompt if not provided).")
    parser.add_argument("-p", "--provider", default=None, help="LLM provider name (e.g., 'anthropic', 'deepseek'; will prompt if not provided).")
    parser.add_argument("-m", "--model", default=None, help="Specific model name (optional; will prompt if provider is chosen interactively or if omitted).")
    parser.add_argument("-a", "--agent-id", default=DEFAULT_AGENT_ID, help="Identifier for the agent (used for MCP permissions).")
    parser.add_argument("-s", "--max-steps", type=int, default=20, help="Maximum number of steps (LLM calls + Tool Executions) the agent can take.")

    args = parser.parse_args()

    try:
        asyncio.run(run_agent_session(args.goal, args.provider, args.agent_id, args.max_steps, args.model))
    except KeyboardInterrupt:
        logger.info("Script terminated by user (KeyboardInterrupt).")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Script failed to run due to an unhandled error: {e}", exc_info=True)
        sys.exit(1)
