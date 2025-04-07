import asyncio
import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import traceback # Keep for error reporting

from Clients.base import BaseClient, ProviderConfig
from Core.agent_config import AgentConfiguration
from Core.agent_instance import AgentInstance
from Core.executor import Executor
from Tools.error_codes import ConversationEnded
from Prompts.main import build_system_prompt, discover_tools, Tool # Import Tool for type hint

# --- Updated Config Loading ---
def load_agent_configurations(config_dir: str = "./AgentConfigs") -> List[AgentConfiguration]:
    """Loads agent configurations from YAML files in a directory."""
    print(f"Loading agent configurations from: {config_dir}")
    configs = []
    config_path = Path(config_dir)
    if not config_path.is_dir():
        print(f"Warning: Configuration directory '{config_dir}' not found.")
        return []

    # Load defaults first
    default_config_data = {}
    default_file = config_path / "default_agent.yaml"
    if default_file.exists():
        try:
            with open(default_file, 'r') as f:
                default_config_data = yaml.safe_load(f) or {}
            print(f"  Loaded defaults from {default_file.name}")
        except Exception as e:
            print(f"Warning: Failed to load default config '{default_file.name}': {e}")

    # Load specific agent configs
    for file_path in config_path.glob("*.yaml"):
        if file_path.name == "default_agent.yaml":
            continue

        try:
            with open(file_path, 'r') as f:
                agent_data = yaml.safe_load(f)
                if not agent_data or not isinstance(agent_data, dict):
                     print(f"Warning: Skipping invalid or empty YAML file: {file_path.name}")
                     continue

                # Apply Defaults
                final_data = default_config_data.copy()
                final_data.update(agent_data)

                # Enforce required fields & Provide runtime defaults
                if 'agent_id' not in final_data:
                     final_data['agent_id'] = file_path.stem
                     print(f"Warning: 'agent_id' not found in {file_path.name}, using filename '{final_data['agent_id']}'.")
                if 'role' not in final_data:
                     final_data['role'] = final_data['agent_id']

                final_data.setdefault('model_provider', 'deepseek')
                final_data.setdefault('model_name', 'deepseek-chat')
                # Ensure system_prompt defaults reasonably
                final_data.setdefault('system_prompt', f"You are an AI assistant with the role: {final_data['role']}.")
                final_data.setdefault('allowed_tools', [])

                # Create AgentConfiguration object
                config = AgentConfiguration(
                    agent_id=final_data['agent_id'],
                    role=final_data['role'],
                    model_provider=final_data['model_provider'],
                    model_name=final_data['model_name'],
                    system_prompt=final_data['system_prompt'],
                    allowed_tools=final_data['allowed_tools'],
                    # Add directory_permissions later:
                    # directory_permissions=final_data.get('directory_permissions', {})
                )
                configs.append(config)
                print(f"  Loaded config for agent: {config.agent_id} (Provider: {config.model_provider}, Model: {config.model_name})")

        except Exception as e:
            print(f"Error loading or parsing config file {file_path.name}: {e}")
            traceback.print_exc() # Show traceback for config loading errors

    if not configs:
         print("Error: No specific agent configurations were successfully loaded. Exiting.")
         # Exit or raise? Let's raise for now.
         raise ValueError("Failed to load any valid agent configurations.")

    return configs

class Orchestrator:
    """Manages multiple agent instances and their interactions."""

    def __init__(self, config_list: List[AgentConfiguration]):
        self.agents: Dict[str, AgentInstance] = {}
        self.clients: Dict[str, BaseClient] = {}
        self.executor = Executor() # Shared executor
        self.all_discovered_tools: Dict[str, Tool] = {} # Store discovered tools

        print("Initializing Orchestrator...")
        # Discover tools once during initialization
        self.all_discovered_tools = discover_tools()
        print(f"Orchestrator discovered tools: {list(self.all_discovered_tools.keys())}")

        self._initialize_clients(config_list)
        self._create_agents(config_list) # Pass discovered tools here

    # --- _initialize_clients method remains the same ---
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

                    api_key = os.getenv(provider_config.api_key_env)
                    if not api_key:
                         print(f"Warning: API key {provider_config.api_key_env} not found. Agent using {provider_name} might fail.")

                    sig = inspect.signature(client_class.__init__)
                    if 'config' in sig.parameters: client_instance = client_class(config=provider_config)
                    else: client_instance = client_class()

                    self.clients[provider_name] = client_instance
                    print(f"  Initialized client for: {provider_name}")

                except (ImportError, ValueError, AttributeError, RuntimeError, Exception) as e:
                    print(f"Error initializing client for {provider_name}: {e}")


    # --- Updated _create_agents to pass tools ---
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
                # Pass the discovered tools dictionary to the AgentInstance
                agent_instance = AgentInstance(config, client, self.executor, self.all_discovered_tools)
                self.agents[config.agent_id] = agent_instance
            except ValueError as e:
                 print(f"Error creating agent '{config.agent_id}': {e}")
            except Exception as e:
                 print(f"Unexpected error creating agent '{config.agent_id}': {e}")
                 traceback.print_exc()


    # --- run_main_loop method remains the same ---
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
                    # print(f"Orchestrator (to {target_agent_id}): Proceed.") # Less noisy

                # Execute the agent's turn
                result = await agent.execute_turn()

                turn_count += 1

                # --- Basic Loop Control ---
                if isinstance(result, str) and result.startswith("[ERROR:"):
                    print(f"\n[Orchestrator] Agent '{target_agent_id}' reported error. Stopping loop.")
                    break
                # Check if agent produced no meaningful output AND no tool was used in this turn
                if result == "" and not any(m.content.startswith("Tool ") or m.content.startswith("Calling tool:") for m in agent.messages[-(len(agent.messages) - turn_start_msg_index):]): # Check msgs added this turn
                     # Find index of messages before this turn started
                     # This logic is getting complex, simplify the check
                     if result == "" and agent.messages[-1].role != 'user': # If turn ended empty and last msg isnt user proceed
                          # Check if the effective last assistant message (non-tool) was also empty/non-existent
                          last_assistant_text = ""
                          for msg in reversed(agent.messages):
                              if msg.role == 'assistant' and not msg.content.startswith("Tool ") and not msg.content.startswith("Calling tool:"):
                                   last_assistant_text = msg.content
                                   break
                              if msg.role == 'user': # Don't look past last user message
                                   break
                          if not last_assistant_text.strip():
                               print(f"\n[Orchestrator] Agent '{target_agent_id}' produced no text output and no tool called. Stopping loop.")
                               break


                # Check for pause (placeholder - requires AgentInstance signalling)
                # if agent.should_pause_externally: ...

                if turn_count >= max_turns:
                    print(f"\n[Orchestrator] Reached max turns ({max_turns}). Stopping loop.")
                    break

                await asyncio.sleep(0.2) # Small delay

        except ConversationEnded as e:
            print(f"\n[Orchestrator] Caught ConversationEnded signal from agent '{target_agent_id}': {e}")
        except KeyboardInterrupt:
            print("\n[Orchestrator] Keyboard interrupt detected. Stopping.")
        except Exception as e:
            print(f"\n[Orchestrator] An unexpected error occurred in the main loop: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            print(f"\n--- Main Loop Finished ({target_agent_id}) ---")
