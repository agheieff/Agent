#!/usr/bin/env python3
import os
import sys
import argparse
import dotenv
import asyncio
import traceback

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Core.orchestrator import Orchestrator, load_agent_configurations
from Core.utils import get_multiline_input

def load_env_variables():
    env_file = os.path.join(project_root, ".env")
    if os.path.isfile(env_file):
        print(f"Loading environment variables from {env_file}")
        dotenv.load_dotenv(env_file)
    else:
        print("Warning: .env file not found. API keys must be set in environment.")

async def main():
    load_env_variables()

    parser = argparse.ArgumentParser(description="Run the multi-agent system orchestrator.")
    parser.add_argument("--prompt", type=str, default=None, help="Initial prompt for the CEO agent.")
    parser.add_argument("--agent", type=str, default="ceo", help="ID of the agent to interact with initially.")
    parser.add_argument("--max-turns", type=int, default=10, help="Maximum number of autonomous turns.")
    # Add args to override default model/provider for specific agents later if needed
    # parser.add_argument("--ceo-provider", type=str, help="Override CEO provider")
    # parser.add_argument("--ceo-model", type=str, help="Override CEO model")

    args = parser.parse_args()

    initial_prompt = args.prompt
    if not initial_prompt:
        initial_prompt = get_multiline_input("Enter the initial prompt for the CEO agent (press Enter twice to submit):\n")
        if not initial_prompt:
             print("Error: No initial prompt provided.")
             sys.exit(1)

    try:
        # Load configurations (replace with file loading later)
        agent_configs = load_agent_configurations()

        # --- Optional: Override config based on args ---
        # Example: Override CEO model if args are provided
        # if args.ceo_provider or args.ceo_model:
        #     for cfg in agent_configs:
        #         if cfg.agent_id == 'ceo':
        #             if args.ceo_provider: cfg.model_provider = args.ceo_provider
        #             if args.ceo_model: cfg.model_name = args.ceo_model
        #             print(f"Overriding CEO config: Provider={cfg.model_provider}, Model={cfg.model_name}")
        #             break
        # --------------------------------------------

        # Initialize and run the orchestrator
        orchestrator = Orchestrator(agent_configs)
        if args.agent not in orchestrator.agents:
             print(f"Error: Initial agent '{args.agent}' not found in loaded configurations.")
             print(f"Available agents: {list(orchestrator.agents.keys())}")
             sys.exit(1)

        await orchestrator.run_main_loop(
            initial_prompt=initial_prompt,
            target_agent_id=args.agent,
            max_turns=args.max_turns
        )

    except Exception as e:
        print(f"\nAn error occurred during orchestrator setup or execution: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution cancelled by user.")
