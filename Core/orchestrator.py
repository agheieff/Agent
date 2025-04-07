import asyncio
import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Optional

from Clients.base import BaseClient, ProviderConfig
from Core.agent_config import AgentConfiguration
from Core.agent_instance import AgentInstance
from Core.executor import Executor
from Tools.error_codes import ConversationEnded
from Prompts.main import generate_system_prompt # Keep for default prompt generation

# Placeholder for loading configs (replace with file loading later)
def load_agent_configurations() -> List[AgentConfiguration]:
    """Loads agent configurations (replace with actual file/db loading)."""
    print("Loading default agent configurations...")
    # Example default CEO config
    ceo_tools = ["message", "pause", "end"] # Start with limited tools for CEO
    ceo_prompt = generate_system_prompt("anthropic") # Reuse existing prompt logic for now
    ceo_prompt += "\n\n# ROLE: CEO\nYou are the CEO agent. Your primary role is to interact with the user, understand high-level goals, and delegate tasks to appropriate manager agents (though none exist yet). For now, you will execute tasks yourself using your limited tools or respond directly."

    # Add more default configs here later (Manager, Coder, etc.)

    return [
        AgentConfiguration(
            agent_id="ceo",
            role="CEO",
            model_provider="anthropic", # Default, override via run.py args
            model_name="claude-3-5-sonnet", # Default, override via run.py args
            system_prompt=ceo_prompt,
            allowed_tools=ceo_tools
        ),
        # Example Coder config (not used in simple loop yet)
        # AgentConfiguration(
        #     agent_id="coder_01",
        #     role="Coder",
        #     model_provider="anthropic",
        #     model_name="claude-3-haiku",
        #     system_prompt="You are a coding agent...",
        #     allowed_tools=["read_file", "write_file", "edit_file"]
        # ),
    ]

class Orchestrator:
    """Manages multiple agent instances and their interactions."""

    def __init__(self, config_list: List[AgentConfiguration]):
        self.agents: Dict[str, AgentInstance] = {}
        self.clients: Dict[str, BaseClient] = {} # Shared clients per provider
        self.executor = Executor() # Shared executor

        print("Initializing Orchestrator...")
        self._initialize_clients(config_list)
        self._create_agents(config_list)

    def _initialize_clients(self, config_list: List[AgentConfiguration]):
        """Initializes required LLM clients based on agent configs."""
        print("Initializing LLM clients...")
        providers_needed = {cfg.model_provider for cfg in config_list}
        for provider_name in providers_needed:
            if provider_name not in self.clients:
                try:
                    api_dir = Path(__file__).parent.parent / "Clients" / "API"
                    module = importlib.import_module(f"Clients.API.{provider_name}")
                    client_class = None
                    provider_config = None
                    config_name_const = f"{provider_name.upper()}_CONFIG"

                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient:
                             if name.lower() == f"{provider_name}client": client_class = obj
                        if isinstance(obj, ProviderConfig) and name == config_name_const: provider_config = obj

                    if not client_class: raise ValueError(f"Client class not found for {provider_name}")
                    if not provider_config: raise ValueError(f"ProviderConfig const not found for {provider_name}")

                    # Check API key
                    api_key = os.getenv(provider_config.api_key_env)
                    if not api_key:
                         print(f"Warning: API key {provider_config.api_key_env} not found. Agent using {provider_name} might fail.")
                         # Decide whether to skip or proceed allowing potential failure
                         # continue # Option: Skip client creation if key missing

                    # Instantiate client (handle config arg possibility)
                    sig = inspect.signature(client_class.__init__)
                    if 'config' in sig.parameters: client_instance = client_class(config=provider_config)
                    else: client_instance = client_class()

                    self.clients[provider_name] = client_instance
                    print(f"  Initialized client for: {provider_name}")

                except (ImportError, ValueError, AttributeError, RuntimeError, Exception) as e:
                    print(f"Error initializing client for {provider_name}: {e}")
                    # Decide if this is fatal or if other agents can proceed
                    # raise  # Option: Make it fatal

    def _create_agents(self, config_list: List[AgentConfiguration]):
        """Creates AgentInstance objects from configurations."""
        print("Creating agent instances...")
        for config in config_list:
            if config.agent_id in self.agents:
                print(f"Warning: Duplicate agent_id '{config.agent_id}'. Skipping.")
                continue
            client = self.clients.get(config.model_provider)
            if not client:
                print(f"Warning: Client for provider '{config.model_provider}' not initialized. Cannot create agent '{config.agent_id}'.")
                continue
            try:
                agent_instance = AgentInstance(config, client, self.executor)
                self.agents[config.agent_id] = agent_instance
            except ValueError as e:
                 print(f"Error creating agent '{config.agent_id}': {e}")


    async def run_main_loop(self, initial_prompt: str, target_agent_id: str = "ceo", max_turns: int = 10):
        """
        Runs a simplified main loop focusing on a single agent for now.
        """
        print(f"\n--- Starting Main Loop (Target: {target_agent_id}, Max Turns: {max_turns}) ---")
        agent = self.agents.get(target_agent_id)
        if not agent:
            print(f"Error: Target agent '{target_agent_id}' not found.")
            return

        # Add initial prompt to the target agent
        agent.add_message('user', initial_prompt)
        print(f"User (to {target_agent_id}): {initial_prompt}")

        turn_count = 0
        try:
            while turn_count < max_turns:
                print(f"\n--- Turn {turn_count + 1} ({target_agent_id}) ---")

                # Ensure alternating roles before executing turn
                if agent.messages and agent.messages[-1].role == 'assistant':
                    # Last turn ended with assistant. Add placeholder user turn.
                    agent.add_message('user', "Proceed.")
                    print(f"Orchestrator (to {target_agent_id}): Proceed.")


                # Execute the agent's turn
                result = await agent.execute_turn()

                turn_count += 1

                # --- Basic Loop Control ---
                # Check if agent returned an error
                if isinstance(result, str) and result.startswith("[ERROR:"):
                    print(f"\n[Orchestrator] Agent '{target_agent_id}' reported error. Stopping loop.")
                    break
                # Check if agent produced no meaningful output (might indicate completion or stuck state)
                if result == "" and agent.messages[-1].role != 'user': # Agent produced no text, last msg likely tool result or empty assistant msg
                      # Let's check if a tool was run in the last message additions
                      tool_run_in_last_turn = any(m.content.startswith("Tool ") or m.content.startswith("Calling tool:") for m in agent.messages[-2:]) # Check last ~2 msgs
                      if not tool_run_in_last_turn:
                           print(f"\n[Orchestrator] Agent '{target_agent_id}' produced no text output. Stopping loop.")
                           break
                      else:
                           print(f"\n[Orchestrator] Agent '{target_agent_id}' finished turn with tool use. Continuing...")


                # Check for pause (placeholder for future implementation)
                # if agent.needs_external_pause: # Requires AgentInstance to signal pause state
                #     print("[Orchestrator] Agent requested pause. Pausing loop.")
                #     # Get user input and add to agent messages
                #     # Reset pause flag

                # Simple loop break for now
                if turn_count >= max_turns:
                    print(f"\n[Orchestrator] Reached max turns ({max_turns}). Stopping loop.")
                    break

                await asyncio.sleep(0.2) # Small delay between turns

        except ConversationEnded as e:
            print(f"\n[Orchestrator] Caught ConversationEnded signal from agent '{target_agent_id}': {e}")
        except KeyboardInterrupt:
             print("\n[Orchestrator] Keyboard interrupt detected. Stopping.")
        except Exception as e:
            print(f"\n[Orchestrator] An unexpected error occurred in the main loop: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            print(f"\n--- Main Loop Finished ({target_agent_id}) ---")
