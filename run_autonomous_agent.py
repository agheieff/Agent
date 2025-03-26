#!/usr/bin/env python3
"""
Example script to run the autonomous agent.
"""
import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Ensure project root is in path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# --- Configure Logging ---
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level_str,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Reduce verbosity of HTTPX logs
logger = logging.getLogger(__name__)
# --- End Logging Config ---

# --- Load Environment Variables ---
load_dotenv()
# --- End Env Vars ---

# --- Import Core Components (after path setup and logging) ---
try:
    from Clients import get_client, AnthropicClient, DeepSeekClient # Import specific clients you might use
    from Core import AgentRunner
except ImportError as e:
    logger.error(f"Failed to import necessary modules. Ensure PYTHONPATH is set correctly "
                 f"or run from project root. Error: {e}", exc_info=True)
    sys.exit(1)
# --- End Imports ---


async def main():
    """Sets up and runs the autonomous agent."""

    # --- Configuration ---
    provider_name = "anthropic" # or "deepseek", "openai", etc.
    # model_name = "claude-3-5-sonnet" # Optional: Specify model, otherwise client default is used
    agent_goal = "Read the file '/tmp/agent_data/input.txt', summarize its content, and write the summary to '/tmp/agent_data/summary.txt'."
    agent_identifier = "file-summarizer-001"
    max_agent_steps = 15
    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp") # Ensure MCP server is running

    # --- Sanity Checks ---
    if not mcp_url:
        logger.error("MCP_SERVER_URL environment variable is not set. Cannot connect to MCP.")
        sys.exit(1)

    # Ensure the target directory for the goal exists (for this example)
    # In a real scenario, the agent might need to create directories using an operation
    try:
        agent_data_path = "/tmp/agent_data" # Match the path used in default permissions
        os.makedirs(agent_data_path, exist_ok=True)
        # Create a dummy input file for the goal
        with open(os.path.join(agent_data_path, "input.txt"), "w") as f:
             f.write("This is the first line of the input file.\n")
             f.write("This is the second line, containing some important details.\n")
             f.write("The third line provides context.\n")
             f.write("Finally, the fourth line concludes the input.\n")
        logger.info(f"Created dummy input file in {agent_data_path}")
    except Exception as e:
         logger.warning(f"Could not create example directory/file at /tmp/agent_data: {e}. "
                        f"Agent file operations might fail if permissions are restricted to this path.")


    # --- Initialize Client ---
    logger.info(f"Initializing client for provider: {provider_name}")
    # Pass MCP config directly to the client constructor
    client = get_client(provider_name, mcp_server_url=mcp_url, mcp_agent_id=agent_identifier)

    if not client:
        logger.error(f"Failed to initialize client for provider '{provider_name}'. Check API keys and dependencies.")
        sys.exit(1)

    # Optional: If a specific model was requested, set it (or handle if invalid)
    # if model_name:
    #    try:
    #        client.get_model_config(model_name) # Validate model exists in config
    #        client.default_model = model_name
    #        logger.info(f"Using model: {model_name}")
    #    except ValueError as e:
    #        logger.error(f"Invalid model name '{model_name}' for provider '{provider_name}': {e}")
    #        sys.exit(1)
    # else:
    #    logger.info(f"Using default model for {provider_name}: {client.default_model}")


    # --- Initialize AgentRunner ---
    agent_runner = AgentRunner(
        client=client,
        goal=agent_goal,
        agent_id=agent_identifier,
        max_steps=max_agent_steps
    )

    # --- Run the Agent ---
    try:
        final_history = await agent_runner.run_autonomous()

        # --- Print Final History ---
        print("\n" + "="*20 + " Autonomous Run Finished " + "="*20)
        print(f"Goal: {agent_goal}")
        print("-"*60)
        for i, message in enumerate(final_history):
            print(f"--- Turn {i+1} ({message.role}) ---")
            print(message.content)
            print("-" * 20)
        print("="*60)

    except Exception as e:
        logger.error(f"An error occurred during the autonomous run: {e}", exc_info=True)
    finally:
        # Ensure client resources are closed even if run_autonomous fails early
        if client and hasattr(client, 'close'):
            await client.close()
            logger.info("Ensured client resources are closed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execution interrupted by user.")
        sys.exit(0)
