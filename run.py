#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any # Added Tuple, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
# --- End Setup ---

# --- Configure Logging ---
load_dotenv()
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
is_testing = "pytest" in sys.modules
effective_log_level = "DEBUG" if is_testing else log_level_str

logging.basicConfig(
    level=effective_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
if effective_log_level != "DEBUG":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
# --- End Logging Config ---

# --- Import Core Components (after path setup and logging) ---
try:
    from Clients import get_client, Message, BaseClient
    from Core import AgentRunner
    # AgentRunResult is defined in agent_runner
    from Core.agent_runner import AgentRunResult, DEFAULT_MCP_TIMEOUT
except ImportError as e:
    logger.critical(f"Failed to import necessary modules. Ensure PYTHONPATH is set correctly "
                    f"or run from project root. Error: {e}", exc_info=True)
    sys.exit(1)
# --- End Imports ---

# --- Constants ---
DEFAULT_AGENT_ID = "autonomous-agent-007"

# --- Helper Functions for Interactive Setup ---

async def discover_and_validate_providers() -> List[str]:
    """
    Discovers client modules and validates them by attempting initialization.
    Returns a list of provider names that were successfully initialized.
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
            # In testing, this might be mocked to return a mock client directly.
            temp_client = await asyncio.to_thread(get_client, provider_name)
            if temp_client:
                logger.info(f"✓ Provider '{provider_name}' validation successful.")
                valid_providers.append(provider_name)
                await temp_client.close()
            else:
                # get_client logs its own error if it returns None
                pass
        except (ImportError, ValueError, RuntimeError, TypeError) as e:
            logger.warning(f"✗ Provider '{provider_name}' validation failed: {e}")
        except Exception as e:
            logger.error(f"✗ Unexpected error validating provider '{provider_name}': {e}", exc_info=False)
        finally:
            if temp_client and hasattr(temp_client, 'close'): # Ensure close is attempted even on some errors
                try:
                    await temp_client.close()
                except Exception: # Ignore close errors during validation
                    pass

    return sorted(valid_providers)

async def prompt_for_choice(options: List[str], prompt_message: str) -> Optional[str]:
    """
    Displays options and prompts the user for a numbered choice asynchronously.
    """
    if not options:
        return None
    print(prompt_message)
    for i, option in enumerate(options):
        print(f"  {i+1}. {option}")

    while True:
        try:
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
            return None

async def prompt_for_multiline_input(prompt_message: str) -> Optional[str]:
    """
    Prompts the user for multi-line input asynchronously, ending with a double Enter.
    """
    print(prompt_message + " (Press Enter twice to finish)")
    lines = []
    try:
        while True:
            line = await asyncio.to_thread(input)
            if line == "":
                break
            lines.append(line)
        return "\n".join(lines) if lines else None
    except (EOFError, KeyboardInterrupt):
        logger.warning("Input interrupted.")
        return None

# --- Session Setup Logic ---

@dataclass
class SessionConfig:
    """Configuration determined during session setup."""
    provider: str
    model: str
    goal: str
    agent_id: str
    max_steps: int
    mcp_url: str
    mcp_timeout: float

async def setup_session_interactively(
    goal_arg: Optional[str],
    provider_arg: Optional[str],
    agent_id_arg: str,
    max_steps_arg: int,
    model_arg: Optional[str]
) -> Optional[SessionConfig]:
    """Handles the interactive setup for provider, model, and goal."""
    provider = provider_arg
    model = model_arg
    goal = goal_arg

    temp_client: Optional[BaseClient] = None # Used for validation/model listing

    try:
        # --- Provider Selection ---
        if not provider:
            valid_providers = await discover_and_validate_providers()
            if not valid_providers:
                logger.critical("No valid LLM providers found or could be initialized.")
                return None
            provider = await prompt_for_choice(valid_providers, "Please choose an LLM provider:")
            if not provider:
                print("Provider selection cancelled.")
                return None
            logger.info(f"User selected provider: {provider}")
            model = None # Reset model if provider chosen interactively

        # --- Minimal Client Init for Model Selection (if needed) ---
        # Initialize briefly just to get model list if model not specified
        if not model:
            try:
                logger.debug(f"Temporarily initializing client for '{provider}' to get models.")
                temp_client = await asyncio.to_thread(get_client, provider)
                if not temp_client:
                    logger.critical(f"Failed to initialize client '{provider}' for model selection.")
                    return None

                available_models = temp_client.get_available_models()
                if not available_models:
                    logger.error(f"Provider '{provider}' reported no available models.")
                    return None

                default_model = temp_client.default_model
                model_prompt = f"Please choose a model for '{provider}' (default: {default_model}):"
                display_models = [f"{m} {'(default)' if m == default_model else ''}" for m in available_models]

                chosen_display_model = await prompt_for_choice(display_models, model_prompt)
                if not chosen_display_model:
                    print("Model selection cancelled.")
                    return None

                model = chosen_display_model.split(' (default)')[0].strip()
                logger.info(f"User selected model: {model}")

            finally:
                if temp_client:
                    await temp_client.close()
                    logger.debug("Temporary client closed after model selection.")

        if not goal:
            goal = await prompt_for_multiline_input("Please enter the goal for the agent:")
            if not goal:
                print("Goal input cancelled or empty.")
                return None

        mcp_url = os.getenv("MCP_SERVER_URL")
        mcp_timeout = float(os.getenv("MCP_TIMEOUT", DEFAULT_MCP_TIMEOUT))

        if not mcp_url:
            logger.critical("MCP_SERVER_URL environment variable is not set.")
            return None

        # All checks passed, return config
        return SessionConfig(
            provider=provider,
            model=model,
            goal=goal,
            agent_id=agent_id_arg,
            max_steps=max_steps_arg,
            mcp_url=mcp_url,
            mcp_timeout=mcp_timeout
        )

    except KeyboardInterrupt:
        logger.info("Session setup interrupted by user.")
        print("\nSession setup interrupted.")
        return None
    except Exception as e:
        logger.error(f"Error during session setup: {e}", exc_info=True)
        print(f"\nError during setup: {e}")
        return None
    finally:
        # Ensure temp client is closed if exception occurred mid-setup
        if temp_client and hasattr(temp_client, 'close'):
            try:
                await temp_client.close()
            except Exception:
                pass

# --- Main Agent Execution Logic ---

async def run_agent_session(session_config: SessionConfig):
    """Initializes client/runner and runs the autonomous loop."""
    llm_client: Optional[BaseClient] = None
    agent_runner: Optional[AgentRunner] = None

    try:
        try:
            # Initialize the actual client instance for the run
            llm_client = await asyncio.to_thread(get_client, session_config.provider)
            if not llm_client or not isinstance(llm_client, BaseClient):
                logger.critical(f"Failed to initialize a valid LLM client for provider '{session_config.provider}'.")
                return

            # Validate and set the chosen model
            llm_client.get_model_config(session_config.model) # Validate existence
            llm_client.default_model = session_config.model # Set for the run
            logger.info(f"Using LLM model: {session_config.model}")

        except Exception as client_init_err:
            logger.critical(f"Failed to initialize LLM client for provider '{session_config.provider}': {client_init_err}", exc_info=True)
            return

        # --- Initialize AgentRunner ---
        agent_runner = AgentRunner(
            client=llm_client,
            goal=session_config.goal,
            mcp_server_url=session_config.mcp_url,
            agent_id=session_config.agent_id,
            mcp_timeout=session_config.mcp_timeout,
            max_steps=session_config.max_steps
        )

        # --- Run the Autonomous Loop ---
        print("\n" + "="*20 + " Starting Autonomous Agent Run " + "="*20)
        print(f"Goal: {session_config.goal}")
        print(f"Agent ID: {session_config.agent_id}")
        print(f"Provider: {session_config.provider} (Model: {session_config.model})")
        print(f"MCP URL: {session_config.mcp_url}")
        print(f"Max Steps: {session_config.max_steps}")
        print("="*60 + "\n")

        run_result: AgentRunResult = await agent_runner.run_autonomous()

        # --- Process Result ---
        print("\n" + "="*20 + " Autonomous Run Finished " + "="*20)
        print(f"Outcome: {run_result.status}")
        print(f"Steps Taken: {run_result.steps_taken}")
        if run_result.status == "completed":
            # Use final_message which should contain the summary from finish_goal
            print(f"Final Summary from Agent: {run_result.final_message or '[No summary provided]'}")
        elif run_result.status == "error":
            print(f"Error Message: {run_result.final_message}")
        elif run_result.status == "max_steps":
             print(f"Reason: {run_result.final_message}")

        # Optional: Log or print final history (consider adding a flag for this)
        if run_result.final_history and logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- Final Conversation History ---")
            for i, message in enumerate(run_result.final_history):
                logger.debug(f"Turn {i+1} ({message.role}): {str(message.content)[:200]}...") # Log truncated content
            logger.debug("--- End History ---")

    except KeyboardInterrupt:
        logger.info("Agent run interrupted by user.")
        print("\nAgent run interrupted.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during agent execution: {e}", exc_info=True)
        print(f"\nSYSTEM ERROR: An unexpected error occurred during execution: {e}")
    finally:
        # --- Cleanup ---
        try:
            if agent_runner:
                await agent_runner.close()
                logger.info("AgentRunner resources closed.")
            elif llm_client: # If runner failed but client existed
                await llm_client.close()
                logger.info("LLM Client resources closed.")
            else:
                logger.info("Run finished (Cleanup skipped, client/runner may not have initialized).")

            # ----- FIX 3: Add small sleep before fully exiting -----
            await asyncio.sleep(0.01)
            # -------------------------------------------------------
        except Exception as cleanup_err:
            logger.error(f"Error during cleanup: {cleanup_err}", exc_info=True)


# --- Argument Parsing and Main Execution ---
async def main():
    """Parses arguments and orchestrates the session setup and execution."""
    parser = argparse.ArgumentParser(
        description="Run an autonomous agent with a specific goal, interactively prompting if needed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-g", "--goal", default=None, help="The goal for the autonomous agent.")
    parser.add_argument("-p", "--provider", default=None, help="LLM provider name (e.g., 'anthropic', 'deepseek').")
    parser.add_argument("-m", "--model", default=None, help="Specific model name (optional).")
    parser.add_argument("-a", "--agent-id", default=DEFAULT_AGENT_ID, help="Identifier for the agent (used for MCP permissions).")
    parser.add_argument("-s", "--max-steps", type=int, default=20, help="Maximum steps agent can take.")

    args = parser.parse_args()

    # Perform interactive setup if needed
    session_config = await setup_session_interactively(
        args.goal, args.provider, args.agent_id, args.max_steps, args.model
    )

    # Run the agent session if setup was successful
    if session_config:
        await run_agent_session(session_config)
    else:
        logger.info("Session setup failed or was cancelled. Exiting.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script terminated by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Script failed to run due to an unhandled error: {e}", exc_info=True)
        sys.exit(1)
